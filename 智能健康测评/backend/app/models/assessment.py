"""用户健康风险测评记录模型（对齐课件 D5 user_health_risk_assessment 表）"""
from datetime import datetime

from sqlalchemy import (
    Column, BigInteger, String, Integer, Text, DateTime,
    Enum as SAEnum, DECIMAL, TIMESTAMP, Index,
)

from app.core.database import Base
from app.core.data_protection import EncryptedText


class UserHealthRiskAssessment(Base):
    """用户健康风险测评记录表"""
    __tablename__ = "user_health_risk_assessment"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        Index("idx_assessment_time", "assessment_time"),
        Index("idx_risk_level", "risk_level"),
        Index("idx_total_score", "total_score"),
        Index("idx_user_assessment", "user_id", "assessment_time"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    user_id = Column(String(64), nullable=False, comment="用户唯一标识")
    user_name = Column(String(100), nullable=False, comment="用户姓名")
    sex = Column(SAEnum("男", "女", "其他"), nullable=False, default="男", comment="性别")
    age = Column(Integer, nullable=False, comment="年龄")

    assessment_time = Column(DateTime, nullable=False, default=datetime.now, comment="测评时间")
    assessment_count = Column(Integer, default=1, comment="第几次测评")
    assessment_type = Column(String(50), default="NRS2002", comment="测评类型")

    # NRS2002 结果
    total_score = Column(Integer, nullable=False, comment="总分0-7")
    nutritional_impairment_score = Column(Integer, nullable=False, comment="营养受损分0-3")
    disease_severity_score = Column(Integer, nullable=False, comment="疾病严重度分0-3")
    age_score = Column(Integer, nullable=False, comment="年龄分0-1")

    assessment_basis = Column(EncryptedText, comment="评分依据说明")
    risk_level = Column(SAEnum("无风险", "低风险", "中风险", "高风险"),
                        nullable=False, comment="风险等级")
    recommendations = Column(EncryptedText, comment="健康建议")
    llm_report = Column(EncryptedText, comment="LLM生成的完整健康报告")

    # 临床信息
    bmi = Column(DECIMAL(4, 2), comment="BMI")
    weight_loss_pct = Column(DECIMAL(5, 2), comment="近3月体重下降%")
    weight_change = Column(String(100), comment="体重变化描述")
    disease_condition = Column(EncryptedText, comment="疾病状况")
    dietary_intake = Column(String(200), comment="进食情况")

    created_at = Column(TIMESTAMP, server_default="CURRENT_TIMESTAMP", comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default="CURRENT_TIMESTAMP",
                        onupdate="CURRENT_TIMESTAMP", comment="更新时间")
    created_by = Column(String(100), default="system", comment="创建人")
