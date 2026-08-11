"""
扫描源相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class SourceCreate(BaseModel):
    """创建扫描源"""
    name: str = Field(..., min_length=1, max_length=100, description="源名称")
    path: str = Field(..., min_length=1, max_length=500, description="容器内路径")
    type: str = Field("filesystem", pattern="^(filesystem|emby)$", description="类型")
    emby_url: Optional[str] = Field(None, description="Emby 地址")
    emby_api_key: Optional[str] = Field(None, description="Emby API Key")


class SourceUpdate(BaseModel):
    """修改扫描源（所有字段可选，只更新传了的）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    path: Optional[str] = Field(None, min_length=1, max_length=500)
    enabled: Optional[bool] = None
    emby_url: Optional[str] = None
    emby_api_key: Optional[str] = None


class SourceItem(BaseModel):
    """扫描源列表中的一项"""
    id: int
    name: str
    path: str
    type: str
    enabled: bool
    emby_url: Optional[str] = None
    last_scan_at: Optional[str] = None
    last_scan_status: Optional[str] = None
    last_error: Optional[str] = None
    show_count: Optional[int] = None
    created_at: Optional[str] = None


class CheckPathRequest(BaseModel):
    """检查路径请求"""
    path: str = Field(..., min_length=1, description="要检查的路径")
