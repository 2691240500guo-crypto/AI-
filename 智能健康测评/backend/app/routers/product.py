import base64
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import DEMO_ACCOUNTS, create_access_token, resolve_user_id, verify_password
from app.models.auth import AppUser
from app.models.social import SocialComment, SocialLike, SocialPost, SocialFollow
from app.schemas.common import ApiResponse
from app.services.moderation_service import moderate_images_batch, moderate_text
from app.services.tongue_service import analyze_tongue, save_tongue_record, serialize_tongue
from app.services.privacy_service import require_health_consent
from app.utils.redis_cache import delete as redis_delete

router = APIRouter(prefix="/api", tags=["HealthyBot 产品能力"])
logger = logging.getLogger("product_router")

# 社区图床桶（公开读，供 feed <img> 直接展示）
POST_IMAGES_BUCKET = "health-posts"
POST_IMAGES_LIMIT = 9
POST_IMAGE_MAX_MB = 5


class LoginRequest(BaseModel):
    account: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    role: str = Field("user", pattern="^(user|admin)$")


class PostRequest(BaseModel):
    user_id: str = "ANON001"
    user_name: str = "匿名用户"
    content: str = Field(..., min_length=1, max_length=2000)
    images: list[str] = Field(default_factory=list, max_length=9)
    tags: list[str] = Field(default_factory=list, max_length=10)


class CommentRequest(BaseModel):
    user_id: str = "ANON001"
    user_name: str = "匿名用户"
    content: str = Field(..., min_length=1, max_length=500)


class PlanRequest(BaseModel):
    user_id: str = "ANON001"
    goal: str = "保持健康"
    days: int = Field(7, ge=1, le=14)
    # 重新生成时递增，用于在同一档位内轮换菜单（0/1/2…）
    variant: int = Field(0, ge=0, le=99)


class ReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    operator: str = "admin"


# 社区机审：文本红线词与图片视觉审核统一由 moderation_service 提供
# （文本命中 → 帖子转 pending_review；图片明确违规 → 上传即拦截）


