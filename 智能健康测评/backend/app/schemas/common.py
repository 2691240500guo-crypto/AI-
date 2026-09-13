"""通用响应模型"""
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装：{status, message, data}"""
    status: int = 200
    message: str = "success"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    detail: str
