"""知识库相关路由：文件上传入库 / 列表 / 删除 / 向量检索"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.knowledge import SearchRequest, SearchHit
from app.services import knowledge_service
from app.utils.milvus_client import get_milvus
from app.utils.minio_client import get_minio

logger = logging.getLogger("knowledge_router")

router = APIRouter(prefix="/api/knowledge", tags=["多模态知识库"])


@router.post("/upload", response_model=ApiResponse)
async def upload_file(
    file: UploadFile = File(...),
    uploaded_by: str = Form("system"),
    db: Session = Depends(get_db),
):
    """上传知识文档/图片：MinIO 存储 + 多模态解析 + Milvus 向量化 + MySQL 元数据"""
    filename = file.filename or "unnamed"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")

    try:
        result = knowledge_service.upload_and_index(db, filename, data, uploaded_by)
    except Exception as e:  # noqa: BLE001
        logger.exception("上传失败 %s", filename)
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "上传失败"))
    return ApiResponse(status=200, message="入库成功", data=result)


@router.get("/files", response_model=ApiResponse)
def list_knowledge_files(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """知识库文件列表"""
    files = knowledge_service.list_files(db, limit, offset)
    data = []
    for f in files:
        data.append({
            "id": f.id, "file_name": f.file_name, "file_type": f.file_type,
            "file_ext": f.file_ext, "file_size": f.file_size,
            "status": f.status, "chunk_count": f.chunk_count,
            "content_summary": f.content_summary,
            "parse_message": f.parse_message,
            "upload_time": f.upload_time.isoformat() if f.upload_time else None,
        })
    return ApiResponse(status=200, message="success", data=data)


@router.delete("/files/{file_id}", response_model=ApiResponse)
def delete_knowledge_file(file_id: int, db: Session = Depends(get_db)):
    """删除知识库文件（含 MinIO 对象与 Milvus 向量）"""
    ok = knowledge_service.delete_file(db, file_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文件不存在")
    return ApiResponse(status=200, message="已删除", data={"file_id": file_id})


@router.get("/files/{file_id}/url", response_model=ApiResponse)
def file_url(file_id: int, db: Session = Depends(get_db)):
    """获取文件临时访问 URL（需登录场景用 presigned url）"""
    f = knowledge_service.get_file(db, file_id)
    if not f or not f.object_name:
        raise HTTPException(status_code=404, detail="文件不存在")
    url = get_minio().presigned_url(f.object_name)
    return ApiResponse(status=200, message="success", data={"url": url})


@router.post("/search", response_model=ApiResponse)
def search_knowledge(req: SearchRequest):
    """基于 Milvus 的向量语义检索"""
    hits = get_milvus().search(req.query, top_k=req.top_k, file_id=req.file_id)
    return ApiResponse(
        status=200, message="success",
        data=[SearchHit(**h) for h in hits],
    )


@router.get("/stats", response_model=ApiResponse)
def knowledge_stats(db: Session = Depends(get_db)):
    """知识库统计（供可视化）"""
    files = knowledge_service.list_files(db, 1000, 0)
    by_type = {}
    by_status = {}
    total_chunks = 0
    for f in files:
        by_type[f.file_type or "other"] = by_type.get(f.file_type or "other", 0) + 1
        by_status[f.status] = by_status.get(f.status, 0) + 1
        total_chunks += f.chunk_count or 0
    return ApiResponse(status=200, message="success", data={
        "total_files": len(files),
        "total_chunks": total_chunks,
        "by_type": by_type,
        "by_status": by_status,
    })
