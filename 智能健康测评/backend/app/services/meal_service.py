import json
import logging
import re
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.meal import MealRecord
from app.services.llm_client import get_llm

logger = logging.getLogger("meal_service")


def aggregate_nutrition(items: list[dict]) -> dict:
    fields = ("calories", "protein_g", "fat_g", "carbs_g")
    return {field: round(sum(float(item.get(field) or 0) for item in items), 1) for field in fields}


def calculate_daily_score(calories: float, target_calories: float, *, is_today: bool) -> int | None:
    """Score a completed day against a personal target.

    In-progress days deliberately have no score until 75% of the target is logged. Otherwise a
    morning meal is incorrectly presented as an unhealthy full-day result.
    """
    target = max(float(target_calories or 0), 1)
    if is_today and calories < target * 0.75:
        return None
    return min(100, max(0, round(100 - abs(float(calories) - target) / target * 100)))


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("vision response did not contain JSON")
    return json.loads(match.group(0))


def analyze_image(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    pending = {"items": [], "status": "pending", "source": "vision", "message": "请补充或修正识别结果后再保存"}
    try:
        prompt = (
            "分析这张餐食照片，仅输出 JSON，不要 Markdown。格式："
            '{"items":[{"name":"菜品","grams":100,"calories":0,"protein_g":0,"fat_g":0,"carbs_g":0}],'
            '"meal_type":"早餐|午餐|晚餐|加餐"}。估算不确定时填 0，禁止编造医学诊断。'
        )
        text = get_llm().vision(image_bytes, mime=mime, prompt=prompt)
        payload = _extract_json(text)
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        nutrition = aggregate_nutrition(items)
        return {"items": items, "meal_type": payload.get("meal_type", "其他"), **nutrition,
                "status": "ready", "source": "vision", "message": "请确认菜品和估算份量"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("meal vision failed: %s", exc)
        return pending


def parse_meal_text(text: str) -> dict:
    """从对话文本中抽取一餐食物记录（AI 智能问答的“帮我记饮食”链路）。

    返回结构与 analyze_image 一致（items/status/totals），前端可复用同一套
    “可编辑确认 → /meals/confirm 落库”交互。
    """
    pending = {"items": [], "status": "pending", "source": "text", "message": "未从描述中识别出明确食物，请补充描述或手动记录"}
    try:
        prompt = (
            "用户描述了一顿饭，请抽取其中的食物并估算营养，仅输出 JSON，不要 Markdown。格式："
            '{"items":[{"name":"食物名","grams":100,"calories":0,"protein_g":0,"fat_g":0,"carbs_g":0}],'
            '"meal_type":"早餐|午餐|晚餐|加餐"}。'
            "每项：grams 为估算克重；热量按中国食物成分表常识估算；gram/热量不确定时填合理估计，不要编造疾病或药物。"
            "若描述里没有具体食物（例如只是说“今天吃得很健康”），返回 {\"items\":[],\"meal_type\":\"其他\"}。"
        )
        raw = get_llm().chat([
            {"role": "system", "content": "你是严谨的营养记录助手，负责把用户的一句话转成结构化饮食数据。"},
            {"role": "user", "content": f"{prompt}\n\n用户的描述：{text}"},
        ], temperature=0.1, max_tokens=900)
        payload = _extract_json(raw)
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if not items:
            return pending
        nutrition = aggregate_nutrition(items)
        return {"items": items, "meal_type": payload.get("meal_type", "其他"), **nutrition,
                "status": "ready", "source": "text", "message": "已识别，请核对克重与热量后保存"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("meal text parse failed: %s", exc)
        return pending


def save_meal(db: Session, user_id: str, meal_type: str, meal_date: date,
              items: list[dict], note: str = "", image_url: str = "") -> dict:
    nutrition = aggregate_nutrition(items)
    record = MealRecord(user_id=user_id, meal_type=meal_type, meal_date=meal_date,
                        items=items, image_url=image_url, note=note, status="confirmed", **nutrition)
    db.add(record)
    db.commit()
    db.refresh(record)
    return serialize_meal(record)


def serialize_meal(record: MealRecord) -> dict:
    return {"id": record.id, "user_id": record.user_id, "meal_type": record.meal_type,
            "meal_date": record.meal_date.isoformat(), "items": record.items or [],
            "calories": round(record.calories or 0, 1), "protein_g": round(record.protein_g or 0, 1),
            "fat_g": round(record.fat_g or 0, 1), "carbs_g": round(record.carbs_g or 0, 1),
            "status": record.status, "note": record.note or "", "created_at": record.created_at.isoformat()}


def daily_summary(db: Session, user_id: str, meal_date: date) -> dict:
    records = db.query(MealRecord).filter_by(user_id=user_id, meal_date=meal_date).order_by(MealRecord.created_at).all()
    totals = aggregate_nutrition([{"calories": r.calories, "protein_g": r.protein_g, "fat_g": r.fat_g, "carbs_g": r.carbs_g} for r in records])
    from app.models.plan import MealPlan

    plan = (db.query(MealPlan)
            .filter_by(user_id=user_id)
            .order_by(MealPlan.updated_at.desc(), MealPlan.id.desc())
            .first())
    target_calories = float(plan.calories_target) if plan and plan.calories_target else 2000.0
    score = calculate_daily_score(totals["calories"], target_calories, is_today=meal_date == date.today()) if records else 0
    return {
        "date": meal_date.isoformat(),
        "meals": [serialize_meal(r) for r in records],
        "totals": totals,
        "score": score,
        "score_message": (
            "今日仍在记录中，完成主要餐次后再计算饮食评分。"
            if score is None else f"按 {int(target_calories)} kcal 个性化目标计算"
        ),
        "target_calories": round(target_calories),
        "meal_count": len(records),
    }
