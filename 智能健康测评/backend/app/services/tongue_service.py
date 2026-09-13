"""舌象多特征检测服务（F9）。

架构（v2，2026-09-11 起重写）：

    舌象照片
      │
      ▼
    YOLOv8n 单次前向 → 检出多种舌象特征（14 类，一张图可多标签）
      │
      ▼
    规则层 _derive_conclusion()：由检出特征推导用户侧「舌色 + 苔质 + 覆盖范围」结论
      · 舌色优先级：紫舌(暗红) > 红舌 > 默认淡红
      · 苔质优先级：黄苔 > 白苔 > 滑苔 > 剥苔 > 默认薄白
      · 覆盖范围：苔类框面积 ÷ 整图面积（中性描述，不输出厚薄）
      每条结论都带 evidence（哪条检出、置信度多少），可解释、可审计、可复核。
      │
      ▼
    可信度闸门 FEATURE_RELIABILITY：**只有实测可信的特征才允许写进结论**
      · high/medium → 参与结论；low/unusable → 只进检出明细并在前端标注
      · 实测口径：图级多标签检出率（test 552 张，conf≥0.25）
      │
      ▼
    建议层 build_advice()：翻译成通俗解读 + 可执行建议（只依据可信特征）

与 v1 的区别：v1 的「舌色 / 苔质」来自一个用**弱标签**（按 ROI 颜色统计自动生成）
训练的 3 分类小网络，实测已退化为常量输出（详见
docs/舌象YOLO与苔质分类_技术分析与训练复现.md）。v2 改为由**持证中医师双重审核标注**
训练的检测模型直接给出特征，再由规则层推导结论，不再有「拍脑袋的分类头」。

术语边界：本模块只做「舌象特征观察」，不输出诊断、证型或处方。
"""
import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings
from app.services.tongue_advice import build_advice

logger = logging.getLogger("tongue_service")
_model = None

# 舌象原图公开读桶（供历史记录 <img> 回显）
TONGUE_IMAGES_BUCKET = "health-tongue"

# ---- 14 类舌象特征（类别码与训练用 classes.txt 一致，勿随意调整）----
TONGUE_FEATURES: dict[str, dict[str, str]] = {
    "baitaishe": {"label": "白苔", "group": "coat"},
    "botaishe": {"label": "剥苔", "group": "coat"},
    "chihenshe": {"label": "齿痕舌", "group": "shape"},
    "gandanao": {"label": "肝区凹陷", "group": "area"},
    "hongdianshe": {"label": "红点舌", "group": "shape"},
    "hongshe": {"label": "红舌", "group": "color"},
    "huangtaishe": {"label": "黄苔", "group": "coat"},
    "huataishe": {"label": "滑苔", "group": "coat"},
    "liewenshe": {"label": "裂纹舌", "group": "shape"},
    "pangdashe": {"label": "胖大舌", "group": "shape"},
    "shenquao": {"label": "肾区凹陷", "group": "area"},
    "shoushe": {"label": "瘦小舌", "group": "shape"},
    "xinfeiao": {"label": "心肺区凹陷", "group": "area"},
    "zishe": {"label": "紫舌（暗红）", "group": "color"},
}

