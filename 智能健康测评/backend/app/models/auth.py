from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String
from app.core.database import Base

class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    account = Column(String(64), unique=True, nullable=False, index=True)
    password = Column(String(128), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

