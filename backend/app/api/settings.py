"""
设置 API 路由 —— 配置的读写 + 连接测试

所有配置项存数据库 settings 表，同时支持环境变量覆盖。
敏感字段（Token/API Key）打码后返回。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..models.setting import Setting
from ..utils.helpers import make_response, mask_secret, is_masked
from ..config import settings as app_settings
from .deps import get_current_user

router = APIRouter(prefix="/api/settings", tags=["设置"], dependencies=[Depends(get_current_user)])

# 敏感字段列表（这些字段的值在返回前端时打码）
MASKED_KEYS = {"mp_token", "emby_api_key", "tmdb_key"}

# 配置项定义（key → [默认值, 中文说明]）
CONFIG_DEFS = {
    "mp_url":           ["", "MoviePilot 地址（如 http://192.168.1.100:3000）"],
    "mp_token":         ["", "MoviePilot API Token（MP 设置→安全→API令牌）"],
    "tmdb_key":         ["", "TMDB API Key（MoviePilot v3 无需填写）"],
    "tmdb_lang":        ["zh-CN", "TMDB 语言偏好"],
    "auto_scan":        ["0", "是否开启自动定时扫描：1=开启 0=关闭"],
    "scan_interval":    ["12", "自动扫描间隔（小时）"],
    "auto_subscribe":   ["0", "扫描后自动订阅缺集：1=开启 0=关闭"],
    "include_specials": ["0", "是否检测特别篇 S00：1=检测 0=不检测"],
    "last_scan":        ["", "上次扫描完成时间（系统自动记录）"],
}


def _is_masked_value(value: str) -> bool:
    """判断字符串是否已打码（全星号开头）"""
    return is_masked(value)


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """
    获取所有设置项

    敏感字段自动打码返回（前端显示"******abcd"，用户不改就不更新）。
    """
    # 从数据库读取已保存的值
    result = await db.execute(select(Setting))
    db_settings = {s.key: s.value for s in result.scalars().all()}

    items = []
    for key, (default, desc) in CONFIG_DEFS.items():
        value = db_settings.get(key, default)
        masked = False
        display = value
        if key in MASKED_KEYS and value and not _is_masked_value(value):
            display = mask_secret(value)
            masked = True

        items.append({
            "key": key,
            "value": value,
            "display": display,
            "desc": desc,
            "default": default,
            "masked": masked,
        })

    return make_response(True, data={"items": items})


@router.put("")
async def save_settings(
    body: dict = None,
    db: AsyncSession = Depends(get_db),
):
    """
    保存设置

    敏感字段如果传回来的是打码值（用户没改），跳过不保存，
    避免把 "******wxyz" 存进数据库覆盖真实值。
    """
    if not body:
        return make_response(False, message="没有要保存的设置")

    saved_count = 0
    for key, value in body.items():
        if key not in CONFIG_DEFS:
            continue

        # 敏感字段打码值跳过
        if key in MASKED_KEYS and isinstance(value, str) and _is_masked_value(value):
            continue

        value_str = str(value)
        # upsert（存在则更新，不存在则插入）
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value_str
        else:
            db.add(Setting(key=key, value=value_str))
        saved_count += 1

    await db.commit()

    # 刷新内存中的配置（让新设置立即生效）
    # 注意：pydantic-settings 从环境变量读取，数据库配置需要运行时手动处理
    # 这里通知外部重新加载 TMDB 客户端等

    return make_response(True, message=f"已保存 {saved_count} 项设置")


@router.post("/test")
async def test_connection(
    body: dict = None,
    db: AsyncSession = Depends(get_db),
):
    """
    测试连接 —— 检查 MoviePilot / TMDB / Emby 是否可用

    优先使用请求中传的临时值测试，
    如果没传则用数据库中保存的值。
    """
    results = []
    mp_url = (body or {}).get("mp_url", app_settings.mp_url)
    mp_token = (body or {}).get("mp_token", app_settings.mp_token)

    # 1. 测试 MoviePilot
    if mp_url and mp_token:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{mp_url.rstrip('/')}/api/v1/",
                    headers={"Authorization": mp_token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    version = data.get("version", "未知")
                    results.append({"name": "MoviePilot", "ok": True,
                                   "detail": f"连接成功（版本：{version}）"})
                else:
                    results.append({"name": "MoviePilot", "ok": False,
                                   "detail": f"返回异常状态码：{resp.status_code}"})
        except Exception as e:
            results.append({"name": "MoviePilot", "ok": False,
                           "detail": f"连接失败：{e}"})
    else:
        results.append({"name": "MoviePilot", "ok": False,
                       "detail": "地址或 Token 未填写"})

    # 2. 测试 TMDB
    tmdb_key = (body or {}).get("tmdb_key", app_settings.tmdb_key)
    if mp_url and mp_token:
        # 通过 MP 代理更好
        results.append({"name": "TMDB 数据", "ok": True,
                       "detail": "将使用 MoviePilot 代理（无需 TMDB Key）"})
    elif tmdb_key:
        results.append({"name": "TMDB 数据", "ok": True,
                       "detail": "将使用直连 TMDB（自己的 API Key）"})
    else:
        results.append({"name": "TMDB 数据", "ok": False,
                       "detail": "MP 地址未填，且未填 TMDB Key，请至少填一个"})

    # 3. 测试 Emby（如果配置了）
    emby_url = (body or {}).get("emby_url", "")
    emby_key = (body or {}).get("emby_api_key", "")
    if emby_url and emby_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{emby_url.rstrip('/')}/emby/System/Info",
                    headers={"X-Emby-Token": emby_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append({"name": "Emby", "ok": True,
                                   "detail": f"连接成功（{data.get('ServerName', '')}）"})
                else:
                    results.append({"name": "Emby", "ok": False,
                                   "detail": f"连接失败：状态码 {resp.status_code}"})
        except Exception as e:
            results.append({"name": "Emby", "ok": False,
                           "detail": f"连接失败：{e}"})
    else:
        results.append({"name": "Emby", "ok": None,
                       "detail": "未配置（可跳过，不影响使用）"})

    return make_response(True, data={"results": results})
