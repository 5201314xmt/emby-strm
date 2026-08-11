"""
============================================================
数据模型模块 - 定义程序中用到的数据结构
============================================================
说明：
  - 用简单的 dataclass（数据类）定义结构，比到处用字典更清晰、不易出错
  - 扫描器返回这些对象，分析器使用这些对象，前端接口也基于它们
============================================================
"""

from dataclasses import dataclass, field


@dataclass
class EpisodeInfo:
    """
    一集剧的信息（来自 TMDB）
    """
    episode_number: int = 0        # 集号（第几集）
    air_date: str = ""             # 播出日期 "2024-01-01"，没播出为空
    name: str = ""                 # 集名


@dataclass
class SeasonInfo:
    """
    一季剧的信息（来自 TMDB）
    """
    season_number: int = 0         # 季号（0=特别篇）
    episode_count: int = 0         # 这一季一共有多少集（含未播出）


@dataclass
class ShowInfo:
    """
    一部剧的基本信息（来自 TMDB）
    """
    tmdb_id: int = 0               # TMDB 编号
    name: str = ""                 # 剧名
    year: str = ""                 # 年份
    poster: str = ""               # 海报地址（可空）
    seasons: list = field(default_factory=list)   # 所有季的列表 [SeasonInfo]


@dataclass
class ScanResult:
    """
    一次扫描的原始结果（"目前有哪些集"）
    """
    shows: dict = field(default_factory=dict)
    # shows 的结构：
    #   { tmdb_id: {
    #        "name": "剧名（目录名）",
    #        "seasons": { 季号: [已有集号...] }
    #     }
    #   }

    unrecognized: list = field(default_factory=list)
    # 未识别出的内容：[{"path": 路径, "reason": 原因}]


# ============================================================
# 季的状态常量（存数据库用）
# ============================================================
SEASON_COMPLETE = "complete"       # 这一季集数完整，没有缺
SEASON_PARTIAL = "partial"         # 缺了一部分集
SEASON_FULL_MISSING = "full_missing"  # 整季都没有

# 订阅状态（MoviePilot 的订阅状态）
SUB_STATE_WAIT = "R"      # R = 等待中（订阅了还没搜索）
SUB_STATE_SEARCH = "S"    # S = 搜索中（正在找资源）
SUB_STATE_DONE = "P"      # P = 已完成（下载齐全）
