from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProfileRequest(BaseModel):
    user_name: str = "匿名用户"
    sex: str = "其他"
    age: Optional[int] = Field(None, ge=1, le=120)
    height_cm: Optional[int] = Field(None, ge=50, le=250)
    weight_kg: Optional[int] = Field(None, ge=10, le=400)
    goal: str = "保持健康"
    allergies: str
    conditions: str
    preferences: str = ""

    @field_validator("allergies", "conditions")
    @classmethod
    def _required_health_fields(cls, v: str) -> str:
        """过敏/疾病与基础疾病必填（填「无」也算），AI 需据此避开过敏原与饮食禁忌。"""
        if not v or not v.strip():
            raise ValueError("过敏/疾病 与 基础疾病 为必填项（没有请填「无」）")
        return v.strip()


class ChatRequest(BaseModel):
    user_id: str = "ANON001"
    conversation_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=4000)
    # 请求级图谱增强开关（前端可切换，用于演示「接入图谱前/后」对比）：
    #   None → 跟随 .env 的 GRAPH_RAG_ENABLED 默认值
    #   True / False → 本次提问强制开启 / 关闭图谱上下文注入
    use_graph: Optional[bool] = None


class MemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = Field(None, pattern="^(allergy|condition|goal|preference)$")


class ConsentRequest(BaseModel):
    granted: bool
    policy_version: str = Field("v1.0", min_length=1, max_length=20)
