"""知识库与图谱相关请求/响应模型"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FileUploadResult(BaseModel):
    """文件上传+解析结果"""
    file_id: int
    file_name: str
    file_type: str
    status: str
    chunk_count: int
    content_summary: str
    parse_message: str


class KnowledgeFileOut(BaseModel):
    id: int
    file_name: str
    file_type: str
    file_ext: str
    file_size: int
    status: str
    chunk_count: int
    content_summary: str
    parse_message: Optional[str]
    upload_time: Optional[datetime]
    file_url: Optional[str]


class SearchRequest(BaseModel):
    query: str = Field(..., description="检索问题")
    top_k: int = 5
    file_id: Optional[int] = None


class SearchHit(BaseModel):
    content: str
    source: str
    file_id: Optional[int]
    distance: float


class GraphData(BaseModel):
    categories: List[str]
    nodes: List[dict]
    links: List[dict]


class DiseaseGraphOut(BaseModel):
    disease: str
    nutrients: List[dict]
    foods: List[str]
    advice: str
