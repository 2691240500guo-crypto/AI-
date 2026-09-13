"""运营总览（管理端 AdminPage 真实数据源）。

聚合各业务域的真实数据，替代前端写死的演示数字：
  - 用户 / 对话 / 测评 / 社区 / 饮食 / 舌象 / 知识库
  - 近 14 天测评趋势、内容审核通过率
  - 最近动态（跨业务域合并，时间倒序）
"""
import logging
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import effective_login_account_count
from app.models.assistant import AssistantConversation, AssistantMessage, UserProfile
from app.models.assessment import UserHealthRiskAssessment
from app.models.auth import AppUser
from app.models.knowledge_file import KnowledgeFile
from app.models.meal import MealRecord
from app.models.social import SocialComment, SocialLike, SocialPost
from app.models.tongue import TongueRecord
from app.schemas.common import ApiResponse
from app.services.plan_service import serialize_plan
from app.utils.redis_cache import get_json, set_json

logger = logging.getLogger("admin_router")

router = APIRouter(prefix="/api/admin", tags=["运营总览"])


class PlanPatchRequest(BaseModel):
    """管理端人工修改饮食计划（不传的字段保持 AI 原样）。"""
    calories_target: int | None = Field(None, ge=800, le=5000)
    set_label: str | None = Field(None, max_length=100)
    recipes: list[dict] | None = None
    shopping_list: list[str] | None = None
    review_note: str | None = Field(None, max_length=1000)


class PlanReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    note: str = ""
    operator: str = "admin"


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@router.get("/overview", response_model=ApiResponse)
def overview(db: Session = Depends(get_db)):
    """管理端运营总览：全部为真实聚合数据。"""
    cached = get_json("admin:overview:v1")
    if cached:
        return ApiResponse(data=cached)
    today_start = datetime.combine(datetime.now().date(), dtime.min)
    since14 = datetime.now() - timedelta(days=14)

    # —— 用户 ——
    user_total = effective_login_account_count(db)
    profile_total = db.query(func.count(UserProfile.user_id)).scalar() or 0

    # —— 对话 ——
    conv_total = db.query(func.count(AssistantConversation.id)).scalar() or 0
    msg_total = db.query(func.count(AssistantMessage.id)).scalar() or 0
    msg_today = (
        db.query(func.count(AssistantMessage.id))
        .filter(AssistantMessage.created_at >= today_start,
                AssistantMessage.role == "user")
        .scalar() or 0
    )

    # —— 测评 ——
    assess_total = db.query(func.count(UserHealthRiskAssessment.id)).scalar() or 0
    avg_score = db.query(func.avg(UserHealthRiskAssessment.total_score)).scalar() or 0
    dist_rows = (
        db.query(UserHealthRiskAssessment.risk_level, func.count(UserHealthRiskAssessment.id))
        .group_by(UserHealthRiskAssessment.risk_level).all()
    )
    risk_dist = {level: 0 for level in ("无风险", "低风险", "中风险", "高风险")}
    for level, cnt in dist_rows:
        risk_dist[level] = cnt
    trend_rows = (
        db.query(func.date(UserHealthRiskAssessment.assessment_time), func.count(UserHealthRiskAssessment.id))
        .filter(UserHealthRiskAssessment.assessment_time >= since14)
        .group_by(func.date(UserHealthRiskAssessment.assessment_time))
        .order_by(func.date(UserHealthRiskAssessment.assessment_time))
        .all()
    )
    daily_trend = [{"date": str(d), "count": c} for d, c in trend_rows]

    # —— 社区 ——
    post_total = db.query(func.count(SocialPost.id)).scalar() or 0
    post_published = db.query(func.count(SocialPost.id)).filter(SocialPost.status == "published").scalar() or 0
    post_pending = db.query(func.count(SocialPost.id)).filter(SocialPost.status == "pending_review").scalar() or 0
    post_rejected = db.query(func.count(SocialPost.id)).filter(SocialPost.status == "rejected").scalar() or 0
    comment_total = db.query(func.count(SocialComment.id)).scalar() or 0
    like_total = db.query(func.count(SocialLike.id)).scalar() or 0
    pass_rate = round(post_published / post_total * 100, 1) if post_total else 100.0

    # —— 饮食 / 舌象 ——
    meal_total = db.query(func.count(MealRecord.id)).scalar() or 0
    tongue_total = db.query(func.count(TongueRecord.id)).scalar() or 0

    # —— 知识库 ——
    kb_files = db.query(func.count(KnowledgeFile.id)).scalar() or 0
    kb_chunks = db.query(func.coalesce(func.sum(KnowledgeFile.chunk_count), 0)).scalar() or 0

    # —— 最近动态（跨域合并，时间倒序取 8 条）——
    activities: list[dict] = []
    for r in db.query(UserHealthRiskAssessment).order_by(desc(UserHealthRiskAssessment.assessment_time)).limit(4).all():
        activities.append({
            "type": "assessment", "name": r.user_name,
            "action": f"完成营养测评 · {r.risk_level}（{r.total_score}分）",
            "time": _fmt(r.assessment_time),
        })
    for p in db.query(SocialPost).order_by(desc(SocialPost.created_at)).limit(4).all():
        status_text = {"published": "发布了一条动态", "pending_review": "发布内容待审核", "rejected": "内容被驳回"}.get(p.status, "发布内容")
        activities.append({
            "type": "social", "name": p.user_name, "action": status_text,
            "time": _fmt(p.created_at),
        })
    for m in db.query(MealRecord).order_by(desc(MealRecord.created_at)).limit(3).all():
        activities.append({
            "type": "meal", "name": m.user_id,
            "action": f"记录{ m.meal_type } · {round(m.calories or 0)} kcal",
            "time": _fmt(m.created_at),
        })
    for t in db.query(TongueRecord).order_by(desc(TongueRecord.created_at)).limit(2).all():
        activities.append({
            "type": "tongue", "name": t.user_id,
            "action": f"保存舌象观察 · {t.tongue_color or '未明确'}",
            "time": _fmt(t.created_at),
        })
    activities = [a for a in activities if a["time"]]
    activities.sort(key=lambda a: a["time"], reverse=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "users": {"accounts": user_total, "profiles": profile_total},
        "conversation": {"conversations": conv_total, "messages": msg_total, "messages_today": msg_today},
        "assessment": {"total": assess_total, "avg_score": round(float(avg_score), 2),
                       "risk_distribution": risk_dist, "daily_trend": daily_trend},
        "community": {"posts": post_total, "published": post_published, "pending": post_pending,
                      "rejected": post_rejected, "comments": comment_total, "likes": like_total,
                      "pass_rate": pass_rate},
        "meals": {"total": meal_total},
        "tongue": {"total": tongue_total},
        "knowledge": {"files": kb_files, "chunks": int(kb_chunks)},
        "activities": activities[:8],
    }
    set_json("admin:overview:v1", payload, ttl_seconds=15)
    return ApiResponse(data=payload)


@router.get("/tongue/evaluation", response_model=ApiResponse)
def tongue_evaluation(split: str = "test"):
    """Run the reproducible tongue localization acceptance evaluation."""
    from app.services.tongue_evaluation import evaluate_tongue_dataset

    backend_root = Path(__file__).resolve().parents[2]
    data_root = backend_root / "data" / "tongue_dataset"
    model_path = backend_root / "models" / "tongue" / "yolov8n-tongue.pt"
    if not data_root.exists() or not model_path.exists():
        raise HTTPException(status_code=503, detail="舌象验收数据集或模型文件不存在")
    return ApiResponse(data=evaluate_tongue_dataset(data_root, model_path, split=split))