@router.post("/auth/login", response_model=ApiResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """登录并签发 JWT。演示账号：user/user123、admin/admin123；也支持库内账号。"""
    expected = DEMO_ACCOUNTS[req.role]
    account = db.query(AppUser).filter_by(account=req.account, role=req.role).first()
    if account:
        valid = verify_password(req.password, account.password)
    else:
        valid = (req.account == req.role and req.password == expected["password"])
    if not valid:
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    name = account.name if account else expected["name"]
    token, expires_in = create_access_token(req.account, req.role, name)
    return ApiResponse(data={
        "token": token, "token_type": "bearer", "expires_in": expires_in,
        "role": req.role, "user": {"id": req.account, "name": name},
    })


def serialize_post(post: SocialPost, liked: bool = False, following: bool = False):
    return {"id": post.id, "user_id": post.user_id, "user_name": post.user_name, "content": post.content,
            "images": post.images or [], "tags": post.tags or [], "likes": post.likes_count or 0,
            "comments": post.comments_count or 0, "liked": liked, "following": following, "status": post.status,
            "created_at": post.created_at.isoformat() if post.created_at else None}


@router.get("/social/feed", response_model=ApiResponse)
def social_feed(request: Request, user_id: str = "ANON001", scope: str = "all", limit: int = 20,
                db: Session = Depends(get_db)):
    """Published posts for discovery or the authenticated user's following feed."""
    uid = resolve_user_id(request, user_id)
    if scope not in {"all", "following"}:
        raise HTTPException(status_code=400, detail="scope 仅支持 all 或 following")
    query = db.query(SocialPost).filter_by(status="published")
    if scope == "following":
        following_ids = [row.following_id for row in db.query(SocialFollow.following_id)
                         .filter_by(follower_id=uid).all()]
        if not following_ids:
            return ApiResponse(data=[])
        query = query.filter(SocialPost.user_id.in_(following_ids))
    posts = query.order_by(desc(SocialPost.created_at)).limit(min(limit, 100)).all()
    liked_ids = {x.post_id for x in db.query(SocialLike).filter_by(user_id=uid).all()}
    following_ids = {x.following_id for x in db.query(SocialFollow).filter_by(follower_id=uid).all()}
    return ApiResponse(data=[serialize_post(p, p.id in liked_ids, p.user_id in following_ids) for p in posts])


@router.post("/social/posts", response_model=ApiResponse)
def create_post(req: PostRequest, request: Request, db: Session = Depends(get_db)):
    # 机审：正文 + 话题标签一起过红线词库
    checked_text = f"{req.content} {' '.join(req.tags)}"
    hit = moderate_text(checked_text)
    status = "pending_review" if hit else "published"
    payload = req.model_dump()
    payload["user_id"] = resolve_user_id(request, req.user_id)   # 归属以登录身份为准
    post = SocialPost(**payload, status=status)
    db.add(post)
    db.commit()
    db.refresh(post)
    redis_delete("admin:overview:v1")
    message = (
        f"内容含疑似违规表述（“{hit}”），已进入人工复核，通过后将自动展示。"
        if hit
        else "发布成功"
    )
    return ApiResponse(message=message, data=serialize_post(post))


@router.post("/social/upload", response_model=ApiResponse)
async def social_upload(request: Request, files: list[UploadFile] = File(...), user_id: str = Form("ANON001")):
    """社区图片上传：多图（≤9 张、单张 ≤5MB）。

    流程：格式/大小校验 → **图片机审（明确违规整批拦截）** → 存入 MinIO 公开读桶 → 返回直链。
    """
    owner = resolve_user_id(request, user_id)
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的图片")
    if len(files) > POST_IMAGES_LIMIT:
        raise HTTPException(status_code=400, detail=f"最多上传 {POST_IMAGES_LIMIT} 张图片")

    allowed_ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                   "image/gif": ".gif", "image/bmp": ".bmp"}

    # 阶段一：读取 + 校验 + 机审（全部通过才上传，避免半途拦截留下孤儿文件）
    staged: list[tuple[bytes, str, str]] = []
    for f in files:
        mime = f.content_type or "image/jpeg"
        ext = allowed_ext.get(mime)
        if not ext:
            raise HTTPException(status_code=400, detail=f"不支持的图片类型: {mime}（仅支持 jpg/png/webp/gif/bmp）")
        data = await f.read()
        if not data:
            continue
        if len(data) > POST_IMAGE_MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename or '图片'} 超过 {POST_IMAGE_MAX_MB}MB")
        staged.append((data, mime, ext))
    if not staged:
        raise HTTPException(status_code=400, detail="未接收到有效图片")

    passed, verdict = moderate_images_batch([(data, mime) for data, mime, _ in staged])
    if not passed:
        labels = "、".join(verdict.get("category_labels") or ["疑似违规"])
        reason = verdict.get("reason") or "疑似违反社区内容红线"
        raise HTTPException(
            status_code=400,
            detail=f"图片未通过机审（{labels}）：{reason}。已拦截，如有异议可联系管理员人工复核。",
        )

    # 阶段二：机审通过后统一上传
    from app.utils.minio_client import get_minio
    import uuid

    urls: list[str] = []
    for data, mime, ext in staged:
        object_name = f"posts/{owner}/{uuid.uuid4().hex}{ext}"
        urls.append(get_minio().upload_public_bytes(POST_IMAGES_BUCKET, object_name, data, mime))
    return ApiResponse(message="图片机审通过", data={"urls": urls, "moderation": {"checked": True, "count": len(urls)}})


