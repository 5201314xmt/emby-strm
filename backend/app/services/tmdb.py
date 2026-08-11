"""
TMDB 数据源服务 —— 三级缓存获取剧集信息

数据源模式（自动切换）：
  1. MoviePilot 代理（推荐）：走 MP 的 /api/v1/tmdb/* 接口，无需 TMDB Key
  2. TMDB 直连：用自己的 API Key 调 api.themoviedb.org

三级缓存策略：
  一级：内存缓存（进程内 → 24h TTL）
  二级：磁盘缓存（SQLite tmdb_cache 表 → 跨重启永久保存）
  三级：网络请求（失败时自动退回旧缓存，绝不丢数据）

网络失败时的行为：
  旧缓存存在 → 返回旧数据并标记 data_quality="degraded"（禁止自动订阅）
  无旧缓存 → 返回 None（该季参与缺集计算失败，标记为 error）
"""
import json
import threading
import time
from datetime import datetime, date

import httpx

from ..core.database import AsyncSessionLocal
from ..models.tmdb_cache import TMDBCache
from ..services.logger import add_log
from sqlalchemy import select, delete

from .tmdb_models import EpisodeInfo, SeasonInfo, ShowInfo

_TMDB_API = "https://api.themoviedb.org/3"
_TIMEOUT = 30
_CACHE_TTL = 24 * 3600
_SHOW_SEASON = -1  # season=-1 表示"剧信息"缓存


