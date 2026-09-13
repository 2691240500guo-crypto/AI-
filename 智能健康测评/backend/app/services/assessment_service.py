"""测评服务：NRS2002 规则评分 → LLM 报告增强 → MySQL 落库"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.assessment import UserHealthRiskAssessment
from app.services.nrs2002_engine import evaluate_nrs2002, NRS2002Result
from app.services.llm_client import get_llm

logger = logging.getLogger("assessment_service")


def _compute_bmi(weight_kg: Optional[float], height_cm: Optional[float],
                 bmi: Optional[float]) -> Optional[float]:
    if bmi is not None:
        return round(float(bmi), 2)
    if weight_kg and height_cm:
        h_m = height_cm / 100
        if h_m > 0:
            return round(weight_kg / (h_m * h_m), 2)
    return None


def _next_count(db: Session, user_id: str) -> int:
    """用户第几次测评"""
    latest = (
        db.query(UserHealthRiskAssessment)
        .filter(UserHealthRiskAssessment.user_id == user_id)
        .order_by(UserHealthRiskAssessment.assessment_time.desc())
        .first()
    )
    return (latest.assessment_count + 1) if latest else 1


def run_assessment(db: Session, req: Dict[str, Any],
                   need_llm_report: bool = True) -> Dict[str, Any]:
    """执行一次完整测评，返回 dict 结果"""
    bmi = _compute_bmi(req.get("weight_kg"), req.get("height_cm"), req.get("bmi"))

    # ---- 1. NRS2002 规则评分 ----
    nrs: NRS2002Result = evaluate_nrs2002(
        bmi=bmi,
        weight_loss_pct=req.get("weight_loss_pct"),
        disease_level=req.get("disease_level", "无"),
        dietary_intake=req.get("dietary_intake", "正常"),
        age=req.get("age"),
    )

    # ---- 2. 组装用户信息，LLM 生成报告 ----
    llm_report = None
    if need_llm_report:
        try:
            user_info = {
                "姓名": req.get("user_name", "匿名用户"),
                "性别": req.get("sex", "男"),
                "年龄": req.get("age"),
                "BMI": bmi,
                "近3月体重下降(%)": req.get("weight_loss_pct"),
                "疾病状况": req.get("disease_condition") or req.get("disease_level", "无"),
                "进食情况": req.get("dietary_intake", "正常"),
            }
            llm_report = get_llm().generate_report(user_info, nrs.to_dict())
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 报告生成失败，使用规则模板: %s", e)
            llm_report = None

    # ---- 3. 落库 ----
    count = _next_count(db, req.get("user_id", "ANON001"))
    record = UserHealthRiskAssessment(
        user_id=req.get("user_id", "ANON001"),
        user_name=req.get("user_name", "匿名用户"),
        sex=req.get("sex", "男"),
        age=req.get("age"),
        assessment_time=datetime.now(),
        assessment_count=count,
        assessment_type="NRS2002",
        total_score=nrs.total_score,
        nutritional_impairment_score=nrs.nutritional_score,
        disease_severity_score=nrs.disease_score,
        age_score=nrs.age_score,
        assessment_basis=nrs.basis,
        risk_level=nrs.risk_level,
        recommendations=nrs.recommendations,
        llm_report=llm_report,
        bmi=bmi,
        weight_loss_pct=req.get("weight_loss_pct"),
        weight_change=req.get("weight_change", ""),
        disease_condition=req.get("disease_condition", ""),
        dietary_intake=req.get("dietary_intake", "正常"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "record_id": record.id,
        "user_id": record.user_id,
        "user_name": record.user_name,
        "age": record.age,
        "bmi": float(record.bmi) if record.bmi is not None else None,
        "total_score": record.total_score,
        "nutritional_impairment_score": record.nutritional_impairment_score,
        "disease_severity_score": record.disease_severity_score,
        "age_score": record.age_score,
        "risk_level": record.risk_level,
        "basis": record.assessment_basis,
        "recommendations": record.recommendations,
        "llm_report": record.llm_report,
        "assessment_time": record.assessment_time,
        "assessment_count": record.assessment_count,
    }


def get_assessment_detail(db: Session, record_id: int):
    return db.query(UserHealthRiskAssessment).filter_by(id=record_id).first()


def get_history(db: Session, user_id: str, limit: int = 50):
    return (
        db.query(UserHealthRiskAssessment)
        .filter_by(user_id=user_id)
        .order_by(UserHealthRiskAssessment.assessment_time.desc())
        .limit(limit)
        .all()
    )
