"""Health-data subject rights: consent, memory management, export and erasure."""
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.data_protection import encryption_configured
from app.core.security import get_current_user
from app.models.assessment import UserHealthRiskAssessment
from app.models.assistant import AssistantConversation, AssistantMemory, AssistantMessage, UserProfile, AgentRun, AgentStep
from app.models.meal import MealRecord
from app.models.plan import MealPlan
from app.models.privacy import DataConsent, ObjectDeletionTask
from app.models.social import SocialComment, SocialFollow, SocialLike, SocialPost
from app.models.tongue import TongueRecord
from app.schemas.assistant import ConsentRequest, MemoryRequest
from app.schemas.common import ApiResponse
from app.services.assistant_service import list_memories, remember
from app.services.meal_service import serialize_meal
from app.services.privacy_service import has_active_health_consent, require_health_consent
from app.services.tongue_service import serialize_tongue

router = APIRouter(prefix="/api/privacy", tags=["健康数据合规"])


class EraseRequest(BaseModel):
    confirm: str = Field(..., pattern="^DELETE_MY_DATA$")


def _owner(request: Request) -> str:
    return str(get_current_user(request)["id"])


def _consent_dict(consent: DataConsent | None) -> dict:
    return {
        "granted": bool(consent and consent.granted),
        "consent_type": consent.consent_type if consent else "health_data",
        "policy_version": consent.policy_version if consent else "v1.0",
        "source": consent.source if consent else "web",
        "agreed_at": consent.agreed_at.isoformat() if consent and consent.agreed_at else None,
        "revoked_at": consent.revoked_at.isoformat() if consent and consent.revoked_at else None,
    }


@router.get("/status", response_model=ApiResponse)
def privacy_status(request: Request, db: Session = Depends(get_db)):
    uid = _owner(request)
    consent = (db.query(DataConsent).filter_by(user_id=uid, consent_type="health_data")
               .order_by(DataConsent.id.desc()).first())
    return ApiResponse(data={"encryption_configured": encryption_configured(),
                             "consent": _consent_dict(consent)})


@router.put("/consent", response_model=ApiResponse)
def update_consent(req: ConsentRequest, request: Request, db: Session = Depends(get_db)):
    uid = _owner(request)
    now = datetime.now()
    consent = DataConsent(user_id=uid, consent_type="health_data",
                          policy_version=req.policy_version, granted=req.granted,
                          source="web", agreed_at=now if req.granted else None,
                          revoked_at=None if req.granted else now)
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return ApiResponse(message="健康数据使用同意已更新", data=_consent_dict(consent))


@router.get("/memories", response_model=ApiResponse)
def get_memories(request: Request, db: Session = Depends(get_db)):
    return ApiResponse(data=list_memories(db, _owner(request), limit=100))


@router.post("/memories", response_model=ApiResponse)
def create_memory(req: MemoryRequest, request: Request, db: Session = Depends(get_db)):
    uid = require_health_consent(request, db)
    try:
        memory = remember(db, uid, req.content, req.category, "user")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(message="已保存到长期记忆", data=memory)