# ---- 各特征的实测可靠性（2026-09-11 实测，test 552 张，conf≥0.25，"按图检出"口径）----
# 指标来源：图级多标签检出率评估（见 backend/scripts/evaluate_tongue_features.py），
# recall = 标注含该特征且模型也检出的图占比；f1 = 该特征图级 F1。
# level 含义：
#   high     可信 —— 可直接作为观察结论展示
#   medium   可参考 —— 展示，但提示"仅供参考"
#   low      慎用 —— 仅作参考项，不写入结论，需配合重拍
#   unusable 不可用 —— 测试集上基本测不出，**不参与结论推导，前端须明确标注不可用**
# ⚠️ 这张表是"如实标注能力边界"的关键，不要为了好看把 unusable 调高。
# 分档规则与 scripts/evaluate_tongue_features.py 打印的「可信度建议」完全一致：
#   f1 ≥ 0.70 → high   |   f1 ≥ 0.45 → medium   |   recall ≤ 0.10 → unusable   |   其余 low
# 改这张表 = 改产品对外的能力声明，务必同步更新 MODEL_CARD.md。
FEATURE_RELIABILITY: dict[str, dict[str, Any]] = {
    "baitaishe":   {"level": "high",     "recall": 0.972, "f1": 0.872},
    "huangtaishe": {"level": "high",     "recall": 0.735, "f1": 0.774},
    "liewenshe":   {"level": "high",     "recall": 0.700, "f1": 0.706},
    "shenquao":    {"level": "medium",   "recall": 0.774, "f1": 0.649, "note": "测试集仅 31 张，样本偏少"},
    "hongshe":     {"level": "medium",   "recall": 0.558, "f1": 0.566},
    "shoushe":     {"level": "medium",   "recall": 0.767, "f1": 0.554, "note": "测试集仅 30 张，样本偏少"},
    "chihenshe":   {"level": "medium",   "recall": 0.558, "f1": 0.485, "note": "测试集仅 43 张，精度偏低"},
    "xinfeiao":    {"level": "medium",   "recall": 0.375, "f1": 0.462, "note": "测试集仅 16 张"},
    "pangdashe":   {"level": "low",      "recall": 0.382, "f1": 0.250},
    "botaishe":    {"level": "low",      "recall": 1.000, "f1": 0.250, "note": "测试集仅 1 张，指标不可信"},
    "gandanao":    {"level": "low",      "recall": 0.125, "f1": 0.222, "note": "测试集仅 8 张"},
    "hongdianshe": {"level": "unusable", "recall": 0.050, "f1": 0.084,
                    "note": "标注框仅约 4×9 像素，640 输入下基本不可见"},
    "huataishe":   {"level": "unusable", "recall": 0.000, "f1": 0.000, "note": "测试集 12 张，无一检出"},
    "zishe":       {"level": "unusable", "recall": 0.000, "f1": 0.000,
                    "note": "全库仅 244 个实例（test 0/18）；另测颜色统计规则总准确率仅 0.59，同样不可用"},
}
# 只有这些可信度档次参与「舌色 / 苔质」结论推导
CONCLUSION_LEVELS = ("high", "medium")

# 结论推导规则（列表顺序即优先级）
COLOR_RULES: list[tuple[str, str]] = [("zishe", "暗红"), ("hongshe", "红")]
COLOR_DEFAULT = "淡红"
COAT_RULES: list[tuple[str, str]] = [
    ("huangtaishe", "黄苔"), ("baitaishe", "白苔"), ("huataishe", "滑苔"), ("botaishe", "剥苔"),
]
COAT_DEFAULT = "薄白（无明显苔色）"
COAT_GROUP_CODES = ("baitaishe", "huangtaishe", "huataishe", "botaishe")

# 能力边界（随响应返回，供前端原样展示，避免过度承诺）
CAPABILITY_LIMITS: list[str] = [
    "单次上传只能给出「舌象特征观察」，不等于中医诊断或证型判断。",
    "苔的厚薄无法判断：数据集缺少「厚苔」标注，覆盖面积与厚薄无关（实测无区分度）。",
]
# 苔覆盖面积占比的分档阈值（分母为整图面积）。
# ⚠️ 实测（2026-09-11，60 张有苔图片）：占比全部落在 0.71~1.00，中位数 0.84，
#    没有任何一张低于 0.5 —— 因为 TCM-Tongue 的苔类标注是「整舌级」大框，
#    面积大小反映的是标注方式，**与苔的厚薄无关**。
#    因此这里只输出「覆盖较广 / 较少」这种中性描述，**不输出「厚苔」结论**；
#    真正的厚薄判断需要 TongueDx 数据集的 FurThick 标注。
COAT_AREA_RATIO_WIDE = 0.6
# 单类最低展示置信度：低于该值的检出只进 detections 明细，不参与结论推导
FEATURE_MIN_CONF = 0.25


def _model_path() -> Path:
    raw = Path(settings.TONGUE_YOLO_MODEL)
    return raw if raw.is_absolute() else Path(__file__).resolve().parents[2] / raw