class TMDBSource:
    """
    TMDB 数据源（三级缓存 + 代理/直连自动切换）

    用法：
      src = TMDBSource(mp_client, tmdb_key, lang)
      await src.ensure_mode()                      # 探测数据源模式
      show, stale = await src.get_show(1399)        # 获取剧信息
      eps,  stale = await src.get_season(1399, 1)   # 获取某季集列表
    """

    def __init__(self, mp_client=None, tmdb_key: str = "", lang: str = "zh-CN"):
        self.mp = mp_client
        self.tmdb_key = tmdb_key
        self.lang = lang or "zh-CN"
        self.mode = "auto"          # auto → proxy/direct/none
        self.mode_checked = False
        self._mem_cache: dict[str, tuple[float, any]] = {}
        self._lock = threading.Lock()
        self._tmdb_http: httpx.Client | None = None

    # ========== 探测数据源 ==========

    async def ensure_mode(self) -> str:
        """
        确定用哪种方式获取 TMDB 数据（只探测一次）：
          1. 如果配了 MP 且 MP 支持代理接口 → 用代理
          2. 否则如果配了 TMDB Key → 直连
          3. 都没有 → 无法工作
        """
        if self.mode_checked:
            return self.mode

        # 优先 MP 代理
        if self.mp and self.mp.url and self.mp.token:
            try:
                if await self.mp.tmdb_supported():
                    self.mode = "proxy"
                    await add_log("INFO", "system", "TMDB 数据源：使用 MoviePilot 代理（无需 TMDB Key）")
                    self.mode_checked = True
                    return self.mode
                await add_log("INFO", "system", "MoviePilot 不支持 TMDB 代理接口（可能版本较老）")
            except Exception as e:
                await add_log("WARN", "system", f"探测 MoviePilot TMDB 代理失败：{e}")

        # 其次直连
        if self.tmdb_key:
            self.mode = "direct"
            await add_log("INFO", "system", "TMDB 数据源：使用直连（TMDB API Key）")
        else:
            self.mode = "none"
            await add_log("WARN", "system", "没有可用的 TMDB 数据源：请升级 MoviePilot 到 v3 或填写 TMDB API Key")
        self.mode_checked = True
        return self.mode

    # ========== 对外查询接口 ==========

    async def get_show(self, tmdb_id: int) -> tuple[ShowInfo | None, bool]:
        """获取一部剧的信息，返回 (ShowInfo, is_stale)"""
        mode = await self.ensure_mode()
        if mode == "none":
            return None, False
        return await self._cached(
            "show", tmdb_id, _SHOW_SEASON,
            lambda: self._fetch_show(tmdb_id, mode),
            _show_to_json, _show_from_json,
        )

    async def get_season(self, tmdb_id: int, season: int) -> tuple[list[EpisodeInfo] | None, bool]:
        """获取某一季的集列表，返回 (集列表, is_stale)"""
        mode = await self.ensure_mode()
        if mode == "none":
            return None, False
        return await self._cached(
            "eps", tmdb_id, season,
            lambda: self._fetch_episodes(tmdb_id, season, mode),
            _eps_to_json, _eps_from_json,
        )

    # ========== 缓存管理 ==========

    async def clear_cache(self, tmdb_id: int = None) -> int:
        """清空 TMDB 缓存（手动刷新用），返回删除条数"""
        async with AsyncSessionLocal() as db:
            if tmdb_id:
                result = await db.execute(
                    delete(TMDBCache).where(TMDBCache.tmdb_id == tmdb_id)
                )
            else:
                result = await db.execute(delete(TMDBCache))
            await db.commit()
            count = result.rowcount
        with self._lock:
            self._mem_cache.clear()
        return count

    # ========== 三级缓存查询 ==========

    async def _cached(self, kind: str, tmdb_id: int, season: int,
                      fetch_func, to_json, from_json) -> tuple[any, bool]:
        """带三级缓存的查询，返回 (数据, is_stale)"""
        key = f"{kind}:{tmdb_id}:{season}"
        now = time.time()

        # 1. 内存缓存
        with self._lock:
            hit = self._mem_cache.get(key)
            if hit and now - hit[0] < _CACHE_TTL:
                return hit[1], False

        # 2. 磁盘缓存
        cached_obj, cached_ts = await self._load_cache(tmdb_id, season, from_json)
        if cached_obj is not None and cached_ts is not None and now - cached_ts < _CACHE_TTL:
            with self._lock:
                self._mem_cache[key] = (time.time(), cached_obj)
            return cached_obj, False

        # 3. 网络请求
        try:
            data = await fetch_func()
        except Exception as e:
            await add_log("WARN", "scan", f"TMDB 查询异常（{e}），尝试使用旧缓存")
            data = None

        if data is not None:
            # 成功 → 写入磁盘缓存
            await self._save_cache(tmdb_id, season, to_json(data))
            with self._lock:
                self._mem_cache[key] = (time.time(), data)
            return data, False

        # 4. 网络失败 → 退回旧缓存
        if cached_obj is not None:
            await add_log("WARN", "scan", f"TMDB 查询失败，使用旧缓存（数据可能不是最新）：{key}")
            with self._lock:
                self._mem_cache[key] = (time.time(), cached_obj)
            return cached_obj, True

        return None, False

    async def _load_cache(self, tmdb_id: int, season: int, from_json):
        """从磁盘缓存表读取数据，返回 (解析数据, 时间戳)"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TMDBCache).where(
                    TMDBCache.tmdb_id == tmdb_id,
                    TMDBCache.season == season,
                )
            )
            cache = result.scalar_one_or_none()
            if not cache:
                return None, None
            try:
                return from_json(cache.response_json), time.mktime(cache.created_at.timetuple())
            except Exception:
                return None, None

    async def _save_cache(self, tmdb_id: int, season: int, json_str: str):
        """把成功获取的数据写入磁盘缓存"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(TMDBCache).where(
                    TMDBCache.tmdb_id == tmdb_id,
                    TMDBCache.season == season,
                )
            )
            cache = result.scalar_one_or_none()
            if cache:
                cache.response_json = json_str
                cache.created_at = datetime.now()
            else:
                db.add(TMDBCache(tmdb_id=tmdb_id, season=season, response_json=json_str))
            await db.commit()

    # ========== 网络请求（代理/直连） ==========

    async def _fetch_show(self, tmdb_id: int, mode: str) -> ShowInfo | None:
        """获取剧信息"""
        if mode == "proxy":
            return await self._fetch_show_via_mp(tmdb_id)
        return await self._fetch_show_direct(tmdb_id)

    async def _fetch_show_via_mp(self, tmdb_id: int) -> ShowInfo | None:
        ok, data = await self.mp.tmdb_seasons(tmdb_id)
        if not ok or not isinstance(data, list):
            return None
        show = ShowInfo(tmdb_id=tmdb_id)
        for s in data:
            sn = s.get("season_number", s.get("seasonNumber"))
            if sn is None:
                continue
            show.seasons.append(SeasonInfo(
                season_number=int(sn),
                episode_count=int(s.get("episode_count", s.get("episodeCount")) or 0),
            ))
        return show if show.seasons else None

    async def _fetch_show_direct(self, tmdb_id: int) -> ShowInfo | None:
        data = await self._tmdb_get(f"/tv/{tmdb_id}")
        if not data:
            return None
        show = ShowInfo(
            tmdb_id=tmdb_id,
            name=data.get("name", ""),
            year=(data.get("first_air_date") or "")[:4],
            poster=data.get("poster_path") or "",
        )
        for s in data.get("seasons", []):
            show.seasons.append(SeasonInfo(
                season_number=int(s.get("season_number") or 0),
                episode_count=int(s.get("episode_count") or 0),
            ))
        return show

    async def _fetch_episodes(self, tmdb_id: int, season: int, mode: str) -> list[EpisodeInfo] | None:
        """获取某一季的集列表"""
        if mode == "proxy":
            ok, data = await self.mp.tmdb_episodes(tmdb_id, season)
            if not ok or not isinstance(data, list):
                return None
            return [
                EpisodeInfo(
                    episode_number=int(e.get("episode_number", e.get("episodeNumber")) or 0),
                    air_date=str(e.get("air_date", e.get("airDate")) or ""),
                    name=str(e.get("name", "") or ""),
                )
                for e in data
                if int(e.get("episode_number", e.get("episodeNumber")) or 0) > 0
            ]
        data = await self._tmdb_get(f"/tv/{tmdb_id}/season/{season}")
        if not data:
            return None
        return [
            EpisodeInfo(
                episode_number=int(e.get("episode_number") or 0),
                air_date=str(e.get("air_date") or ""),
                name=str(e.get("name") or ""),
            )
            for e in data.get("episodes", [])
            if int(e.get("episode_number") or 0) > 0
        ]

    async def _tmdb_get(self, path: str) -> dict | None:
        """直连 TMDB 官方 API"""
        import asyncio
        url = _TMDB_API + path
        params = {"api_key": self.tmdb_key, "language": self.lang}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            await add_log("WARN", "scan", f"TMDB 直连查询失败：{e}")
            return None


