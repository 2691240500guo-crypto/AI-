from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import resolve_user_id
from app.models.assistant import AssistantConversation, AssistantMessage, UserProfile, AgentRun, AgentStep
from app.schemas.assistant import ChatRequest, ProfileRequest
from app.schemas.common import ApiResponse
from app.services.assistant_service import chat, upsert_profile
from app.services.privacy_service import require_health_consent

router = APIRouter(prefix="/api/assistant", tags=["健康助手"])


def _require_consent(request: Request, db: Session, user_id: str) -> str:
    return require_health_consent(request, db, user_id)


class ConversationRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


def _profile_dict(profile: UserProfile) -> dict:
    return {key: getattr(profile, key) for key in (
        "user_id", "user_name", "sex", "age", "height_cm", "weight_kg", "goal",
        "allergies", "conditions", "preferences")}


@router.get("/profile/{user_id}", response_model=ApiResponse)
def get_profile(user_id: str, request: Request, db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)   # 归属以登录身份为准
    profile = db.query(UserProfile).filter_by(user_id=uid).first()
    if not profile:
        return ApiResponse(data={"user_id": uid, "user_name": "匿名用户", "sex": "其他",
                                 "age": None, "height_cm": None, "weight_kg": None,
                                 "goal": "保持健康", "allergies": "", "conditions": "",
                                 "preferences": ""})
    return ApiResponse(data=_profile_dict(profile))


@router.put("/profile/{user_id}", response_model=ApiResponse)
def update_profile(user_id: str, req: ProfileRequest, request: Request, db: Session = Depends(get_db)):
    profile = upsert_profile(db, _require_consent(request, db, user_id), req.model_dump())
    return ApiResponse(data=_profile_dict(profile))


@router.post("/chat", response_model=ApiResponse)
def chat_endpoint(req: ChatRequest, request: Request, db: Session = Depends(get_db)):
    uid = _require_consent(request, db, req.user_id)
    # use_graph：请求级图谱增强开关，None 时由服务端跟随 .env 默认值
    return ApiResponse(data=chat(db, uid, req.message, req.conversation_id, req.use_graph))


# ---------------------------------------------------------------
# 会话管理：列表 / 历史消息 / 重命名 / 删除（均以登录身份为归属）
# ---------------------------------------------------------------
@router.get("/conversations", response_model=ApiResponse)
def list_conversations(request: Request, user_id: str = "ANON001", limit: int = 50,
                       db: Session = Depends(get_db)):
    """我的会话列表（按最近活跃倒序，带消息数与最后一条摘要）。"""
    uid = resolve_user_id(request, user_id)
    rows = (
        db.query(AssistantConversation)
        .filter_by(user_id=uid)
        .order_by(desc(AssistantConversation.updated_at))
        .limit(min(limit, 200))
        .all()
    )
    data = []
    for conv in rows:
        count = db.query(func.count(AssistantMessage.id)).filter_by(conversation_id=conv.id).scalar() or 0
        last = (db.query(AssistantMessage)
                .filter_by(conversation_id=conv.id)
                .order_by(desc(AssistantMessage.id)).first())
        data.append({
            "id": conv.id,
            "title": conv.title or "健康咨询",
            "message_count": count,
            "last_message": (last.content or "")[:60] if last else "",
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        })
    return ApiResponse(data=data)


@router.get("/conversations/{conversation_id}/messages", response_model=ApiResponse)
def conversation_messages(conversation_id: int, request: Request, user_id: str = "ANON001",
                          db: Session = Depends(get_db)):
    """回读某会话的历史消息（校验归属）。"""
    uid = resolve_user_id(request, user_id)
    conv = db.query(AssistantConversation).filter_by(id=conversation_id, user_id=uid).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = (db.query(AssistantMessage)
            .filter_by(conversation_id=conversation_id)
            .order_by(AssistantMessage.created_at, AssistantMessage.id)
            .all())
    runs = (db.query(AgentRun).filter_by(conversation_id=conversation_id)
            .order_by(AgentRun.started_at, AgentRun.id).all())
    return ApiResponse(data={
        "conversation_id": conv.id,
        "title": conv.title or "健康咨询",
        "messages": [{
            "role": m.role, "content": m.content, "agent": m.agent,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
        "agent_runs": [{
            "id": run.id, "request_text": run.request_text, "final_answer": run.final_answer,
            "agent_plan": run.agent_plan or [], "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "steps": [{
                "step_index": step.step_index, "agent": step.agent,
                "input_summary": step.input_summary, "output_text": step.output_text,
                "tool_calls": step.tool_calls or [], "sources": step.sources or [],
                "duration_ms": step.duration_ms, "status": step.status, "error": step.error,
            } for step in db.query(AgentStep).filter_by(run_id=run.id)
                .order_by(AgentStep.step_index).all()],
        } for run in runs],
    })


@router.patch("/conversations/{conversation_id}", response_model=ApiResponse)
def rename_conversation(conversation_id: int, req: ConversationRenameRequest, request: Request,
                        user_id: str = "ANON001", db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)
    conv = db.query(AssistantConversation).filter_by(id=conversation_id, user_id=uid).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    conv.title = req.title.strip()
    db.commit()
    db.refresh(conv)
    return ApiResponse(message="已重命名", data={"id": conv.id, "title": conv.title})


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse)
def delete_conversation(conversation_id: int, request: Request, user_id: str = "ANON001",
                        db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)
    conv = db.query(AssistantConversation).filter_by(id=conversation_id, user_id=uid).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(AssistantMessage).filter_by(conversation_id=conversation_id).delete()
    run_ids = [row.id for row in db.query(AgentRun.id).filter_by(conversation_id=conversation_id).all()]
    if run_ids:
        db.query(AgentStep).filter(AgentStep.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).delete(synchronize_session=False)
    db.delete(conv)
    db.commit()
    return ApiResponse(message="会话已删除", data={"id": conversation_id})
