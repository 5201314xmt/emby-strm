"""
缺集相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class SeasonData(BaseModel):
    """一季的缺集详情（列表行中展开用）"""
    season_number: int
    total_episodes: int = 0
    aired_episodes: int = 0
    present_count: int = 0
    missing_count: int = 0
    missing_episodes: List[int] = []
    status: str = "complete"          # complete / partial / full_missing
    data_quality: str = "normal"     # normal / degraded
    subscribed: bool = False
    ignored: bool = False
    mp_state: str = ""


class ShowListItem(BaseModel):
    """缺集列表中的一行"""
    tmdb_id: int
    name: str
    year: Optional[str] = ""
    poster: Optional[str] = ""
    source_ids: List[int] = []
    source_names: List[str] = []     # 源的名字列表（前端直接显示）
    ignore_entire: bool = False
    seasons: List[SeasonData] = []


class ShowDetail(ShowListItem):
    """单剧详情（缺集列表行点击后的抽屉内容）"""
    overview: Optional[str] = ""


class ShowListResponse(BaseModel):
    """缺集列表分页响应"""
    total: int
    page: int
    page_size: int
    items: List[ShowListItem]


class BatchSubscribeRequest(BaseModel):
    """批量订阅请求"""
    items: List[dict] = Field(..., description='[{"tmdb_id": 1, "season": 2}]')


class BatchIgnoreRequest(BaseModel):
    """批量忽略请求"""
    items: List[dict] = Field(..., description='[{"tmdb_id": 1, "season": 2}] (-1=整部剧)')