# ========== 缓存序列化工具 ==========

def _show_to_json(show: ShowInfo) -> str:
    return json.dumps({
        "tmdb_id": show.tmdb_id, "name": show.name, "year": show.year,
        "poster": show.poster,
        "seasons": [{"season_number": s.season_number, "episode_count": s.episode_count}
                    for s in show.seasons],
    }, ensure_ascii=False)


def _show_from_json(text: str) -> ShowInfo:
    d = json.loads(text)
    show = ShowInfo(tmdb_id=int(d.get("tmdb_id") or 0),
                    name=d.get("name", ""), year=d.get("year", ""),
                    poster=d.get("poster", ""))
    for s in d.get("seasons", []):
        show.seasons.append(SeasonInfo(
            season_number=int(s.get("season_number") or 0),
            episode_count=int(s.get("episode_count") or 0),
        ))
    return show


def _eps_to_json(eps: list) -> str:
    return json.dumps([
        {"episode_number": e.episode_number, "air_date": e.air_date, "name": e.name}
        for e in eps
    ], ensure_ascii=False)


def _eps_from_json(text: str) -> list:
    return [
        EpisodeInfo(episode_number=int(e.get("episode_number") or 0),
                    air_date=str(e.get("air_date") or ""),
                    name=str(e.get("name") or ""))
        for e in json.loads(text)
    ]
