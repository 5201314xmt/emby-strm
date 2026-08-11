"""
设置相关 Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class SettingItem(BaseModel):
    """单个配置项"""
    key: str
    value: str
    desc: str = ""
    default: str = ""
    masked: bool = False       # 是否已打码（敏感字段）


class SettingsSaveRequest(BaseModel):
    """保存设置请求（所有字段都是可选的）"""
    mp_url: Optional[str] = None
    mp_token: Optional[str] = None
    tmdb_key: Optional[str] = None
    tmdb_lang: Optional[str] = None
    auto_scan: Optional[bool] = None
    scan_interval: Optional[int] = None
    auto_subscribe: Optional[bool] = None
    include_specials: Optional[bool] = None


class TestConnectionRequest(BaseModel):
    """测试连接请求"""
    mp_url: Optional[str] = None
    mp_token: Optional[str] = None
    tmdb_key: Optional[str] = None
    emby_url: Optional[str] = None
    emby_api_key: Optional[str] = None


class TestResult(BaseModel):
    """单个测试结果"""
    name: str
    ok: Optional[bool] = None    # True=成功 False=失败 None=未配置
    detail: str = ""