def _get_model():
    """加载舌象多特征检测权重（惰性加载，进程内缓存）。

    注意：加载逻辑必须留在本函数内。历史上该段代码因缩进问题落到了另一个函数内部、
    且位于 return 之后，成了永不执行的死代码，导致即使权重文件存在也始终返回 None
    （页面一直显示「未加载 YOLO 权重」）。
    """
    global _model
    if _model is not None:
        return _model
    path = _model_path()
    if not path.exists():
        logger.warning("未找到舌象 YOLO 权重: %s", path)
        return None
    try:
        from ultralytics import YOLO
        _model = YOLO(str(path))
        logger.info("舌象 YOLO 权重加载成功: %s（%d 类）", path, len(_model.names or {}))
        return _model
    except Exception as exc:  # noqa: BLE001
        logger.exception("加载舌象 YOLO 权重失败: %s", exc)
        return None


def _area(box: list[int]) -> float:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def _derive_conclusion(dets: list[dict], image_size: tuple[int, int]) -> dict[str, Any]:
    """由检出特征推导「舌色 / 苔质 / 厚薄」，每条结论都带 evidence。

    dets：按置信度降序排列的检出列表（每项含 class_name / label / confidence / box）
    """
    image_area = max(1, image_size[0] * image_size[1])
    confident = [d for d in dets if d["confidence"] >= FEATURE_MIN_CONF]
    by_code = {d["class_name"]: d for d in confident}

    def _reliable(code: str) -> bool:
        """该特征是否可信到可以写进结论（unusable / low 只进检出明细，不进结论）。"""
        return FEATURE_RELIABILITY.get(code, {}).get("level") in CONCLUSION_LEVELS

    # ---- 舌色 ----
    # ⚠️ 暗红(zishe) 实测不可用（test 图级召回 0/18），因此当前只能给出「红 / 淡红」。
    #    这不是漏做，是数据不足：全库紫舌仅 244 个实例。前端需同步展示该限制。
    color_value, color_conf = COLOR_DEFAULT, 0.0
    color_evidence = "未检出明确舌色特征，按常见淡红处理（暗红特征模型暂不可用）"
    for code, label in COLOR_RULES:
        hit = by_code.get(code)
        if hit and _reliable(code):
            color_value, color_conf = label, hit["confidence"]
            color_evidence = f"检出「{hit['label']}」置信度 {hit['confidence']:.2f}"
            break

    # ---- 苔质（颜色/性质）----
    coat_value, coat_conf = COAT_DEFAULT, 0.0
    coat_evidence = "未检出明确苔色特征，按薄白处理"
    for code, label in COAT_RULES:
        hit = by_code.get(code)
        if hit and _reliable(code):
            coat_value, coat_conf = label, hit["confidence"]
            coat_evidence = f"检出「{hit['label']}」置信度 {hit['confidence']:.2f}"
            break

    # ---- 苔的覆盖范围（中性描述，不输出「厚苔」结论）----
    # 分母用整图面积：只检出 1 个苔框时，若用「所有框外接矩形」当分母会恒等于 1.0（踩过）。
    # 实测该比例无法区分厚薄（见文件顶部注释），故只作覆盖广度的观察值。
    coat_area = sum(_area(d["box"]) for d in confident if d["class_name"] in COAT_GROUP_CODES)
    coat_ratio = round(min(1.0, coat_area / image_area), 4)
    if coat_area > 0:
        wide = coat_ratio >= COAT_AREA_RATIO_WIDE
        coverage_value = f"苔覆盖{'较广' if wide else '较少'}（约 {coat_ratio * 100:.0f}%）"
        coverage_evidence = (
            f"苔类区域合计约占照片 {coat_ratio * 100:.0f}%"
            f"（分档阈值 {COAT_AREA_RATIO_WIDE * 100:.0f}%）；"
            f"该值是覆盖范围估算，不代表苔的厚薄"
        )
    else:
        coverage_value = "未见明显苔"
        coverage_evidence = "未检出苔类特征，覆盖范围不做判断"

    # ---- 形态特征（齿痕 / 裂纹 / 胖大 / 瘦小 / 红点 / 分区凹陷），按类别去重 ----
    seen_codes: set[str] = set()
    morphology = []
    for d in confident:
        if TONGUE_FEATURES.get(d["class_name"], {}).get("group") not in ("shape", "area"):
            continue
        if d["class_name"] in seen_codes:
            continue
        seen_codes.add(d["class_name"])
        rel = FEATURE_RELIABILITY.get(d["class_name"], {})
        morphology.append({
            "code": d["class_name"],
            "label": d["label"],
            "confidence": d["confidence"],
            "area_ratio": round(_area(d["box"]) / image_area, 4),
            "level": rel.get("level", "unknown"),
            "reliable": rel.get("level") in CONCLUSION_LEVELS,
        })

    return {
        "tongue_color": {"value": color_value, "confidence": round(color_conf, 4),
                         "evidence": color_evidence},
        "coat_color": {"value": coat_value, "confidence": round(coat_conf, 4),
                       "evidence": coat_evidence},
        "coat_thickness": {"value": coverage_value, "area_ratio": coat_ratio,
                           "threshold": COAT_AREA_RATIO_WIDE, "evidence": coverage_evidence},
        "morphology": morphology,
        "limits": CAPABILITY_LIMITS,
        "note": "结论由「检出特征 + 规则」推导得出，不是模型直接输出；仅作健康观察参考。",
    }


