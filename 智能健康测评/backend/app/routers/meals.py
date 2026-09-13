from datetime import date

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import resolve_user_id
from app.schemas.common import ApiResponse
from app.schemas.meal import MealConfirmRequest, QuickLogRequest
from app.services.meal_service import analyze_image, daily_summary, parse_meal_text, save_meal
from app.services.privacy_service import require_health_consent
from app.utils.redis_cache import delete as redis_delete, get_json, set_json

router = APIRouter(prefix="/api/meals", tags=["饮食记录"])


@router.post("/analyze", response_model=ApiResponse)
async def analyze_meal(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_health_consent(request, db)
    result = analyze_image(await file.read(), file.content_type or "image/jpeg")
    return ApiResponse(data=result)


@router.post("/quick-log", response_model=ApiResponse)
def quick_log_meal(req: QuickLogRequest, request: Request, db: Session = Depends(get_db)):
    """AI 智能问答：把一句话描述转成可确认的饮食草稿（不落库，确认走 /confirm）。"""
    require_health_consent(request, db)
    return ApiResponse(data=parse_meal_text(req.text))


@router.post("/confirm", response_model=ApiResponse)
def confirm_meal(req: MealConfirmRequest, request: Request, db: Session = Depends(get_db)):
    uid = require_health_consent(request, db, req.user_id)
    data = save_meal(db, uid, req.meal_type, req.meal_date,
                     [item.model_dump() for item in req.items], req.note, req.image_url)
    redis_delete(f"meals:daily:{uid}:{req.meal_date.isoformat()}")
    return ApiResponse(data=data)


@router.get("/daily", response_model=ApiResponse)
def get_daily(request: Request, user_id: str = "ANON001", meal_date: date | None = None,
              db: Session = Depends(get_db)):
    uid = resolve_user_id(request, user_id)
    target = meal_date or date.today()
    key = f"meals:daily:{uid}:{target.isoformat()}"
    cached = get_json(key)
    if cached is not None:
        return ApiResponse(data=cached)
    data = daily_summary(db, uid, target)
    set_json(key, data, ttl_seconds=45)
    return ApiResponse(data=data)