# ---------------------------------------------------------------
# 饮食计划人工审核：列表 / 修改 / 通过 / 驳回
# 管理员不修改内容直接通过时，用户端沿用 AI 生成的版本（source 保持 ai）
# ---------------------------------------------------------------
@router.get("/plans", response_model=ApiResponse)
def plan_queue(status: str = "pending_review", limit: int = 50, db: Session = Depends(get_db)):
    """计划审核队列（默认待审核），附带用户画像摘要。"""
    from app.models.plan import MealPlan

    query = db.query(MealPlan)
    if status and status != "all":
        query = query.filter(MealPlan.status == status)
    rows = query.order_by(desc(MealPlan.updated_at)).limit(min(limit, 200)).all()

    profiles = {p.user_id: p for p in db.query(UserProfile).all()}
    data = []
    for r in rows:
        item = serialize_plan(r)
        p = profiles.get(r.user_id)
        item["profile"] = ({
            "user_name": p.user_name, "sex": p.sex, "age": p.age,
            "height_cm": p.height_cm, "weight_kg": p.weight_kg, "goal": p.goal,
        } if p else None)
        data.append(item)
    return ApiResponse(data=data)


@router.patch("/plans/{plan_id}", response_model=ApiResponse)
def plan_update(plan_id: int, req: PlanPatchRequest, db: Session = Depends(get_db)):
    """人工修改计划内容；只要动过内容字段就标记为 manual（营养师已调整）。"""
    from app.models.plan import MealPlan

    record = db.query(MealPlan).filter_by(id=plan_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    changed = False
    if req.calories_target is not None:
        record.calories_target = req.calories_target
        changed = True
    if req.set_label is not None:
        record.set_label = req.set_label
        changed = True
    if req.recipes is not None:
        record.recipes = req.recipes
        changed = True
    if req.shopping_list is not None:
        record.shopping_list = req.shopping_list
        changed = True
    if req.review_note is not None:
        record.review_note = req.review_note
    if changed:
        record.source = "manual"

    db.commit()
    db.refresh(record)
    return ApiResponse(message="已保存人工调整" if changed else "已保存备注", data=serialize_plan(record))


@router.post("/plans/{plan_id}/review", response_model=ApiResponse)
def plan_review(plan_id: int, req: PlanReviewRequest, db: Session = Depends(get_db)):
    """通过 / 驳回。通过后用户端展示该版本（未修改则即 AI 原版）。"""
    from app.models.plan import MealPlan

    record = db.query(MealPlan).filter_by(id=plan_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="计划不存在")

    record.status = "approved" if req.action == "approve" else "rejected"
    if req.note:
        record.review_note = req.note
    record.reviewed_by = req.operator
    record.reviewed_at = datetime.now()
    db.commit()
    db.refresh(record)
    message = "已通过，用户端将展示该计划" if record.status == "approved" else "已驳回，用户端将提示重新生成"
    return ApiResponse(message=message, data=serialize_plan(record))


# ---------------------------------------------------------------
# 运营总览明细：统计卡点击后拉起弹窗的数据源
# kind = users（活跃用户）/ conversations（AI 会话）/ posts（待审内容）
#        / assessments（累计测评）/ meals / tongue / knowledge
# ---------------------------------------------------------------
@router.get("/details", response_model=ApiResponse)
def details(kind: str, limit: int = 20, db: Session = Depends(get_db)):
    """按业务域返回明细列表，供运营总览卡片点击查看。"""
    limit = max(1, min(limit, 100))
    rows: list[dict] = []
    title = ""

    if kind == "users":
        title = "活跃用户明细"
        for p in db.query(UserProfile).order_by(desc(UserProfile.updated_at)).limit(limit).all():
            conv = db.query(func.count(AssistantConversation.id)).filter(
                AssistantConversation.user_id == p.user_id).scalar() or 0
            assess = db.query(func.count(UserHealthRiskAssessment.id)).filter(
                UserHealthRiskAssessment.user_id == p.user_id).scalar() or 0
            rows.append({
                "主键": p.user_id, "姓名": p.user_name,
                "性别": p.sex or "-", "年龄": p.age or "-",
                "目标": p.goal or "-",
                "AI会话": conv, "测评次数": assess,
                "更新于": _fmt(p.updated_at),
            })

    elif kind == "conversations":
        title = "AI 会话明细（含今日）"
        today = datetime.now().date()
        q = db.query(AssistantConversation).order_by(desc(AssistantConversation.updated_at))
        all_convs = q.limit(200).all()
        today_convs = [c for c in all_convs if c.updated_at and c.updated_at.date() == today]
        picked = (today_convs or all_convs)[:limit]
        for c in picked:
            msg = db.query(func.count(AssistantMessage.id)).filter(
                AssistantMessage.conversation_id == c.id).scalar() or 0
            rows.append({
                "会话ID": c.id, "用户": c.user_id, "标题": c.title,
                "消息数": msg, "是否今日": "是" if c.updated_at and c.updated_at.date() == today else "否",
                "更新时间": _fmt(c.updated_at),
            })

    elif kind == "posts":
        title = "内容明细（待审优先）"
        q = db.query(SocialPost).order_by(
            func.field(SocialPost.status, "pending_review", "published", "rejected"),
            desc(SocialPost.created_at),
        )
        for p in q.limit(limit).all():
            rows.append({
                "帖子ID": p.id, "作者": p.user_name,
                "内容": (p.content or "")[:40] + ("…" if len(p.content or "") > 40 else ""),
                "状态": {"published": "已发布", "pending_review": "待审核", "rejected": "已驳回"}.get(p.status, p.status),
                "图片数": len(p.images or []),
                "点赞": p.likes_count, "评论": p.comments_count,
                "发布时间": _fmt(p.created_at),
            })

    elif kind == "assessments":
        title = "测评记录明细（按风险等级排序）"
        for r in db.query(UserHealthRiskAssessment).order_by(
                desc(UserHealthRiskAssessment.total_score),
                desc(UserHealthRiskAssessment.assessment_time)).limit(limit).all():
            rows.append({
                "记录ID": r.id, "用户": r.user_name, "年龄": r.age,
                "总分": f"{r.total_score} / 7", "等级": r.risk_level,
                "营养/疾病/年龄分": f"{r.nutritional_impairment_score} + "
                                   f"{r.disease_severity_score} + {r.age_score}",
                "测评时间": _fmt(r.assessment_time),
            })

    elif kind == "meals":
        title = "饮食记录明细"
        for m in db.query(MealRecord).order_by(desc(MealRecord.created_at)).limit(limit).all():
            items = m.items or []
            names = "、".join([str(i.get("name") or i.get("food") or "未命名")
                               for i in items if isinstance(i, dict)]) or (m.note or "-")
            rows.append({
                "记录ID": m.id, "用户": m.user_id,
                "餐次": m.meal_type, "日期": str(m.meal_date or "-"),
                "食物": names[:40],
                "热量": f"{round(m.calories or 0)} kcal",
                "蛋白/脂肪/碳水": f"{round(m.protein_g or 0)}/{round(m.fat_g or 0)}/{round(m.carbs_g or 0)} g",
                "时间": _fmt(m.created_at),
            })

    elif kind == "tongue":
        title = "舌象记录明细"
        for t in db.query(TongueRecord).order_by(desc(TongueRecord.created_at)).limit(limit).all():
            rows.append({
                "记录ID": t.id, "用户": t.user_id,
                "舌色": t.tongue_color or "未明确", "状态": t.status or "-",
                "时间": _fmt(t.created_at),
            })

    elif kind == "knowledge":
        title = "知识库文件明细"
        for f in db.query(KnowledgeFile).order_by(desc(KnowledgeFile.upload_time)).limit(limit).all():
            rows.append({
                "文件": f.file_name, "类型": f.file_type,
                "大小": f"{round((f.file_size or 0) / 1024, 1)} KB",
                "状态": f.status, "向量块": f.chunk_count,
                "入库时间": _fmt(f.upload_time),
            })

    else:
        raise HTTPException(status_code=400, detail=f"不支持的明细类型：{kind}")

    columns = list(rows[0].keys()) if rows else []
    return ApiResponse(data={"kind": kind, "title": title,
                             "columns": columns, "rows": rows,
                             "total": len(rows)})
