"""
扫描相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ScanStartRequest(BaseModel):
    """开始扫描请求"""
    source_ids: Optional[List[int]] = Field(None, description="指定扫描哪些源（空=全部启用源）")


class ScanStatusResponse(BaseModel):
    """扫描进度（HTTP 降级）"""
    job_id: Optional[int] = None
    running: bool = False
    status: str = "idle"
    phase: str = ""
    progress: float = 0.0
    done_shows: int = 0
    total_shows: int = 0
    current_item: str = ""
    eta_seconds: int = 0
    error: str = ""


class ScanHistoryItem(BaseModel):
    """历史扫描记录"""
    id: int
    status: str
    source_ids: List[int] = []
    phase: str = ""
    total_shows: int = 0
    done_shows: int = 0
    auto_subscribed: int = 0
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
