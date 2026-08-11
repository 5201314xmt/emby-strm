"""
TMDB 数据模型 —— 剧中信息的 dataclass

这些只是纯数据结构，不包含业务逻辑。
"""
from dataclasses import dataclass, field


@dataclass
class EpisodeInfo:
    """一集剧的信息（来自 TMDB）"""
    episode_number: int = 0    # 集号
    air_date: str = ""          # 播出日期 "2024-01-01"
    name: str = ""              # 集名


@dataclass
class SeasonInfo:
    """一季剧的信息（来自 TMDB）"""
    season_number: int = 0     # 季号（0=特别篇）
    episode_count: int = 0     # 这一季一共有多少集（含未播出）


@dataclass
class ShowInfo:
    """一部剧的基本信息（来自 TMDB）"""
    tmdb_id: int = 0           # TMDB 编号
    name: str = ""             # 剧名
    year: str = ""             # 首播年份
    poster: str = ""           # 海报路径
    seasons: list = field(default_factory=list)  # [SeasonInfo, ...]