@router.delete("/memories/{memory_id}", response_model=ApiResponse)
def delete_memory(memory_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.query(AssistantMemory).filter_by(id=memory_id, user_id=_owner(request)).first()
    if not row:
        raise HTTPException(status_code=404, detail="记忆不存在")
    db.delete(row)
    db.commit()
    return ApiResponse(message="长期记忆已删除", data={"id": memory_id})


def _export_data(db: Session, uid: str) -> dict:
    profile = db.query(UserProfile).filter_by(user_id=uid).first()
    assessments = db.query(UserHealthRiskAssessment).filter_by(user_id=uid).all()
    meals = db.query(MealRecord).filter_by(user_id=uid).all()
    tongues = db.query(TongueRecord).filter_by(user_id=uid).all()
    plans = db.query(MealPlan).filter_by(user_id=uid).all()
    conversations = db.query(AssistantConversation).filter_by(user_id=uid).all()
    conversation_ids = [row.id for row in conversations]
    messages = (db.query(AssistantMessage).filter(AssistantMessage.conversation_id.in_(conversation_ids)).all()
                if conversation_ids else [])
    runs = db.query(AgentRun).filter(AgentRun.conversation_id.in_(conversation_ids)).all() if conversation_ids else []
    posts = db.query(SocialPost).filter_by(user_id=uid).all()
    post_ids = [row.id for row in posts]
    comments = db.query(SocialComment).filter_by(user_id=uid).all()
    likes = db.query(SocialLike).filter_by(user_id=uid).all()
    follows = db.query(SocialFollow).filter_by(follower_id=uid).all()
    consent = (db.query(DataConsent).filter_by(user_id=uid).order_by(DataConsent.id.desc()).first())
    return {
        "export_version": "v1.0",
        "exported_at": datetime.now().isoformat(),
        "user_id": uid,
        "profile": {field: getattr(profile, field) for field in (
            "user_id", "user_name", "sex", "age", "height_cm", "weight_kg", "goal",
            "allergies", "conditions", "preferences")} if profile else None,
        "memories": list_memories(db, uid, limit=100),
        "consent": _consent_dict(consent),
        "assessments": [{"id": row.id, "user_name": row.user_name, "sex": row.sex,
                         "age": row.age, "assessment_time": row.assessment_time.isoformat() if row.assessment_time else None,
                         "total_score": row.total_score, "risk_level": row.risk_level,
                         "assessment_basis": row.assessment_basis, "recommendations": row.recommendations,
                         "llm_report": row.llm_report, "bmi": float(row.bmi) if row.bmi is not None else None,
                         "disease_condition": row.disease_condition, "dietary_intake": row.dietary_intake}
                        for row in assessments],
        "meals": [serialize_meal(row) for row in meals],
        "tongue_records": [serialize_tongue(row) for row in tongues],
        "plans": [{"id": row.id, "goal": row.goal, "days": row.days,
                   "calories_target": row.calories_target, "set_label": row.set_label,
                   "personalization": row.personalization, "recipes": row.recipes,
                   "shopping_list": row.shopping_list, "status": row.status,
                   "review_note": row.review_note, "created_at": row.created_at.isoformat() if row.created_at else None}
                  for row in plans],
        "conversations": [{"id": row.id, "title": row.title,
                           "created_at": row.created_at.isoformat() if row.created_at else None,
                           "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                           "messages": [{"role": msg.role, "content": msg.content, "agent": msg.agent,
                                         "created_at": msg.created_at.isoformat() if msg.created_at else None}
                                        for msg in messages if msg.conversation_id == row.id]}
                          for row in conversations],
        "agent_runs": [{"id": run.id, "conversation_id": run.conversation_id,
                        "request_text": run.request_text, "final_answer": run.final_answer,
                        "agent_plan": run.agent_plan or [], "status": run.status,
                        "steps": [{"step_index": step.step_index, "agent": step.agent,
                                   "output_text": step.output_text, "tool_calls": step.tool_calls or [],
                                   "sources": step.sources or [], "status": step.status}
                                  for step in db.query(AgentStep).filter_by(run_id=run.id).all()]}
                       for run in runs],
        "community": {"posts": [{"id": row.id, "content": row.content, "images": row.images,
                                   "tags": row.tags, "status": row.status,
                                   "created_at": row.created_at.isoformat() if row.created_at else None}
                                  for row in posts],
                      "comments": [{"id": row.id, "post_id": row.post_id, "content": row.content,
                                    "created_at": row.created_at.isoformat() if row.created_at else None}
                                   for row in comments],
                      "likes": [{"post_id": row.post_id} for row in likes],
                      "following": [{"following_id": row.following_id} for row in follows]},
    }


@router.get("/export", response_model=ApiResponse)
def export_data(request: Request, db: Session = Depends(get_db)):
    return ApiResponse(message="健康数据导出完成", data=_export_data(db, _owner(request)))


def _object_from_url(url: str) -> tuple[str, str] | None:
    if not url:
        return None
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/", 1)
    if len(parts) != 2:
        return None
    bucket, object_name = parts
    return bucket, object_name


def _process_deletion_tasks(db: Session, limit: int = 100, user_id: str | None = None) -> int:
    """Attempt pending object deletions; failed rows remain for a later retry worker."""
    from app.utils.minio_client import get_minio
    query = db.query(ObjectDeletionTask).filter(ObjectDeletionTask.status == "pending")
    if user_id:
        query = query.filter(ObjectDeletionTask.user_id == user_id)
    rows = (query
            .order_by(ObjectDeletionTask.id).limit(limit).all())
    completed = 0
    for row in rows:
        row.attempts += 1
        try:
            if get_minio().remove_from_bucket(row.bucket, row.object_name):
                row.status = "deleted"
                row.processed_at = datetime.now()
                completed += 1
            else:
                row.last_error = "MinIO 删除返回失败"
        except Exception as exc:  # noqa: BLE001
            row.last_error = str(exc)[:500]
    db.commit()
    return completed


