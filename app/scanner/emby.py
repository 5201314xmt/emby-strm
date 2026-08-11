"""
============================================================
Emby 扫描器 - 通过 Emby 的 API 读取媒体库，"目前有哪些集"
============================================================
说明：
  - 这是一个可选的扫描方式：不挂载 strm 目录时，用 Emby API 也能拿到
    "库里有哪部剧、哪些集"（strm 文件被 Emby 扫描后会在库里出现）
  - 需要：Emby 地址 + API Key（Emby 设置->高级->API 密钥）
  - 输出的结果结构和文件扫描器完全一样（都是 ScanResult），
    因此上层代码完全不用区分数据从哪来，方便扩展
============================================================
"""

import httpx

from ..models import ScanResult
from .. import logger

# 共享 HTTP 客户端（复用连接，Emby 剧多时逐个请求也不慢）
_http = httpx.Client(timeout=30)


def scan(emby_url: str, api_key: str) -> ScanResult:
    """
    通过 Emby API 扫描媒体库
    返回：ScanResult（和文件扫描器格式一致）
    失败时返回空结果并记录日志。
    """
    result = ScanResult()
    if not emby_url or not api_key:
        logger.log("ERROR", "scan", "Emby 扫描失败：地址或 API Key 未填写")
        return result

    try:
        # 1. 找到第一个管理员用户（Emby API 的 Items 接口需要用户 ID）
        users = _get_json(emby_url, api_key, "/emby/Users")
        user_id = None
        for user in users or []:
            if user.get("Policy", {}).get("IsAdministrator"):
                user_id = user.get("Id")
                break
        if not user_id and users:
            user_id = users[0].get("Id")
        if not user_id:
            logger.log("ERROR", "scan", "Emby 扫描失败：找不到用户")
            return result

        # 2. 拉取所有剧集（Series）列表
        series_list = _get_json(
            emby_url, api_key,
            f"/emby/Users/{user_id}/Items",
            {"IncludeItemTypes": "Series", "Recursive": "true",
             "Fields": "ProviderIds,ProductionYear", "Limit": "100000"},
        )
        items = (series_list or {}).get("Items", [])
        logger.log("INFO", "scan", f"Emby 中找到了 {len(items)} 部剧")

        # 3. 对每部剧拉取剧集（Episodes）列表
        for series in items:
            tmdb_id = _get_tmdb_id(series)
            series_id = series.get("Id")
            if not tmdb_id or not series_id:
                result.unrecognized.append(
                    {"path": series.get("Name", "未知剧名"), "reason": "Emby 里这部剧没有 TMDB 编号"})
                continue

            # 剧集接口返回该剧全部季的剧集
            episodes = _get_json(
                emby_url, api_key,
                f"/emby/Shows/{series_id}/Episodes",
                {"Fields": "ProviderIds", "Limit": "100000"},
            )
            ep_items = (episodes or {}).get("Items", [])

            # 初始化这部剧的记录
            show = result.shows.setdefault(tmdb_id, {"name": "", "seasons": {}})
            if not show["name"]:
                show["name"] = series.get("Name", "")

            # 逐个剧集收集 (季号, 集号)
            for ep in ep_items:
                # 跳过"预告片/花絮"等非正片类型
                if ep.get("Type") not in (None, "Episode"):
                    continue
                season_num = ep.get("ParentIndexNumber")
                ep_num = ep.get("IndexNumber")
                if season_num is None or ep_num is None:
                    continue
                season_list = show["seasons"].setdefault(int(season_num), [])
                if ep_num not in season_list:
                    season_list.append(int(ep_num))

    except Exception as e:   # 网络或权限问题都汇总到这里，给出中文提示
        logger.log("ERROR", "scan", f"Emby 扫描出错：{e}")

    return result


# ============================================================
# 小工具函数
# ============================================================

def _get_tmdb_id(item: dict):
    """从 Emby 返回的条目里取 TMDB 编号（ProviderIds 字段里）"""
    providers = item.get("ProviderIds") or {}
    return providers.get("Tmdb")


def _get_json(url: str, api_key: str, path: str, params: dict = None) -> dict:
    """
    发送 Emby API 请求并返回 JSON
    Emby 的 API Key 通过 X-Emby-Token 请求头传递
    """
    headers = {"X-Emby-Token": api_key}
    resp = _http.get(url.rstrip("/") + path, params=params or {}, headers=headers)
    resp.raise_for_status()          # 出错会抛异常，由上层统一处理
    return resp.json()
