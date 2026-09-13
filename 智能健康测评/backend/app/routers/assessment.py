"""测评相关路由：NRS2002 营养风险筛查"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, resolve_scoped_user_id
from app.schemas.common import ApiResponse
from app.schemas.assessment import AssessmentRequest, AssessmentResponse
from app.services import assessment_service
from app.services.privacy_service import require_health_consent

logger = logging.getLogger("assessment_router")

router = APIRouter(prefix="/api/assessment", tags=["营养风险测评"])


@router.post("", response_model=ApiResponse)
def create_assessment(req: AssessmentRequest, request: Request, db: Session = Depends(get_db)):
    """执行一次 NRS2002 营养风险筛查（规则评分 + LLM 报告）"""
    try:
        payload = req.model_dump()
        payload["user_id"] = require_health_consent(request, db, req.user_id)
        result = assessment_service.run_assessment(
            db,
            payload,
            need_llm_report=req.need_llm_report,
        )
        return ApiResponse(status=200, message="测评完成", data=result)
    except Exception as e:  # noqa: BLE001
        logger.exception("测评失败")
        raise HTTPException(status_code=500, detail=f"测评失败: {e}")


@router.get("/history", response_model=ApiResponse)
def assessment_history(
    request: Request,
    user_id: str = Query("ANON001", description="用户ID"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """某用户的测评历史"""
    owner_id = resolve_scoped_user_id(request, user_id, allow_admin_claim=True)
    rows = assessment_service.get_history(db, owner_id, limit)
    data = []
    for r in rows:
        data.append({
            "record_id": r.id, "user_id": r.user_id, "user_name": r.user_name,
            "age": r.age, "bmi": float(r.bmi) if r.bmi is not None else None,
            "total_score": r.total_score,
            "nutritional_impairment_score": r.nutritional_impairment_score,
            "disease_severity_score": r.disease_severity_score,
            "age_score": r.age_score,
            "risk_level": r.risk_level,
            "assessment_time": r.assessment_time.isoformat() if r.assessment_time else None,
            "assessment_count": r.assessment_count,
            "basis": r.assessment_basis,
            "recommendations": r.recommendations,
            "llm_report": r.llm_report,
            "disease_condition": r.disease_condition,
            "dietary_intake": r.dietary_intake,
        })
    return ApiResponse(status=200, message="success", data=data)


@router.get("/stats", response_model=ApiResponse)
def assessment_stats(db: Session = Depends(get_db)):
    """统计：风险等级分布 / 平均分 / 总人次（供 ECharts 可视化）"""
    from sqlalchemy import func
    from app.models.assessment import UserHealthRiskAssessment as A

    total = db.query(func.count(A.id)).scalar() or 0
    avg_score = db.query(func.avg(A.total_score)).scalar() or 0

    # 风险等级分布
    dist_rows = (
        db.query(A.risk_level, func.count(A.id))
        .group_by(A.risk_level).all()
    )
    dist = {level: 0 for level in ("无风险", "低风险", "中风险", "高风险")}
    for level, cnt in dist_rows:
        dist[level] = cnt

    # 近 14 天每日测评数
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(days=14)
    daily_rows = (
        db.query(func.date(A.assessment_time), func.count(A.id))
        .filter(A.assessment_time >= since)
        .group_by(func.date(A.assessment_time))
        .order_by(func.date(A.assessment_time))
        .all()
    )
    trend = [{"date": str(d), "count": c} for d, c in daily_rows]

    return ApiResponse(status=200, message="success", data={
        "total": total,
        "avg_score": round(float(avg_score), 2),
        "risk_distribution": dist,
        "daily_trend": trend,
    })


@router.get("/detail/{record_id}", response_model=ApiResponse)
def assessment_detail(record_id: int, request: Request, db: Session = Depends(get_db)):
    """测评详情"""
    r = assessment_service.get_assessment_detail(db, record_id)
    if not r:
        raise HTTPException(status_code=404, detail="记录不存在")
    user = get_current_user(request)
    if user.get("role") != "admin" and r.user_id != str(user["id"]):
        # A 404 does not reveal whether another user's health record exists.
        raise HTTPException(status_code=404, detail="记录不存在")
    data = {
        "record_id": r.id, "user_id": r.user_id, "user_name": r.user_name,
        "sex": r.sex, "age": r.age,
        "bmi": float(r.bmi) if r.bmi is not None else None,
        "weight_loss_pct": float(r.weight_loss_pct) if r.weight_loss_pct is not None else None,
        "weight_change": r.weight_change,
        "disease_condition": r.disease_condition,
        "dietary_intake": r.dietary_intake,
        "total_score": r.total_score,
        "nutritional_impairment_score": r.nutritional_impairment_score,
        "disease_severity_score": r.disease_severity_score,
        "age_score": r.age_score,
        "risk_level": r.risk_level,
        "assessment_basis": r.assessment_basis,
        "recommendations": r.recommendations,
        "llm_report": r.llm_report,
        "assessment_time": r.assessment_time.isoformat() if r.assessment_time else None,
        "assessment_count": r.assessment_count,
    }
    return ApiResponse(status=200, message="success", data=data)
