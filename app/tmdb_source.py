"""
============================================================
TMDB 数据源模块 - 负责获取"这部剧总共该有多少集"
============================================================
说明：
  - 缺集 = 应该有(来自TMDB) - 已有(来自扫描)
  - 数据源有两种，自动选择：
      1. MoviePilot 代理（推荐）：走 MP 的接口拿 TMDB 数据，
         小白不需要自己申请 TMDB API Key（MoviePilot v3 支持）
      2. TMDB 直连：填自己的 TMDB API Key（MP 老版本 v2 不支持代理时用）
  - 三级缓存（性能关键）：
      内存缓存（本次进程内）→ 数据库缓存（跨重启，落盘）→ 网络请求
    成功的数据永久落盘；网络失败时退回旧缓存数据（标记为旧数据），
    绝不会因为一次 API 故障就导致整部剧分析失败
  - 手动刷新：清空缓存后下次扫描重新获取最新数据（设置页有按钮）
============================================================
"""

import datetime
import json
import threading
import time

import httpx

from . import database, logger
from .models import EpisodeInfo, SeasonInfo, ShowInfo

# TMDB 直连的官方地址
_TMDB_API = "https://api.themoviedb.org/3"

# 请求超时（秒）
_TIMEOUT = 30

# 缓存有效期（秒）：24 小时内直接读缓存；超过后重新请求一次，
# 如果请求失败则退回旧缓存（数据不会丢失，只是标记为"旧数据"）
_CACHE_TTL = 24 * 3600

# season = -1 表示"剧信息"缓存（季列表用真实季号）
_SHOW_SEASON = -1


