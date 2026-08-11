"""
全局应用状态 —— 跨模块共享的实例

存放 MoviePilot 客户端和 TMDB 数据源的全局引用，
所有 API 路由和后台任务通过此模块获取统一实例。

设置保存后调用 reload_clients() 即可热更新。
"""
from ..services.moviepilot import MoviePilotClient
from ..services.tmdb import TMDBSource
from ..config import settings as app_settings

# ---- 共享客户端实例 ----
mp_client: MoviePilotClient = None
tmdb_source: TMDBSource = None


def init_clients():
    """应用启动时初始化所有客户端（从 DB 配置读取）"""
    global mp_client, tmdb_source
    mp_client = MoviePilotClient()
    tmdb_source = TMDBSource(mp_client, app_settings.tmdb_key, app_settings.tmdb_lang)


def reload_clients():
    """设置保存后调用，让新配置立即生效"""
    global mp_client, tmdb_source
    mp_client = MoviePilotClient()
    tmdb_source = TMDBSource(mp_client, app_settings.tmdb_key, app_settings.tmdb_lang)


def get_auto_subscribe() -> bool:
    """读取自动订阅开关"""
    return app_settings.auto_subscribe


def get_include_specials() -> bool:
    """读取是否包含特别篇"""
    return app_settings.include_specials
