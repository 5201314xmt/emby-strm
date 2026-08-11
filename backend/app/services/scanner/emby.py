"""
Emby API 扫描器 —— 通过 Emby API 遍历媒体库获取已存在的集

复用原项目 v1 的 Emby API 对接逻辑。
遍历管理员用户的所有 Series → 所有 Episodes，
汇总为 (TMDB编号, 季号, 集号) 的格式。
"""
import httpx
from .base import ScanResult
from ..logger import add_log

# Emby API 超时
_TIMEOUT = 60


async def _emby_get(emby_url: str, api_key: str, path: str, params: dict = None) -> dict | None:
    """调用 Emby API"""
    url = emby_url.rstrip("/") + path
    headers = {"X-Emby-Token": api_key}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            await add_log("WARN", "scan", f"Emby API 返回 {resp.status_code}: {path}")
            return None
    except Exception as e:
        await add_log("ERROR", "scan", f"Emby API 请求失败: {e} ({path})")
        return None


async def scan_emby(emby_url: str, emby_api_key: str, source_id: int = 0) -> ScanResult:
    """
    通过 Emby API 扫描媒体库

    Args:
        emby_url:     Emby 服务器地址（如 http://192.168.1.100:8096）
        emby_api_key: Emby API Key
        source_id:    扫描源 ID

    Returns:
        ScanResult（shows 字典 + unrecognized 列表）
    """
    result = ScanResult()

    # 1. 找管理员用户
    users = await _emby_get(emby_url, emby_api_key, "/emby/Users")
    if not users:
        result.unrecognized.append({
            "path": emby_url,
            "source_id": source_id,
            "reason": "Emby API 返回空用户列表，请检查 API Key",
        })
        return result

    admin_user = None
    for u in users:
        if u.get("Policy", {}).get("IsAdministrator"):
            admin_user = u
            break
    if not admin_user:
        admin_user = users[0]  # 没有管理员就取第一个

    user_id = admin_user["Id"]
    await add_log("INFO", "scan", f"Emby 用户: {admin_user.get('Name', user_id)}")

    # 2. 获取所有剧集（Series）—— 支持分页
    all_series = []
    start_index = 0
    limit = 200
    while True:
        series_list = await _emby_get(
            emby_url, emby_api_key,
            f"/emby/Users/{user_id}/Items",
            params={
                "IncludeItemTypes": "Series",
                "Recursive": True,
                "Fields": "ProviderIds",
                "StartIndex": start_index,
                "Limit": limit,
            },
        )
        if not series_list or "Items" not in series_list:
            break
        items = series_list["Items"]
        all_series.extend(items)
        if len(items) < limit:
            break
        start_index += limit

    await add_log("INFO", "scan", f"Emby 发现 {len(all_series)} 部剧集")

    for series in all_series:
        # 3. 获取 TMDB 编号（从 ProviderIds 中提取）
        provider_ids = series.get("ProviderIds", {})
        tmdb_id_str = provider_ids.get("Tmdb") or provider_ids.get("tmdb")
        if not tmdb_id_str:
            result.unrecognized.append({
                "path": series.get("Name", "未知"),
                "source_id": source_id,
                "reason": "Emby 剧集缺少 TMDB 编号（ProviderIds 中无 Tmdb）",
            })
            continue
        try:
            tmdb_id = int(tmdb_id_str)
        except ValueError:
            result.unrecognized.append({
                "path": series.get("Name", "未知"),
                "source_id": source_id,
                "reason": f"TMDB 编号格式异常: {tmdb_id_str}",
            })
            continue

        series_name = series.get("Name", "")
        series_id = series.get("Id", "")

        # 4. 获取该剧集的所有 Episode —— 支持分页
        all_episodes = []
        ep_start = 0
        ep_limit = 500
        while True:
            episodes = await _emby_get(
                emby_url, emby_api_key,
                f"/emby/Users/{user_id}/Items",
                params={
                    "ParentId": series_id,
                    "IncludeItemTypes": "Episode",
                    "Recursive": True,
                    "Fields": "ParentIndexNumber,IndexNumber",
                    "StartIndex": ep_start,
                    "Limit": ep_limit,
                },
            )
            if not episodes or "Items" not in episodes:
                break
            items = episodes["Items"]
            all_episodes.extend(items)
            if len(items) < ep_limit:
                break
            ep_start += ep_limit

        if not all_episodes:
            continue

        show = result.shows.setdefault(tmdb_id, {
            "name": series_name,
            "source_ids": {source_id},
            "seasons": {},
        })
        if not show["name"]:
            show["name"] = series_name

        for ep in all_episodes:
            season_num = ep.get("ParentIndexNumber") or 1
            ep_num = ep.get("IndexNumber")
            if ep_num is None:
                continue
            try:
                season_num = int(season_num)
                ep_num = int(ep_num)
            except ValueError:
                continue

            season_set = show["seasons"].setdefault(season_num, [])
            if ep_num not in season_set:
                season_set.append(ep_num)

    await add_log("INFO", "scan", f"Emby 扫描完成：{len(result.shows)} 部剧")
    return result