@router.get("/social/posts/{post_id}/comments", response_model=ApiResponse)
def list_comments(post_id: int, db: Session = Depends(get_db)):
    """某帖子的评论列表（正序展示）。"""
    rows = (
        db.query(SocialComment)
        .filter_by(post_id=post_id)
        .order_by(SocialComment.created_at)
        .limit(200)
        .all()
    )
    return ApiResponse(data=[{
        "id": c.id, "post_id": c.post_id, "user_id": c.user_id,
        "user_name": c.user_name, "content": c.content,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in rows])


@router.post("/social/posts/{post_id}/like", response_model=ApiResponse)
def like_post(post_id: int, request: Request, user_id: str = "ANON001", db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)
    post = db.query(SocialPost).filter_by(id=post_id, status="published").first()
    if not post: raise HTTPException(status_code=404, detail="帖子不存在")
    like = db.query(SocialLike).filter_by(post_id=post_id, user_id=uid).first()
    if like:
        db.delete(like); post.likes_count = max(0, (post.likes_count or 0) - 1); liked = False
    else:
        db.add(SocialLike(post_id=post_id, user_id=uid)); post.likes_count = (post.likes_count or 0) + 1; liked = True
    db.commit()
    return ApiResponse(data={"post_id": post_id, "liked": liked, "likes": post.likes_count})


@router.post("/social/posts/{post_id}/comments", response_model=ApiResponse)
def comment_post(post_id: int, req: CommentRequest, request: Request, db: Session = Depends(get_db)):
    post = db.query(SocialPost).filter_by(id=post_id, status="published").first()
    if not post: raise HTTPException(status_code=404, detail="帖子不存在")
    payload = req.model_dump()
    payload["user_id"] = resolve_user_id(request, req.user_id)
    comment = SocialComment(post_id=post_id, **payload)
    db.add(comment); post.comments_count = (post.comments_count or 0) + 1; db.commit(); db.refresh(comment)
    return ApiResponse(data={"id": comment.id, "content": comment.content, "user_name": comment.user_name, "created_at": comment.created_at.isoformat()})

@router.post("/social/users/{target_id}/follow", response_model=ApiResponse)
def follow_user(target_id: str, request: Request, user_id: str = "ANON001", db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)
    if target_id == uid:
        raise HTTPException(status_code=400, detail="不能关注自己")
    follow = db.query(SocialFollow).filter_by(follower_id=uid, following_id=target_id).first()
    if follow:
        db.delete(follow); following = False
    else:
        db.add(SocialFollow(follower_id=uid, following_id=target_id)); following = True
    db.commit()
    return ApiResponse(data={"target_id": target_id, "following": following})


# ---------------------------------------------------------------
# 内容审核（管理端）：待审队列 / 通过 / 驳回
# 仅 published 会出现在 feed，pending_review / rejected 均不可见
# ---------------------------------------------------------------
@router.get("/social/moderation/queue", response_model=ApiResponse)
def moderation_queue(status: str = "pending_review", limit: int = 50, db: Session = Depends(get_db)):
    rows = (
        db.query(SocialPost)
        .filter(SocialPost.status == status)
        .order_by(desc(SocialPost.created_at))
        .limit(min(limit, 200))
        .all()
    )
    return ApiResponse(data=[serialize_post(p) for p in rows])


@router.post("/social/moderation/{post_id}/review", response_model=ApiResponse)
def moderation_review(post_id: int, req: ReviewRequest, db: Session = Depends(get_db)):
    post = db.query(SocialPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.status == "published":
        raise HTTPException(status_code=400, detail="该内容已发布，无需重复审核")
    post.status = "published" if req.action == "approve" else "rejected"
    db.commit()
    db.refresh(post)
    redis_delete("admin:overview:v1")
    action_text = "已通过并对外展示" if post.status == "published" else "已驳回（不对外展示）"
    return ApiResponse(message=action_text, data=serialize_post(post))


# ---------------------------------------------------------------
# 饮食计划生成：实现已下沉到 plan_service（对话内 AI 生成与 REST 复用同一逻辑）
# 生成即落库为「待审核」版本，管理端可人工审核/修改，未修改则沿用 AI 版本
# ---------------------------------------------------------------
from app.services.plan_service import get_current_plan, upsert_plan


@router.post("/plans/generate", response_model=ApiResponse)
def generate_plan(req: PlanRequest, request: Request, db: Session = Depends(get_db)):
    """个性化饮食计划：结合健康画像(性别/年龄/身高/体重/目标)与近 7 天饮食记录生成。"""
    uid = require_health_consent(request, db, req.user_id)
    return ApiResponse(message="已生成计划，等待营养师审核",
                       data=upsert_plan(db, uid, req.goal, req.days, req.variant))


@router.get("/plans/current", response_model=ApiResponse)
def current_plan(request: Request, user_id: str = "ANON001", db: Session = Depends(get_db)):
    """用户当前计划（含审核状态 / 营养师备注）；没有则 data 为 null。"""
    return ApiResponse(data=get_current_plan(db, resolve_user_id(request, user_id)))


@router.post("/voice/transcribe", response_model=ApiResponse)
async def transcribe_voice(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_health_consent(request, db)
    audio = await file.read()
    try:
        from app.services.llm_client import get_llm
        text = get_llm().transcribe_audio(audio, file.filename or "voice.webm", file.content_type or "audio/webm")
        return ApiResponse(data={"text": text, "source": "siliconflow"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("ASR unavailable: %s", exc)
        return ApiResponse(data={"text": "语音已收到，请确认后再发送。", "source": "fallback", "pending": True,
                                 "model": settings.ASR_MODEL, "fallback_reason": str(exc)[:240]})


@router.post("/voice/speak", response_model=ApiResponse)
def speak_text(request: Request, text: str = Form(...), db: Session = Depends(get_db)):
    require_health_consent(request, db)
    try:
        from app.services.llm_client import get_llm
        audio = get_llm().synthesize_speech(text)
        return ApiResponse(data={"audio_base64": base64.b64encode(audio).decode(), "mime": "audio/mpeg"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("TTS unavailable: %s", exc)
        return ApiResponse(data={"audio_base64": None, "mime": "audio/mpeg", "pending": True,
                                 "model": settings.TTS_MODEL, "fallback_reason": str(exc)[:240]})


@router.get("/voice/capabilities", response_model=ApiResponse)
def voice_capabilities():
    return ApiResponse(data={
        "asr_model": settings.ASR_MODEL,
        "tts_model": settings.TTS_MODEL,
        "asr_endpoint": settings.SILICONFLOW_ASR_URL or f"{settings.siliconflow_base_url}/audio/transcriptions",
        "tts_endpoint": settings.SILICONFLOW_TTS_URL or f"{settings.siliconflow_base_url}/audio/speech",
        "fallback_enabled": True,
    })


@router.post("/tongue/analyze", response_model=ApiResponse)
async def tongue_analyze(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_health_consent(request, db)
    image = await file.read()
    if not image:
        raise HTTPException(status_code=400, detail="舌象图片不能为空")
    try:
        return ApiResponse(data=analyze_tongue(image, file.content_type or "image/jpeg"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("tongue analysis failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"舌体图片解析失败: {exc}")


@router.post("/tongue/save", response_model=ApiResponse)
async def tongue_save(request: Request, file: UploadFile = File(...), user_id: str = Form("ANON001"),
                      note: str = Form(""), db: Session = Depends(get_db)):
    """分析舌象并保存为历史记录（原图存 MinIO，供历史趋势回显）。"""
    owner = require_health_consent(request, db, user_id)
    image = await file.read()
    if not image:
        raise HTTPException(status_code=400, detail="舌象图片不能为空")
    try:
        record = save_tongue_record(db=db, user_id=owner, image_bytes=image,
                                    mime=file.content_type or "image/jpeg", note=note)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tongue save failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"舌象保存失败: {exc}")
    if record is None:
        return ApiResponse(status=200, message="未检出清晰舌体，本次不保存", data=None)
    return ApiResponse(status=200, message="已保存到舌象记录", data=record)


@router.get("/tongue/records", response_model=ApiResponse)
def tongue_records(request: Request, user_id: str = "ANON001", limit: int = 60, db: Session = Depends(get_db)):
    """我的舌象历史记录（时间倒序），供趋势对比。"""
    from app.models.tongue import TongueRecord

    rows = (
        db.query(TongueRecord)
        .filter_by(user_id=resolve_user_id(request, user_id))
        .order_by(desc(TongueRecord.created_at))
        .limit(min(limit, 200))
        .all()
    )
    return ApiResponse(data=[serialize_tongue(r) for r in rows])


@router.get("/tongue/images/{record_id}")
def tongue_image(record_id: int, request: Request, db: Session = Depends(get_db)):
    """Authenticated image gateway: decrypts the private MinIO blob on demand."""
    from app.models.tongue import TongueRecord
    from app.utils.minio_client import get_minio

    owner = resolve_user_id(request, "ANON001")
    row = db.query(TongueRecord).filter_by(id=record_id, user_id=owner).first()
    if not row or not row.image_object_name:
        raise HTTPException(status_code=404, detail="舌象图片不存在")
    data = get_minio().download_private_encrypted_bytes(row.image_bucket or "health-tongue", row.image_object_name)
    if not data:
        raise HTTPException(status_code=404, detail="舌象图片暂不可用")
    return Response(content=data, media_type=row.image_mime or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=300"})
