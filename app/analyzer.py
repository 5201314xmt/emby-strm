"""
============================================================
缺集计算模块 - 对比"应该有"和"已有"，算出缺哪些集
============================================================
说明：
  - 输入：TMDB 该季的全部集（应该有） + 扫描到的集（已有）
  - 输出：缺集列表和状态（写入数据库，网页展示）
  - 这里的函数是"纯计算"，不碰网络不碰数据库，方便测试
============================================================
"""

import datetime

from .models import (
    SEASON_COMPLETE, SEASON_PARTIAL, SEASON_FULL_MISSING,
    EpisodeInfo,
)
from .tmdb_source import is_aired


def analyze_season(season_number: int, episodes: list, present_eps: list,
                   today: datetime.date = None, data_quality: str = "normal") -> dict:
    """
    计算某一季的缺集情况

    参数：
      season_number 季号
      episodes      TMDB 里这一季的全部集（EpisodeInfo 列表，含播出日期）
      present_eps   扫描到的已有集号列表，如 [1,2,3]
      today         今天的日期（测试时可传入固定日期）
      data_quality  数据质量：normal=正常  degraded=用了旧缓存/降级估算

    返回：
      {
        "season_number": 1,
        "total_episodes": 10,      # TMDB 全集数（含未播出）
        "aired_episodes": 9,       # 已播出的集数
        "present_episodes": [...], # 已有的集号
        "missing_episodes": [...], # 缺的集号（已播出但库里没有）
        "status": "partial",       # complete=完整 partial=缺部分 full_missing=整季缺失
        "data_quality": "normal",  # normal=正常数据 degraded=数据可能不准
      }
      如果这一季一集都还没播出（未开播），返回 None（不需要关注）
    """
    today = today or datetime.date.today()

    # 1. 只算已播出的集（没播出的不算缺集，避免误订阅）
    aired_nums = [e.episode_number for e in episodes if is_aired(e, today)]

    # 2. 如果这一季还没开播（一集都没播），直接跳过
    if not aired_nums:
        return None

    aired_set = set(aired_nums)
    present_set = set(int(e) for e in (present_eps or []))

    # 3. 缺集 = 已播出 - 已有；已有的集也只统计在已播出范围内
    missing = sorted(aired_set - present_set)
    present_in_range = sorted(aired_set & present_set)

    # 4. 判断这一季的状态
    if not missing:
        status = SEASON_COMPLETE
    elif not present_in_range:
        status = SEASON_FULL_MISSING
    else:
        status = SEASON_PARTIAL

    return {
        "season_number": season_number,
        "total_episodes": len(episodes),
        "aired_episodes": len(aired_set),
        "present_episodes": present_in_range,
        "missing_episodes": missing,
        "status": status,
        "data_quality": data_quality,
    }


def build_fallback_episodes(season_number: int, episode_count: int) -> list:
    """
    生成"退化版"集列表（TMDB 查询失败时的兜底方案）：
    假设从第 1 集到 episode_count 连续。
    播出日期统一填 2000-01-01（表示早已播出），
    这样这些集都会被当作已播出参与缺集计算（宁多勿漏）。
    只在数据源临时故障时使用，属正常降级。
    """
    return [EpisodeInfo(episode_number=n, air_date="2000-01-01", name="")
            for n in range(1, episode_count + 1)]
