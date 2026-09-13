from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, Integer, String

from app.core.database import Base
from app.core.data_protection import EncryptedText, EncryptedJSON


class MealRecord(Base):
    __tablename__ = "meal_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    meal_type = Column(String(20), default="其他")
    meal_date = Column(Date, nullable=False, index=True)
    image_url = Column(String(500), default="")
    items = Column(EncryptedJSON, nullable=False, default=list)
    calories = Column(Float, default=0)
    protein_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    carbs_g = Column(Float, default=0)
    status = Column(String(20), default="confirmed")
    note = Column(EncryptedText, default="")
    created_at = Column(DateTime, default=datetime.now)
