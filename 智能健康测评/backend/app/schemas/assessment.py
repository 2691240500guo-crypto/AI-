"""测评请求/响应模型"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AssessmentRequest(BaseModel):
    """NRS2002 测评入参（结构化）"""
    user_id: str = Field("ANON001", description="用户ID")
    user_name: str = Field("匿名用户", description="姓名")
    sex: str = "男"
    age: int = Field(..., ge=1, le=120, description="年龄(岁)")
    height_cm: Optional[float] = Field(None, description="身高cm（可选，用于计算BMI）")
    weight_kg: Optional[float] = Field(None, description="当前体重kg（可选）")
    bmi: Optional[float] = Field(None, description="BMI（不传则用身高体重算）")
    weight_loss_pct: Optional[float] = Field(None, ge=0, le=100,
                                              description="近3个月体重下降百分比")
    weight_change: str = "无"
    disease_level: str = "无"  # 无/轻度/中度/重度
    disease_condition: str = ""
    dietary_intake: str = "正常"  # 正常/减少25%/减少50%/减少75%/几乎不进食
    need_llm_report: bool = Field(True, description="是否调用 LLM 生成完整报告")


class AssessmentResponse(BaseModel):
    """测评结果"""
    record_id: int
    user_id: str
    user_name: str
    age: int
    bmi: Optional[float]
    total_score: int
    nutritional_impairment_score: int
    disease_severity_score: int
    age_score: int
    risk_level: str
    basis: str
    recommendations: str
    llm_report: Optional[str]
    assessment_time: datetime
    assessment_count: int
