"""
日志相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class LogItem(BaseModel):
    """单条日志"""
    id: int
    timestamp: str
    level: str              # INFO / SUCCESS / WARN / ERROR
    category: str           # system / scan / subscribe / tmdb
    source: Optional[str] = None
    message: str


class LogListResponse(BaseModel):
    """日志列表响应"""
    total: int
    items: List[LogItem]
