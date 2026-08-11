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
            # 敏感字段：返回打码值，前端永不可见明文
            display = mask_secret(value)
            value = display  # ← 用打码值替代真实值，防止密钥泄露到浏览器
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

        # 统一转字符串：布尔值转为 "1"/"0"（兼容前端发 boolean 或 string）
        if isinstance(value, bool):
            value_str = "1" if value else "0"
        else:
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

    # 热更新内存中的客户端实例
    from ..core.app_state import reload_clients
    await reload_clients()
    from ..services.logger import add_log
    await add_log("INFO", "system", "设置已保存，客户端已重新加载")

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

    # 1. 测试 MoviePilot（含版本检测 + 订阅 API 测试）
    if mp_url and mp_token:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                # 兼容不同 MP 版本的认证头
                headers = {"Authorization": mp_token, "X-API-Key": mp_token}

                # 尝试多个路径检测 MP 可用性
                mp_ok = False
                version_str = ""
                for path in ["/api/v1/", "/api/v1/tmdb/seasons/1399", "/api/v1/subscribe/"]:
                    try:
                        resp = await client.get(f"{mp_url.rstrip('/')}{path}", headers=headers)
                        if resp.status_code == 200:
                            mp_ok = True
                            if path == "/api/v1/":
                                try:
                                    data = resp.json()
                                    version_str = data.get("version", "未知")
                                except Exception:
                                    pass
                            break
                    except Exception:
                        continue

                if mp_ok:
                    # 解析版本号判断大版本
                    is_v3 = False
                    try:
                        parts = version_str.lstrip("v").split(".")
                        major = int(parts[0]) if parts else 0
                        is_v3 = major >= 3
                    except Exception:
                        pass

                    # 检测 TMDB 代理可用性
                    tmdb_ok = False
                    try:
                        tr = await client.get(
                            f"{mp_url.rstrip('/')}/api/v1/tmdb/seasons/1399",
                            headers=headers,
                        )
                        tmdb_ok = tr.status_code == 200
                    except Exception:
                        pass

                    # 检测订阅 API
                    sub_ok = False
                    try:
                        sr = await client.get(
                            f"{mp_url.rstrip('/')}/api/v1/subscribe/",
                            headers=headers,
                        )
                        sub_ok = sr.status_code == 200
                    except Exception:
                        pass

                    detail_parts = [f"版本: {version_str}"]
                    if is_v3:
                        detail_parts.append("V3+" if tmdb_ok else "V3（TMDB代理未启用）")
                    else:
                        detail_parts.append("V1/V2（需配置 TMDB API Key）")
                    if sub_ok:
                        detail_parts.append("订阅API可用")
                    else:
                        detail_parts.append("订阅API不可用")

                    results.append({
                        "name": "MoviePilot",
                        "ok": True,
                        "detail": "，".join(detail_parts),
                        "version": version_str,
                        "is_v3": is_v3,
                        "tmdb_proxy": tmdb_ok,
                        "subscribe_ok": sub_ok,
                    })
                else:
                    results.append({"name": "MoviePilot", "ok": False,
                                   "detail": f"返回异常状态码：{resp.status_code}"})
        except Exception as e:
            results.append({"name": "MoviePilot", "ok": False,
                           "detail": f"连接失败：{e}"})
    else:
        results.append({"name": "MoviePilot", "ok": False,
                       "detail": "地址或 Token 未填写"})

    # 2. 测试 TMDB 数据源
    tmdb_key = (body or {}).get("tmdb_key", app_settings.tmdb_key)
    mp_is_v3 = any(r.get("is_v3") for r in results if r.get("name") == "MoviePilot")
    mp_has_proxy = any(r.get("tmdb_proxy") for r in results if r.get("name") == "MoviePilot")

    if mp_has_proxy:
        results.append({"name": "TMDB 数据", "ok": True,
                       "detail": "通过 MoviePilot V3 代理（无需 TMDB Key）"})
    elif mp_is_v3:
        results.append({"name": "TMDB 数据", "ok": False,
                       "detail": "MP V3 但 TMDB 代理未开启，请在 MP 设置中启用"})
    elif tmdb_key:
        results.append({"name": "TMDB 数据", "ok": True,
                       "detail": "使用直连 TMDB API（自己的 Key，MP V1/V2 兼容）"})
    elif mp_url and mp_token:
        results.append({"name": "TMDB 数据", "ok": False,
                       "detail": "MP 为 V1/V2 且未填写 TMDB API Key，请到 TMDB 官网申请免费 Key"})
    else:
        results.append({"name": "TMDB 数据", "ok": False,
                       "detail": "请先配置 MoviePilot 地址，或填写 TMDB API Key 直连"})

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
