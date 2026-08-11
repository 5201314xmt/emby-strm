"""
订阅相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class SubscriptionItem(BaseModel):
    """订阅列表中的一行"""
    id: Optional[int] = None
    tmdb_id: int
    season: int
    mp_id: Optional[int] = None
    name: str = ""
    state: str = "R"            # R=等待 S=搜索中 P=已完成
    auto: bool = False
    created_at: Optional[str] = None


class SubscriptionListResponse(BaseModel):
    """订阅列表响应"""
    source: str = "local"       # mp=从MoviePilot实时获取  local=本地记录
    total: int = 0
    subscriptions: List[SubscriptionItem] = []
    warning: Optional[str] = None
