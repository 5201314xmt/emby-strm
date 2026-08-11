"""
认证相关 Schemas —— 登录、改密、状态查询的请求/响应模型
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    password: str = Field(..., min_length=1, description="管理员密码")


class SetupRequest(BaseModel):
    """首次设置密码请求"""
    password: str = Field(..., min_length=6, description="管理员密码（至少6位）")


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., min_length=1, description="当前密码")
    new_password: str = Field(..., min_length=6, description="新密码（至少6位）")


class AuthStatusResponse(BaseModel):
    """登录状态回包"""
    initialized: bool = Field(..., description="系统是否已初始化（设置过密码）")
    logged_in: bool = Field(..., description="当前是否已登录")
