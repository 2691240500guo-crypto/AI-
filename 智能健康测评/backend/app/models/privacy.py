from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class DataConsent(Base):
    __tablename__ = "data_consents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    consent_type = Column(String(40), nullable=False, default="health_data")
    policy_version = Column(String(20), nullable=False, default="v1.0")
    granted = Column(Boolean, nullable=False, default=False)
    source = Column(String(30), default="web")
    agreed_at = Column(DateTime)
    revoked_at = Column(DateTime)


class ObjectDeletionTask(Base):
    """Outbox for reliable MinIO deletion after a user erasure request."""

    __tablename__ = "object_deletion_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    bucket = Column(String(100), nullable=False)
    object_name = Column(String(500), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.now)
    processed_at = Column(DateTime)
