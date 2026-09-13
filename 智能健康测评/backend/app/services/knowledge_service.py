"""知识库服务：文件上传 → MinIO → 多模态解析 → Milvus 向量化 → 元数据落库"""
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.knowledge_file import KnowledgeFile
from app.services.document_parser import (
    parse_bytes, guess_type, IMAGE_EXTS,
)
from app.utils.minio_client import get_minio
from app.utils.milvus_client import get_milvus

logger = logging.getLogger("knowledge_service")

# 常见类型 mime（用于上传时判定）
import mimetypes  # noqa: E402


def upload_and_index(db: Session, filename: str, data: bytes,
                     uploaded_by: str = "system") -> dict:
    """完整入库链路：
    1. 存 MinIO（原件）
    2. 多模态解析（文本直读 / pdf/docx 抽取 / 图片 OCR）
    3. 文本分块 → 向量化 → Milvus
    4. 元数据 + 状态写入 MySQL
    """
    ext = os.path.splitext(filename)[1].lower()
    ftype = guess_type(ext)
    object_name = f"{datetime.now():%Y%m%d}/{uuid.uuid4().hex}{ext}"

    # ---- 1. 存 MinIO ----
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        get_minio().upload_bytes(object_name, data, mime)
    except Exception as e:  # noqa: BLE001
        logger.exception("MinIO 上传失败")
        return {"ok": False, "error": f"MinIO 上传失败: {e}"}

    # ---- 2. 新建记录（pending）----
    record = KnowledgeFile(
        file_name=filename,
        file_type=ftype,
        file_ext=ext.lstrip("."),
        file_size=len(data),
        object_name=object_name,
        bucket=get_minio().bucket,
        status="parsing",
        uploaded_by=uploaded_by,
        upload_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # ---- 3. 多模态解析 ----
    content, parse_msg, chunks = parse_bytes(filename, data)

    if not chunks:
        record.status = "failed"
        record.parse_message = parse_msg or "解析无内容"
        db.commit()
        return {"ok": False, "file_id": record.id,
                "error": record.parse_message, "record": record}

    # ---- 4. Milvus 向量化 ----
    chunk_count = 0
    try:
        chunk_count = get_milvus().add_chunks(
            file_id=record.id, source=filename, chunks=chunks
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Milvus 向量化失败")
        record.status = "failed"
        record.parse_message = f"向量化失败: {e}（已解析 {len(content)} 字但未入库向量）"
        db.commit()
        return {"ok": False, "file_id": record.id,
                "error": record.parse_message, "record": record}

    # ---- 5. 更新状态 ----
    record.content_text = content[:50000]  # 摘要存储全文前 5 万字
    record.content_summary = content[:300] + ("..." if len(content) > 300 else "")
    record.chunk_count = chunk_count
    record.status = "done"
    record.parse_message = f"解析成功，共 {len(content)} 字，向量化 {chunk_count} 块"
    db.commit()
    db.refresh(record)

    return {
        "ok": True,
        "file_id": record.id,
        "file_name": record.file_name,
        "file_type": record.file_type,
        "status": record.status,
        "chunk_count": record.chunk_count,
        "content_summary": record.content_summary,
        "parse_message": record.parse_message,
    }


def delete_file(db: Session, file_id: int) -> bool:
    """删除知识库文件：MySQL 记录 + MinIO 对象 + Milvus 向量"""
    record = db.query(KnowledgeFile).filter_by(id=file_id).first()
    if not record:
        return False
    try:
        if record.object_name:
            get_minio().remove(record.object_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("MinIO 删除失败: %s", e)
    try:
        get_milvus().delete_by_file(file_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Milvus 删除失败: %s", e)
    db.delete(record)
    db.commit()
    return True


def list_files(db: Session, limit: int = 100, offset: int = 0) -> list:
    return (
        db.query(KnowledgeFile)
        .order_by(KnowledgeFile.upload_time.desc())
        .offset(offset).limit(limit)
        .all()
    )


def get_file(db: Session, file_id: int) -> Optional[KnowledgeFile]:
    return db.query(KnowledgeFile).filter_by(id=file_id).first()