@router.delete("/data", response_model=ApiResponse)
def erase_data(req: EraseRequest, request: Request, db: Session = Depends(get_db)):
    uid = _owner(request)
    conversations = db.query(AssistantConversation).filter_by(user_id=uid).all()
    conversation_ids = [row.id for row in conversations]
    posts = db.query(SocialPost).filter_by(user_id=uid).all()
    post_ids = [row.id for row in posts]
    for row in db.query(TongueRecord).filter_by(user_id=uid).all():
        if row.image_object_name:
            db.add(ObjectDeletionTask(user_id=uid, bucket=row.image_bucket or "health-tongue",
                                      object_name=row.image_object_name))
        else:
            parsed = _object_from_url(row.image_url)
            if parsed:
                db.add(ObjectDeletionTask(user_id=uid, bucket=parsed[0], object_name=parsed[1]))
    for row in posts:
        for image in row.images or []:
            parsed = _object_from_url(image)
            if parsed:
                db.add(ObjectDeletionTask(user_id=uid, bucket=parsed[0], object_name=parsed[1]))
    if post_ids:
        db.query(SocialComment).filter(SocialComment.post_id.in_(post_ids)).delete(synchronize_session=False)
    if conversation_ids:
        db.query(AssistantMessage).filter(AssistantMessage.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
        run_ids = [row.id for row in db.query(AgentRun.id).filter(AgentRun.conversation_id.in_(conversation_ids)).all()]
        if run_ids:
            db.query(AgentStep).filter(AgentStep.run_id.in_(run_ids)).delete(synchronize_session=False)
            db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).delete(synchronize_session=False)
    db.query(SocialComment).filter_by(user_id=uid).delete(synchronize_session=False)
    db.query(SocialLike).filter_by(user_id=uid).delete(synchronize_session=False)
    db.query(SocialFollow).filter((SocialFollow.follower_id == uid) | (SocialFollow.following_id == uid)).delete(synchronize_session=False)
    deleted = {
        "profile": db.query(UserProfile).filter_by(user_id=uid).delete(synchronize_session=False),
        "memories": db.query(AssistantMemory).filter_by(user_id=uid).delete(synchronize_session=False),
        "consents": db.query(DataConsent).filter_by(user_id=uid).delete(synchronize_session=False),
        "assessments": db.query(UserHealthRiskAssessment).filter_by(user_id=uid).delete(synchronize_session=False),
        "meals": db.query(MealRecord).filter_by(user_id=uid).delete(synchronize_session=False),
        "tongue_records": db.query(TongueRecord).filter_by(user_id=uid).delete(synchronize_session=False),
        "plans": db.query(MealPlan).filter_by(user_id=uid).delete(synchronize_session=False),
        "conversations": db.query(AssistantConversation).filter_by(user_id=uid).delete(synchronize_session=False),
        "posts": db.query(SocialPost).filter_by(user_id=uid).delete(synchronize_session=False),
    }
    db.commit()
    deleted_objects = _process_deletion_tasks(db, user_id=uid)
    pending_objects = db.query(ObjectDeletionTask).filter_by(user_id=uid, status="pending").count()
    return ApiResponse(message="健康数据已删除，登录账号保留", data={"deleted": deleted,
                                 "object_deletions": {"completed": deleted_objects, "pending_retry": pending_objects}})


@router.post("/deletion-tasks/retry", response_model=ApiResponse)
def retry_deletion_tasks(request: Request, db: Session = Depends(get_db)):
    """Retry this user's pending object erasures when MinIO is back online."""
    uid = _owner(request)
    pending = db.query(ObjectDeletionTask).filter_by(user_id=uid, status="pending").count()
    completed = _process_deletion_tasks(db, user_id=uid)
    remaining = db.query(ObjectDeletionTask).filter_by(user_id=uid, status="pending").count()
    return ApiResponse(message="删除任务已重试", data={"before": pending, "completed": completed,
                                             "pending_retry": remaining})
