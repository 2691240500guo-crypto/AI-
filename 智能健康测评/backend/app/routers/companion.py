"""Weekly/monthly health summaries and the lightweight companion chat."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, resolve_user_id
from app.models.assessment import UserHealthRiskAssessment
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.meal import MealRecord
from app.models.tongue import TongueRecord
from app.schemas.common import ApiResponse
from app.services.llm_client import get_llm
from app.services.privacy_service import require_health_consent
from app.services.report_service import build_health_report
from app.utils.redis_cache import get_json, set_json

router = APIRouter(prefix="/api", tags=["健康报告与小萌宠"])


class PetChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    user_id: str = "ANON001"
    conversation_id: int | None = None


def _period_range(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "month":
        start = today.replace(day=1)
    else:
        start = today - timedelta(days=today.weekday())
    return start, today


@router.get("/reports/summary", response_model=ApiResponse)
def health_report(period: str = "week", request: Request = None, db: Session = Depends(get_db)):
    period = "month" if period == "month" else "week"
    uid = require_health_consent(request, db)
    start, end = _period_range(period)
    key = f"health:report:{uid}:{period}:{end.isoformat()}"
    cached = get_json(key)
    if cached is not None:
        return ApiResponse(data=cached)

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    assessments = db.query(UserHealthRiskAssessment).filter(
        UserHealthRiskAssessment.user_id == uid,
        UserHealthRiskAssessment.assessment_time >= start_dt,
        UserHealthRiskAssessment.assessment_time < end_dt,
    ).order_by(UserHealthRiskAssessment.assessment_time.desc()).all()
    meals = db.query(MealRecord).filter(
        MealRecord.user_id == uid,
        MealRecord.meal_date >= start,
        MealRecord.meal_date <= end,
    ).order_by(MealRecord.meal_date.desc(), MealRecord.created_at.desc()).all()
    tongues = db.query(TongueRecord).filter(
        TongueRecord.user_id == uid,
        TongueRecord.created_at >= start_dt,
        TongueRecord.created_at < end_dt,
    ).order_by(TongueRecord.created_at.desc()).all()
    conversation_count = db.query(func.count(AssistantConversation.id)).filter(
        AssistantConversation.user_id == uid,
        AssistantConversation.updated_at >= start_dt,
        AssistantConversation.updated_at < end_dt,
    ).scalar() or 0
    report = build_health_report(
        period=period, start=start, end=end,
        assessments=[{"total_score": r.total_score, "risk_level": r.risk_level} for r in assessments],
        meals=[{"calories": r.calories, "protein_g": r.protein_g, "fat_g": r.fat_g, "carbs_g": r.carbs_g} for r in meals],
        tongues=[{"tongue_color": r.tongue_color, "coat": r.coat} for r in tongues],
        conversations=int(conversation_count),
    )
    set_json(key, report, ttl_seconds=120)
    return ApiResponse(data=report)


def _conversation(db: Session, user_id: str, requested_id: int | None) -> AssistantConversation:
    row = None
    if requested_id:
        row = db.query(AssistantConversation).filter_by(id=requested_id, user_id=user_id).first()
    if row is None:
        row = AssistantConversation(user_id=user_id, title="小萌宠健康陪伴")
        db.add(row)
        db.flush()
    return row


@router.post("/pet/chat", response_model=ApiResponse)
def pet_chat(req: PetChatRequest, request: Request, db: Session = Depends(get_db)):
    # 萌宠只做轻量情感陪伴，不读取健康数据，因此不要求健康数据授权。
    get_current_user(request)
    uid = resolve_user_id(request, req.user_id)
    conversation = _conversation(db, uid, req.conversation_id)
    db.add(AssistantMessage(conversation_id=conversation.id, role="user", content=req.message, agent="companion"))
    fallback = "我在这里陪你。可以先从今天的一餐、睡眠或心情说起，我会帮你整理成小目标。"
    reply = fallback
    try:
        reply = get_llm().chat([
            {"role": "system", "content": "你是温柔、简短的小萌宠健康陪伴助手。只提供生活方式建议，不做诊断；每次最多三句话。"},
            {"role": "user", "content": req.message},
        ], temperature=0.65, max_tokens=300).strip() or fallback
    except Exception:
        pass
    db.add(AssistantMessage(conversation_id=conversation.id, role="assistant", content=reply, agent="companion"))
    conversation.updated_at = datetime.now()
    db.commit()
    return ApiResponse(data={"conversation_id": conversation.id, "reply": reply, "agent": "companion"})
