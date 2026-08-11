"""
仪表盘相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class DashboardKPI(BaseModel):
    """仪表盘顶部的统计数字"""
    show_count: int = Field(0, description="总剧集数")
    missing_count: int = Field(0, description="缺集总数")
    full_missing_count: int = Field(0, description="整季缺失数")
    subscribed_count: int = Field(0, description="已订阅数")
    partial_count: int = Field(0, description="部分缺失剧数")
    unrecognized_count: int = Field(0, description="未识别文件数")


class RecentScanInfo(BaseModel):
    """最近扫描记录摘要"""
    id: int
    status: str                # completed / failed / cancelled
    source_names: List[str] = []   # 扫描了哪些源
    started_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    show_count: int = 0
    missing_count: int = 0


class ActiveScanInfo(BaseModel):
    """当前正在运行的扫描（null=没有进行中的扫描）"""
    job_id: int
    status: str
    phase: str
    progress: float
    done_shows: int
    total_shows: int
    current_item: str
    eta_seconds: int


class DashboardResponse(BaseModel):
    """仪表盘聚合接口返回"""
    kpi: DashboardKPI
    active_scan: Optional[ActiveScanInfo] = None
    recent_scans: List[RecentScanInfo] = []
    alerts: List[str] = []
