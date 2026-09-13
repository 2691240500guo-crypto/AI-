"""社区内容机审服务（文本红线词 + 图片视觉审核）。

设计原则（健康社区合规红线：禁药 / 禁夸大功效 / 禁医疗广告 / 禁色情暴力）：
  - 文本：内置红线词库，命中即转人工复核（pending_review）
  - 图片：调用视觉模型（Qwen3-VL）判定违规类别；**只在明确违规时拦截**，
    不确定一律放行，避免把正常餐照误判；机审服务不可用时放行并标记 checked=False
"""
import json
import logging
import re

from app.services.llm_client import get_llm

logger = logging.getLogger("moderation")

# ---------------------------------------------------------------
# 文本红线词库（禁药 / 禁夸大功效 / 禁医疗广告 / 引流）
# 演示版内置词表，生产可替换为敏感词服务
# ---------------------------------------------------------------
SENSITIVE_WORDS = [
    "包治", "根治", "神药", "特效药", "祖传秘方", "药到病除", "偏方", "处方药",
    "售卖", "出售", "代购", "加微信", "加v", "私聊我", "点击链接",
    "百分百有效", "绝对有效", "三天见效", "月瘦", "不反弹", "立减",
    "减肥药", "燃脂丸", "特效减肥", "保健品疗效",
    "博彩", "赌博", "诈骗", "二维码", "联系方式",
]

# 图片违规类别
IMAGE_CATEGORY_LABELS = {
    "A": "色情低俗",
    "B": "暴力血腥",
    "C": "违法广告 / 引流",
    "D": "其他违法违规",
}

IMAGE_MODERATION_PROMPT = (
    "你是健康社区的内容安全审核员。请判断这张图片是否违反社区红线：\n"
    "A. 色情 / 低俗（裸露、性暗示）\n"
    "B. 暴力 / 血腥 / 恐怖\n"
    "C. 违法广告或引流（二维码、联系方式、出售或代购药品/减肥产品、夸大疗效宣传）\n"
    "D. 其他违法违规内容\n"
    '仅输出 JSON，不要 Markdown：{"safe": true 或 false, "categories": ["A"], "reason": "简短中文原因"}\n'
    "判定原则：只有在**明确**违规时才判 safe=false；不确定一律判 safe=true。"
    "正常的健康饮食、运动记录、舌象照片、风景人像必须放行。"
)


def moderation_verdict_for_unavailable(reason: str = "机审服务暂不可用") -> dict:
    """Fail closed when image moderation cannot establish a safe verdict."""
    return {
        "checked": False,
        "safe": False,
        "status": "pending_review",
        "categories": [],
        "category_labels": ["待人工复核"],
        "reason": (reason or "机审服务暂不可用")[:200],
    }


def moderate_text(text: str) -> str | None:
    """文本机审：返回命中的第一个敏感词；未命中返回 None。"""
    for word in SENSITIVE_WORDS:
        if word in (text or ""):
            return word
    return None


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("moderation response did not contain JSON")
    return json.loads(match.group(0))


def moderate_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    """图片机审。

    返回：
      {"checked": bool, "safe": bool, "categories": ["C"], "reason": "...", "category_labels": [...]}
    checked=False 表示机审未生效（服务异常），此时放行但不拦截。
    """
    try:
        raw = get_llm().vision(image_bytes, mime=mime, prompt=IMAGE_MODERATION_PROMPT)
        payload = _extract_json(raw)
        safe = bool(payload.get("safe", True))
        categories = [c for c in (payload.get("categories") or []) if isinstance(c, str)]
        return {
            "checked": True,
            "safe": safe,
            "categories": categories,
            "category_labels": [IMAGE_CATEGORY_LABELS.get(c, c) for c in categories],
            "reason": str(payload.get("reason") or "")[:200],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("图片机审不可用，转人工复核: %s", exc)
        return moderation_verdict_for_unavailable(f"机审服务暂不可用：{exc}")


def moderate_images_batch(images: list[tuple[bytes, str]]) -> tuple[bool, dict]:
    """批量审核：返回 (是否全部通过, 首个违规结果)。

    先全部审核再上传，避免部分图片已上传后才被拦截。
    """
    for data, mime in images:
        verdict = moderate_image(data, mime)
        if not verdict["checked"] or not verdict["safe"]:
            return False, verdict
    return True, {}
