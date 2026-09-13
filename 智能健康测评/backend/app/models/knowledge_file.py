"""知识库文件元数据模型：多模态知识库（文档/图片）入库记录"""
from datetime import datetime

from sqlalchemy import (
    Column, BigInteger, String, Integer, Text, DateTime,
    Enum as SAEnum, TIMESTAMP, Index,
)

from app.core.database import Base


class KnowledgeFile(Base):
    """知识库文件表：记录上传的文档/图片及其解析状态"""
    __tablename__ = "knowledge_files"
    __table_args__ = (
        Index("idx_upload_time", "upload_time"),
        Index("idx_status", "status"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="文件ID")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_type = Column(String(50), comment="文件类型: text/pdf/docx/image/pptx")
    file_ext = Column(String(20), comment="扩展名")
    file_size = Column(Integer, comment="文件大小(字节)")

    # MinIO 存储
    object_name = Column(String(500), comment="MinIO对象名")
    bucket = Column(String(100), comment="MinIO桶名")
    file_url = Column(String(1000), comment="访问URL")

    # 解析状态
    status = Column(SAEnum("pending", "parsing", "done", "failed"),
                    default="pending", comment="解析状态")
    chunk_count = Column(Integer, default=0, comment="向量化分块数")
    parse_message = Column(Text, comment="解析结果/错误信息")

    # 内容摘要（文本类文档的全文，图片为OCR结果）
    content_text = Column(Text, comment="解析出的全文/OCR文本")
    content_summary = Column(String(1000), comment="内容摘要")

    # 元数据
    uploaded_by = Column(String(100), default="system", comment="上传人")
    upload_time = Column(DateTime, default=datetime.now, comment="上传时间")
    created_at = Column(TIMESTAMP, server_default="CURRENT_TIMESTAMP", comment="创建时间")
