"""饮食计划记录（支持管理端人工审核与修改）。

生成即落库并置为 pending_review；管理员可修改内容（source 标记 manual）后
通过或驳回。用户端读取「当前计划」时会带上审核状态与营养师备注。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from app.core.database import Base
from app.core.data_protection import EncryptedText


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    goal = Column(String(200), default="保持健康")
    days = Column(Integer, default=7)
    calories_target = Column(Integer, default=2000)
    set_label = Column(String(100), default="")
    personalization = Column(EncryptedText, default="")
    recipes = Column(JSON, default=list, comment="一日三餐菜谱")
    shopping_list = Column(JSON, default=list, comment="购物清单")

    source = Column(String(20), default="ai", comment="ai=AI生成 / manual=已人工调整")
    status = Column(String(20), default="pending_review", index=True,
                    comment="pending_review 待审核 / approved 已通过 / rejected 已驳回")
    review_note = Column(EncryptedText, default="", comment="营养师备注（用户可见）")
    reviewed_by = Column(String(64), default="")
    reviewed_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