def _flatten_observations(conclusion: dict) -> dict[str, Any]:
    """拍平成 v1 兼容字段（前端旧逻辑仍读 tongue_color_observation / coat_observation）。"""
    return {
        "tongue_color_observation": conclusion["tongue_color"]["value"],
        "coat_observation": conclusion["coat_color"]["value"],
        "tongue_color_confidence": conclusion["tongue_color"]["confidence"],
        "coat_confidence": conclusion["coat_color"]["confidence"],
        # 传给建议层时去掉括号里的百分比，只留标签，便于文案映射
        "coat_thickness": conclusion["coat_thickness"]["value"].split("（")[0],
        "observation_note": conclusion["note"],
    }


def analyze_tongue(image_bytes: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    """舌象分析主入口：检出特征 → 推导结论 → 生成建议。"""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    size = (image.width, image.height)
    model = _get_model()

    if model is None:
        # 权重缺失：明确标注，不伪装成检测结果
        return {
            "status": "model_missing", "demo": True, "detections": [], "best": None,
            "features": [], "conclusion": None,
            "image_size": {"width": size[0], "height": size[1]},
            "message": "未加载舌象检测权重，无法分析。请把 TONGUE_YOLO_MODEL 指向训练权重。",
            "disclaimer": "仅供健康观察参考，不能替代医疗诊断。",
        }

    results = model.predict(source=image, conf=settings.TONGUE_YOLO_CONF, verbose=False,
                            max_det=getattr(settings, "TONGUE_YOLO_MAX_DET", 8))
    result = results[0]
    boxes = getattr(result, "boxes", None)
    names = getattr(result, "names", {}) or {}
    dets: list[dict] = []
    if boxes is not None:
        for idx in range(len(boxes)):
            xyxy = boxes.xyxy[idx].tolist()
            conf = float(boxes.conf[idx].item())
            cls_id = int(boxes.cls[idx].item())
            x1, y1, x2, y2 = [max(0, int(v)) for v in xyxy]
            x2, y2 = min(size[0], x2), min(size[1], y2)
            if x2 <= x1 or y2 <= y1:
                continue
            code = str(names.get(cls_id, f"class_{cls_id}"))
            meta = TONGUE_FEATURES.get(code, {})
            dets.append({
                "class_id": cls_id,
                "class_name": code,
                "label": meta.get("label", code),
                "group": meta.get("group", "other"),
                "confidence": round(conf, 4),
                "box": [x1, y1, x2, y2],
                "area_ratio": round(_area([x1, y1, x2, y2]) / max(1, size[0] * size[1]), 4),
            })
    dets.sort(key=lambda d: d["confidence"], reverse=True)

    if not dets:
        return {
            "status": "not_detected", "detections": [], "best": None, "features": [],
            "conclusion": None,
            "image_size": {"width": size[0], "height": size[1]},
            "message": "未检测到清晰的舌象特征，请在自然光下、舌头自然伸出时重拍。",
            "disclaimer": "仅供健康观察参考，不能替代医疗诊断。",
        }

    conclusion = _derive_conclusion(dets, size)
    observations = _flatten_observations(conclusion)
    # 特征列表按类别去重（同一类可能检出多个框，例如舌面多点红刺），保留置信度最高的
    seen: set[str] = set()
    features = []
    for d in dets:
        if d["confidence"] < FEATURE_MIN_CONF or d["class_name"] in seen:
            continue
        seen.add(d["class_name"])
        rel = FEATURE_RELIABILITY.get(d["class_name"], {})
        features.append({"code": d["class_name"], "label": d["label"], "group": d["group"],
                         "confidence": d["confidence"], "box": d["box"],
                         "level": rel.get("level", "unknown"),
                         "recall": rel.get("recall"), "f1": rel.get("f1"),
                         "reliability_note": rel.get("note", ""),
                         "reliable": rel.get("level") in CONCLUSION_LEVELS})
    best = dict(dets[0])
    best.update(observations)
    score = (observations.get("coat_confidence") or observations.get("tongue_color_confidence")
             or best["confidence"])

    return {
        "status": "detected",
        "demo": False,
        "detections": dets,
        "features": features,
        "best": best,
        "conclusion": conclusion,
        # 各特征实测可靠性表（前端按此给标签上色 / 加"不可用"角标）
        "feature_reliability": FEATURE_RELIABILITY,
        "capability_limits": CAPABILITY_LIMITS,
        # 建议只依据「可信 + 可参考」的特征生成，low / unusable 特征不进建议
        "advice": build_advice(observations.get("tongue_color_observation"),
                               observations.get("coat_observation"), score,
                               thickness=observations.get("coat_thickness"),
                               morphology=[m for m in conclusion["morphology"] if m["reliable"]]),
        "image_size": {"width": size[0], "height": size[1]},
        "model_classes": len(names),
        "disclaimer": "仅供健康观察参考，不能替代医疗诊断；如有不适请及时就医。",
    }


def serialize_tongue(record: Any) -> dict:
    image_url = record.image_url or ""
    if getattr(record, "image_object_name", ""):
        image_url = f"/api/tongue/images/{record.id}"
    detail = getattr(record, "detail", None) or {}
    advice = detail.get("advice") if isinstance(detail, dict) else {}
    constitution = advice.get("constitution") if isinstance(advice, dict) else None
    coat = record.coat or ""
    coat_type = coat.split("·", 1)[0].strip() if coat else ""
    return {
        "id": record.id, "user_id": record.user_id, "status": record.status,
        "tongue_color": record.tongue_color or "", "coat": coat,
        "coat_type": coat_type,
        "constitution": constitution or {"label": "未记录", "plain": "本条历史记录没有保存体质倾向。", "evidence": []},
        "confidence": round(record.confidence or 0, 4),
        "box": record.box or [], "image_url": image_url,
        "note": record.note or "",
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def save_tongue_record(db, user_id: str, image_bytes: bytes, mime: str,
                       note: str = "") -> dict | None:
    """分析舌象并保存为历史记录（原图以客户端加密形式存入私有桶）。

    返回序列化后的记录；图片无效 / 未检出舌象特征时不落库，返回 None。
    """
    from uuid import uuid4

    from app.models.tongue import TongueRecord
    from app.utils.minio_client import get_minio

    result = analyze_tongue(image_bytes, mime)
    if result.get("status") != "detected":
        return None

    best = result.get("best") or {}
    conclusion = result.get("conclusion") or {}
    # 1) 原图客户端加密后存入私有 MinIO（失败不阻塞记录落库）
    image_url = ""
    object_name = ""
    try:
        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                   "image/gif": ".gif", "image/bmp": ".bmp"}
        ext = ext_map.get(mime or "image/jpeg", ".jpg")
        object_name = f"tongue/{user_id}/{uuid4().hex}{ext}.enc"
        get_minio().upload_private_encrypted_bytes(
            TONGUE_IMAGES_BUCKET, object_name, image_bytes, mime or "image/jpeg")
    except Exception as exc:  # noqa: BLE001
        logger.warning("舌象原图上传失败（不影响记录）: %s", exc)

    # 2) 记录核心观察结论（保持「观察参考」非诊断措辞）
    thickness = (conclusion.get("coat_thickness") or {}).get("value") or ""
    coat_text = best.get("coat_observation") or ""
    if thickness and thickness != "未见明显苔":
        coat_text = f"{coat_text}·{thickness}" if coat_text else thickness

    record = TongueRecord(
        user_id=user_id,
        status=result["status"],
        tongue_color=best.get("tongue_color_observation") or "",
        coat=coat_text,
        confidence=float(best.get("confidence") or 0),
        box=best.get("box") or [],
        image_url=image_url,
        image_bucket=TONGUE_IMAGES_BUCKET,
        image_object_name=object_name,
        image_mime=mime or "image/jpeg",
        note=(note or "")[:500],
        detail=result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_tongue(record)
