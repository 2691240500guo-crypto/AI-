from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from app.models.privacy import DataConsent
from app.core.security import get_current_user, resolve_user_id


def has_active_health_consent(db: Session, user_id: str) -> bool:
    consent = (db.query(DataConsent)
               .filter_by(user_id=user_id, consent_type="health_data")
               .order_by(DataConsent.id.desc()).first())
    return bool(consent and consent.granted)


def require_health_consent(request: Request, db: Session, claimed_user_id: str | None = None) -> str:
    """Resolve ownership and require explicit consent for health-data collection/transmission."""
    user = get_current_user(request)
    uid = resolve_user_id(request, claimed_user_id)
    if user.get("role") != "admin" and not has_active_health_consent(db, uid):
        raise HTTPException(status_code=428, detail="请先在隐私与数据中同意健康数据使用说明")
    return uid
