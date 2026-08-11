"""
============================================================
认证模块 - 管理员密码 + 登录会话管理
============================================================
说明：
  - 密码用 PBKDF2 加盐哈希保存（标准库实现，不需要额外依赖），
    数据库里永远不存明文密码
  - 登录成功后发一个随机 Session Token 存在浏览器 Cookie 里（30 天有效）
  - 所有 /api/* 接口（除登录相关和健康检查）都要求已登录，防止公网被乱操作
用法：
  - 首次使用：POST /api/auth/setup 设置管理员密码
  - 之后登录：POST /api/auth/login
  - 修改密码：POST /api/auth/change-password（在设置页操作）
============================================================
"""

import datetime
import hashlib
import hmac
import secrets

from . import database

# Session 有效期（天）：30 天内不用重新登录
SESSION_DAYS = 30

# 密码哈希迭代次数（越高越难暴力破解，单次校验约 1/1000 秒，可接受）
_PBKDF2_ITERATIONS = 100_000

# 敏感字段列表：这些字段在网页上打码显示，保存时打码值不会被写回
MASKED_KEYS = ("mp_token", "emby_api_key", "tmdb_key")
MASK_PREFIX = "******"

# ============================================================
# 密码哈希
# ============================================================

def hash_password(password: str) -> str:
    """
    生成密码哈希，格式：pbkdf2$迭代次数$盐(hex)$哈希(hex)
    每次生成都用随机盐，同一密码两次结果不同（防彩虹表）
    """
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    校验密码是否正确
    用 hmac.compare_digest 比较，防止时序攻击
    格式不对（旧版本/损坏）时返回 False，不抛异常
    """
    if not stored:
        return False
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), int(iters),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ============================================================
# 设置存取（存 settings 表，但不属于 CONFIG_DEFS，由本模块专用）
# ============================================================

def get_setting(key: str) -> str:
    """读取设置（settings 表），没有返回空字符串"""
    row = database.query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else ""


def set_setting(key: str, value: str):
    """写入设置（settings 表），已存在则覆盖"""
    database.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def is_initialized() -> bool:
    """是否已经设置过管理员密码（首次使用引导用）"""
    return bool(get_setting("admin_password_hash"))


# ============================================================
# 敏感字段打码
# ============================================================

def mask(value: str) -> str:
    """敏感值打码显示，如 abcdef1234 → ******1234"""
    if not value:
        return ""
    return MASK_PREFIX + value[-4:]


def is_masked(value: str) -> bool:
    """判断一个值是不是打码状态（保存设置时用来跳过，防止覆盖真实值）"""
    return value.startswith(MASK_PREFIX)


# ============================================================
# 登录会话
# ============================================================

def create_session() -> str:
    """
    创建一条新会话，返回随机会话 Token
    浏览器把这个 Token 存在 Cookie 里，之后每次请求带上就能通过验证
    """
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now()
    expires = now + datetime.timedelta(days=SESSION_DAYS)
    database.execute(
        "INSERT INTO sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
        (token,
         now.strftime("%Y-%m-%d %H:%M:%S"),
         expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return token


def validate_session(token) -> bool:
    """校验会话是否有效（存在且没过期）"""
    if not token:
        return False
    row = database.query_one("SELECT expires_at FROM sessions WHERE token=?", (token,))
    if not row:
        return False
    try:
        exp = datetime.datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return exp > datetime.datetime.now()


def destroy_session(token):
    """删除一条会话（退出登录用）"""
    if token:
        database.execute("DELETE FROM sessions WHERE token=?", (token,))


def cleanup_expired_sessions():
    """删除所有过期会话（登录时顺带清理，防止表无限变大）"""
    database.execute(
        "DELETE FROM sessions WHERE expires_at < ?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
    )