class TMDBSource:
    """
    TMDB 数据源（自动切换 代理/直连，带磁盘缓存）
    用法：
      src = TMDBSource(mp_client, tmdb_key, lang)
      show, stale = src.get_show(1399)              # 剧的信息（含所有季）
      eps, stale = src.get_season_episodes(1399, 1)  # 某一季的所有集
    stale=True 表示这次用的是"旧缓存数据"（网络失败时退回），数据可能不是最新
    """

    def __init__(self, mp_client=None, tmdb_key: str = "", lang: str = "zh-CN"):
        self.mp = mp_client            # MoviePilot 客户端（可能是 None）
        self.tmdb_key = tmdb_key       # TMDB API Key（直连用）
        self.lang = lang or "zh-CN"
        # 数据源模式：auto=自动探测 proxy=MP代理 direct=直连 none=没有可用数据源
        self.mode = "auto"
        self.mode_checked = False      # 是否已经探测过（只探测一次）
        self._mem_cache = {}           # 内存缓存：{"show:1399:-1": (时间, 数据)}
        self._lock = threading.Lock()
        # 共享 HTTP 客户端（复用连接，避免每个请求重新创建 SSL 上下文，性能差 10 倍）
        self._tmdb_http = None

    # ============================================================
    # 探测数据源（扫描开始时调用一次）
    # ============================================================

    def ensure_mode(self):
        """
        确定用哪种方式拿 TMDB 数据：
          1. 如果配了 MP 且 MP 支持代理接口 → 用代理（不用申请 Key）
          2. 否则如果配了 TMDB Key → 直连
          3. 都没有 → 无法工作，扫描会报中文提示
        """
        if self.mode_checked:
            return self.mode

        # 优先 MP 代理
        if self.mp and self.mp.url and self.mp.token:
            try:
                if self.mp.tmdb_supported():
                    self.mode = "proxy"
                    logger.log("INFO", "system", "TMDB 数据源：使用 MoviePilot 代理（无需 TMDB Key）")
                    self.mode_checked = True
                    return self.mode
                logger.log("INFO", "system", "MoviePilot 不支持 TMDB 代理接口（可能版本较老）")
            except Exception as e:
                logger.log("WARN", "system", f"探测 MoviePilot TMDB 代理失败：{e}")

        # 其次直连
        if self.tmdb_key:
            self.mode = "direct"
            logger.log("INFO", "system", "TMDB 数据源：使用直连（TMDB API Key）")
        else:
            self.mode = "none"
            logger.log("WARN", "system",
                       "没有可用的 TMDB 数据源：请升级 MoviePilot 到 v3，或在设置页填写 TMDB API Key")
        self.mode_checked = True
        return self.mode

    # ============================================================
    # 对外查询接口
    # ============================================================

    def get_show(self, tmdb_id: int):
        """
        获取一部剧的信息（剧名、年份、海报、所有季）
        返回：(ShowInfo 或 None, 是否旧缓存数据)
        失败且无旧缓存时返回 (None, False)
        """
        mode = self.ensure_mode()
        if mode == "none":
            return None, False
        return self._cached(
            "show", tmdb_id, _SHOW_SEASON,
            lambda: self._fetch_show(tmdb_id, mode),
            _show_to_json, _show_from_json,
        )

    def get_season_episodes(self, tmdb_id: int, season: int):
        """
        获取某一季的所有集（含没播出的，集号 + 播出日期）
        返回：(集列表 或 None, 是否旧缓存数据)
        失败且无旧缓存时返回 (None, False)
        """
        mode = self.ensure_mode()
        if mode == "none":
            return None, False
        return self._cached(
            "eps", tmdb_id, season,
            lambda: self._fetch_episodes(tmdb_id, season, mode),
            _eps_to_json, _eps_from_json,
        )

    def clear_cache(self, tmdb_id=None) -> int:
        """
        清空 TMDB 缓存（手动刷新用）：
          tmdb_id=None 清全部；否则只清这一部剧
        返回删除条数
        """
        if tmdb_id:
            count = database.execute("DELETE FROM tmdb_cache WHERE tmdb_id=?", (tmdb_id,))
        else:
            count = database.execute("DELETE FROM tmdb_cache")
        with self._lock:
            self._mem_cache.clear()
        return count

    # ============================================================
    # 三级缓存查询
    # ============================================================

    def _cached(self, kind: str, tmdb_id: int, season: int, fetch_func,
                to_json, from_json):
        """
        带缓存的查询：内存缓存 → 磁盘缓存 → 网络
        返回：(数据 或 None, is_stale)
          is_stale=True 表示网络请求失败，返回的是磁盘里的旧数据
        """
        key = f"{kind}:{tmdb_id}:{season}"
        now = time.time()

        # 1. 内存缓存（本进程内，最新）
        with self._lock:
            hit = self._mem_cache.get(key)
            if hit and now - hit[0] < _CACHE_TTL:
                return hit[1], False

        # 2. 磁盘缓存（跨重启，永久保存）
        cached_obj, cached_ts = self._load_cache(tmdb_id, season, from_json)
        if cached_obj is not None and cached_ts is not None \
                and now - cached_ts < _CACHE_TTL:
            with self._lock:
                self._mem_cache[key] = (time.time(), cached_obj)
            return cached_obj, False

        # 3. 需要重新请求（无缓存 / 缓存过期）
        try:
            data = fetch_func()
        except Exception as e:
            # 请求过程任何异常都视为"获取失败"→ 走旧缓存兜底
            # 绝不能让网络异常向上抛（那会导致整部剧分析失败）
            logger.log("WARN", "scan", f"TMDB 查询异常（{e}），尝试使用旧缓存数据")
            data = None
        if data is not None:
            self._save_cache(tmdb_id, season, to_json(data))
            with self._lock:
                self._mem_cache[key] = (time.time(), data)
            return data, False

        # 4. 网络失败：退回磁盘里的旧数据（不覆盖、不丢数据），标记为旧数据
        if cached_obj is not None:
            logger.log("WARN", "scan",
                       f"TMDB 查询失败，使用旧缓存数据（数据可能不是最新）：{key}")
            with self._lock:
                self._mem_cache[key] = (time.time(), cached_obj)
            return cached_obj, True

        return None, False

    def _load_cache(self, tmdb_id: int, season: int, from_json):
        """
        从数据库缓存读数据
        返回：(解析后的数据 或 None, 创建时间戳 或 None)
        """
        row = database.query_one(
            "SELECT response_json, created_at FROM tmdb_cache WHERE tmdb_id=? AND season=?",
            (tmdb_id, season))
        if not row:
            return None, None
        try:
            ts = datetime.datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            return from_json(row["response_json"]), time.mktime(ts.timetuple())
        except Exception:
            # 缓存数据损坏 → 当没有缓存处理（下次请求会重新写入）
            return None, None

    def _save_cache(self, tmdb_id: int, season: int, json_str: str):
        """把成功获取的数据写入磁盘缓存（只有成功的数据才写，失败绝不覆盖旧数据）"""
        database.execute(
            "INSERT OR REPLACE INTO tmdb_cache (tmdb_id, season, response_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (tmdb_id, season, json_str,
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

    # ============================================================
    # 具体请求（代理/直连两种实现）
    # ============================================================

    def _fetch_show(self, tmdb_id: int, mode: str) -> ShowInfo:
        """获取剧信息：代理模式用 MP 接口，直连模式用 TMDB 接口"""
        if mode == "proxy":
            return self._fetch_show_via_mp(tmdb_id)
        return self._fetch_show_direct(tmdb_id)

    def _fetch_show_via_mp(self, tmdb_id: int) -> ShowInfo:
        """
        通过 MoviePilot 代理获取剧信息
        注意：MP 的代理接口只返回"季列表"，剧名/年份/海报拿不到，
        所以这里只填季信息，剧名用扫描时拿到的目录名
        """
        ok, data = self.mp.tmdb_seasons(tmdb_id)
        if not ok or not isinstance(data, list):
            logger.log("WARN", "scan", f"获取剧 TMDB:{tmdb_id} 的季信息失败：{data}")
            return None
        show = ShowInfo(tmdb_id=tmdb_id)
        for s in data:
            # MP 返回的字段名做容错（不同版本可能略有不同）
            season_num = s.get("season_number", s.get("seasonNumber"))
            if season_num is None:
                continue
            show.seasons.append(SeasonInfo(
                season_number=int(season_num),
                episode_count=int(s.get("episode_count", s.get("episodeCount")) or 0),
            ))
        if not show.seasons:
            return None
        return show

    def _fetch_show_direct(self, tmdb_id: int) -> ShowInfo:
        """直连 TMDB 官方接口获取剧信息（有剧名/年份/海报）"""
        try:
            data = self._tmdb_get(f"/tv/{tmdb_id}")
        except Exception as e:
            logger.log("WARN", "scan", f"TMDB 查询剧 {tmdb_id} 失败：{e}")
            return None
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

    def _fetch_episodes(self, tmdb_id: int, season: int, mode: str) -> list:
        """获取一季的集列表（两种模式）"""
        if mode == "proxy":
            ok, data = self.mp.tmdb_episodes(tmdb_id, season)
            if not ok or not isinstance(data, list):
                logger.log("WARN", "scan", f"获取季 S{season}（TMDB:{tmdb_id}）的集数失败：{data}")
                return None
            eps = []
            for e in data:
                ep = EpisodeInfo(
                    episode_number=int(e.get("episode_number", e.get("episodeNumber")) or 0),
                    air_date=str(e.get("air_date", e.get("airDate")) or ""),
                    name=str(e.get("name", "") or ""),
                )
                if ep.episode_number > 0:
                    eps.append(ep)
            return eps
        try:
            data = self._tmdb_get(f"/tv/{tmdb_id}/season/{season}")
        except Exception as e:
            logger.log("WARN", "scan", f"TMDB 查询 S{season}（{tmdb_id}）失败：{e}")
            return None
        if not data:
            return None
        eps = []
        for e in data.get("episodes", []):
            ep = EpisodeInfo(
                episode_number=int(e.get("episode_number") or 0),
                air_date=str(e.get("air_date") or ""),
                name=str(e.get("name") or ""),
            )
            if ep.episode_number > 0:
                eps.append(ep)
        return eps

    def _tmdb_get(self, path: str) -> dict:
        """直连 TMDB 官方 API（GET 请求，带 api_key）"""
        if self._tmdb_http is None:
            self._tmdb_http = httpx.Client(timeout=_TIMEOUT)
        resp = self._tmdb_http.get(
            _TMDB_API + path,
            params={"api_key": self.tmdb_key, "language": self.lang},
        )
        resp.raise_for_status()
        return resp.json()


# ============================================================
# 缓存序列化工具（磁盘缓存里存的是 JSON 字符串）
# ============================================================

def _show_to_json(show: ShowInfo) -> str:
    return json.dumps({
        "tmdb_id": show.tmdb_id,
        "name": show.name,
        "year": show.year,
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


# ============================================================
# 小工具：判断一集是否"已播出"（防止把没播的集当缺集）
# ============================================================

def is_aired(episode: EpisodeInfo, today: datetime.date) -> bool:
    """一集是否已播出：有播出日期且不晚于今天"""
    if not episode.air_date:
        return False
    try:
        air = datetime.date.fromisoformat(episode.air_date[:10])
        return air <= today
    except ValueError:
        # 日期格式不对就当已播出，宁多勿漏
        return True
