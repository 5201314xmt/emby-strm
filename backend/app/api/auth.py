"""
认证 API 路由 —— 登录、退出、改密码、健康检查

注意：
  - 健康检查不需要登录（给 Docker 用）
  - 所有接口都返回统一的 { success, data, message } 格式
"""
import asyncio
from fastapi import APIRouter, Request, Response, Depends
from sqlalchemy import select

from ..core.security import (
    hash_password, verify_password, create_session,
    validate_session, destroy_session, destroy_all_sessions_except,
)
from ..core.database import AsyncSessionLocal
from ..models.setting import Setting
from ..schemas.auth import LoginRequest, SetupRequest, ChangePasswordRequest
from ..utils.helpers import make_response
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])

SESSION_COOKIE = "queji_session"

# ========== 工具函数 ==========

def _set_cookie(response: Response, token: str):
    """设置登录 Cookie（30 天有效）"""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,            # JS 无法读取（防 XSS）
        samesite="lax",           # 跨站请求不携带（防 CSRF）
        max_age=30 * 24 * 3600,   # 30 天
        path="/",
    )


async def _get_setting(key: str) -> str | None:
    """从数据库 settings 表读取一个配置值"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Setting.value).where(Setting.key == key)
        )
        row = result.one_or_none()
        return row[0] if row else None


async def _set_setting(key: str, value: str):
    """往数据库 settings 表写入一个配置值"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            db.add(setting)
        await db.commit()


# ========== 接口 ==========

@router.get("/status")
async def auth_status(request: Request):
    """
    获取登录状态

    前端在加载页面时先调这个接口，判断：
      - 系统是否已初始化（没初始化 → 跳转安装向导）
      - 用户是否已登录（没登录 → 跳转登录页）
    """
    pwd_hash = await _get_setting("admin_password_hash")
    initialized = bool(pwd_hash)
    logged_in = await validate_session(request.cookies.get(SESSION_COOKIE))
    return make_response(
        success=True,
        data={
            "initialized": initialized,
            "logged_in": logged_in,
        },
    )


@router.post("/setup")
async def auth_setup(request: Request, response: Response, body: SetupRequest):
    """
    首次安装 —— 设置管理员密码

    只能设置一次。设置成功后自动登录，跳转到主页。
    """
    pwd_hash = await _get_setting("admin_password_hash")
    if pwd_hash:
        return make_response(False, message="系统已初始化，如需修改密码请到设置页")

    # 保存密码哈希
    hashed = hash_password(body.password)
    await _set_setting("admin_password_hash", hashed)

    # 自动登录
    token = await create_session()
    _set_cookie(response, token)

    return make_response(True, message="设置成功！请牢记你的密码")


@router.post("/login")
async def auth_login(request: Request, response: Response, body: LoginRequest):
    """
    登录

    密码正确后下发 Cookie，30 天内免登录。
    错误密码延迟 1 秒返回（防暴力破解）。
    """
    pwd_hash = await _get_setting("admin_password_hash")
    if not pwd_hash:
        return make_response(False, message="系统还未初始化，请先设置管理员密码")

    if not verify_password(body.password, pwd_hash):
        import asyncio
        await asyncio.sleep(1)   # 延迟 1 秒，拖慢暴力破解
        return make_response(False, message="密码不正确，请重试")

    # 登录成功
    token = await create_session()
    _set_cookie(response, token)

    return make_response(True, message="登录成功")


@router.post("/logout")
async def auth_logout(request: Request, response: Response):
    """
    退出登录

    销毁服务端 Session + 清除浏览器 Cookie。
    """
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await destroy_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return make_response(True, message="已退出登录")


@router.post("/change-password")
async def auth_change_password(
    request: Request,
    body: ChangePasswordRequest,
    _: None = Depends(get_current_user),
):
    """
    修改管理员密码

    需要先验证当前密码。修改后其他设备全部重新登录。
    """
    pwd_hash = await _get_setting("admin_password_hash")
    if not verify_password(body.old_password, pwd_hash or ""):
        return make_response(False, message="当前密码不正确")

    # 保存新密码
    new_hash = hash_password(body.new_password)
    await _set_setting("admin_password_hash", new_hash)

    # 让其他设备全部重新登录（保留当前设备）
    current_token = request.cookies.get(SESSION_COOKIE)
    if current_token:
        await destroy_all_sessions_except(current_token)

    return make_response(True, message="密码已修改，其他设备需要重新登录")
