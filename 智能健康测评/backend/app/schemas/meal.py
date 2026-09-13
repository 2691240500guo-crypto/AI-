from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class MealItem(BaseModel):
    name: str
    grams: float = 0
    calories: float = 0
    protein_g: float = 0
    fat_g: float = 0
    carbs_g: float = 0


class MealConfirmRequest(BaseModel):
    user_id: str = "ANON001"
    meal_type: str = "其他"
    meal_date: date
    items: list[MealItem] = Field(default_factory=list)
    note: str = ""
    image_url: str = ""


class QuickLogRequest(BaseModel):
    """AI 智能问答「帮我记饮食」：把一段描述转成结构化饮食草稿。"""
    user_id: str = "ANON001"
    text: str = Field(..., min_length=2, max_length=500)
    meal_date: date | None = None

