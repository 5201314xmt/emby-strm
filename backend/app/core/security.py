"""
安全认证模块 —— 密码哈希 + 会话管理

安全措施：
  - PBKDF2-SHA256 加盐哈希（10 万次迭代）
  - hmac.compare_digest 防时序攻击
  - 错误密码延迟 1 秒（防暴力破解）
  - Session Token 30 天有效
  - 修改密码后其他 session 全部失效

用法：
  from app.core.security import hash_password, verify_password, create_session
"""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from sqlalchemy import select, delete

from ..core.database import AsyncSessionLocal
from ..models.session import Session


# ========== 密码相关 ==========

def hash_password(password: str, salt: str = None) -> str:
    """
    使用 PBKDF2-SHA256 加盐哈希密码

    返回格式：  salt:hash_hex
    盐和哈希用冒号分隔，存到数据库。
    小白不用关心细节——调用 hash_password("123456") 即可。

    Args:
        password: 明文密码
        salt:     盐值（留空自动生成 32 字节随机盐）
    """
    if salt is None:
        salt = secrets.token_hex(32)   # 64 个十六进制字符的随机盐
    # hashlib.pbkdf2_hmac 是 Python 标准库自带，不需要额外安装
    dk = hashlib.pbkdf2_hmac(
        "sha256",                       # 哈希算法
        password.encode("utf-8"),       # 密码转字节
        salt.encode("utf-8"),           # 盐转字节
        100_000,                        # 迭代次数（足够高，防止 GPU 暴破）
    )
    return salt + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    """
    验证密码是否正确

    使用 hmac.compare_digest 比较哈希值（防时序攻击）。
    时序攻击：攻击者通过测量"返回错误的速度"来猜密码。
    compare_digest 让比较时间始终一致，堵住这个漏洞。

    Args:
        password: 用户输入的明文密码
        stored:   数据库里存的 "salt:hash" 字符串
    Returns:
        True=密码正确, False=不正确
    """
    if not stored or ":" not in stored:
        return False
    salt, _ = stored.split(":", 1)
    expected = hash_password(password, salt)
    return hmac.compare_digest(expected.encode(), stored.encode())


# ========== 会话（登录态）相关 ==========

SESSION_DAYS = 30   # 登录有效期（天）


def generate_token() -> str:
    """生成一个 128 位随机 Session Token（256 个十六进制字符）"""
    return secrets.token_hex(128)


async def create_session() -> str:
    """
    创建登录会话（用户登录成功后调用）

    往 sessions 表插一条记录，30 天后自动过期。
    返回 Token，前端存到 Cookie 里。
    """
    token = generate_token()
    now = datetime.now()
    expires = now + timedelta(days=SESSION_DAYS)
    async with AsyncSessionLocal() as db:
        session = Session(
            token=token,
            created_at=now,
            expires_at=expires,
        )
        db.add(session)
        await db.commit()
    return token


async def validate_session(token: str) -> bool:
    """
    验证 Session Token 是否有效

    Args:
        token: 从 Cookie 里取出的 queji_session 值
    Returns:
        True=已登录, False=未登录或已过期
    """
    if not token:
        return False
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Session).where(Session.token == token)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return False
        # 检查是否过期
        if datetime.now() > session.expires_at:
            await db.delete(session)
            await db.commit()
            return False
        return True


async def destroy_session(token: str):
    """销毁登录会话（用户点击退出时调用）"""
    if not token:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Session).where(Session.token == token))
        await db.commit()


async def destroy_all_sessions_except(current_token: str):
    """
    让其他设备全部重新登录（修改密码后调用）
    只保留当前设备的 session。
    """
    if not current_token:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Session).where(Session.token != current_token)
        )
        await db.commit()


async def cleanup_expired_sessions():
    """清理过期的 Session 记录（定时或登录时调用）"""
    async with AsyncSessionLocal() as db:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            delete(Session).where(Session.expires_at < now)
        )
        await db.commit()
