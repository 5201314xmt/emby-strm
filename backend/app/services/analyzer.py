"""
缺集计算引擎 —— 对比"应该有"和"已有"，算出缺哪些集

核心算法：
  已播出集 = TMDB 全部集 中 排除 未播出（播出日期 > 今天）
  缺集     = 已播出集 - 已有集
  状态     = complete（完整）/ partial（缺部分）/ full_missing（整季缺失）

数据质量分级：
  normal   — 数据来源可靠，可以自动订阅
  degraded — 用了旧缓存或降级估算，禁止自动订阅（但手动可以）

未开播的季返回 None（不参加缺集计算，不需要关注）
"""
from datetime import date, datetime

from .tmdb_models import EpisodeInfo

# 季状态常量
SEASON_COMPLETE = "complete"       # 这一季集数完整
SEASON_PARTIAL = "partial"         # 缺了一部分集
SEASON_FULL_MISSING = "full_missing"  # 整季都没有

# 数据质量常量
QUALITY_NORMAL = "normal"      # 数据可靠
QUALITY_DEGRADED = "degraded"  # 数据可能不准（旧缓存/降级估算）


def is_aired(episode: EpisodeInfo, today: date) -> bool:
    """
    判断一集是否已播出

    有播出日期且不晚于今天 → 已播出。
    没有播出日期 → 当做未播出（可能是未来要播的，先不算缺集）。
    日期格式异常 → 当做已播出（宁多勿漏）。
    """
    if not episode.air_date:
        return False
    try:
        air = date.fromisoformat(episode.air_date[:10])
        return air <= today
    except (ValueError, TypeError):
        return True   # 日期不对就当已播出，宁多勿漏


def analyze_season(
    season_number: int,
    episodes: list[EpisodeInfo],
    present_eps: list[int],
    today: date = None,
    data_quality: str = QUALITY_NORMAL,
) -> dict | None:
    """
    计算某一季的缺集情况

    Args:
        season_number: 季号
        episodes:      TMDB 里这一季的全部集（EpisodeInfo 列表）
        present_eps:   扫描到的已有集号列表，如 [1, 2, 3]
        today:         今天的日期（测试时可传入固定日期）
        data_quality:  数据质量标记

    Returns:
        {
            "season_number": 1,
            "total_episodes": 10,       # TMDB 全集数（含未播出）
            "aired_episodes": 9,        # 已播出的集数
            "present_episodes": [1,2],  # 已有的集号（只在已播出范围内）
            "missing_episodes": [3,4],  # 缺的集号（已播出但库里没有）
            "status": "partial",        # complete / partial / full_missing
            "data_quality": "normal",   # normal / degraded
        }
        如果这一季还没开播（一集都没播），返回 None
    """
    today = today or date.today()

    # 1. 只算已播出的集
    aired_nums = [e.episode_number for e in episodes if is_aired(e, today)]

    # 2. 还没开播的季直接跳过
    if not aired_nums:
        return None

    aired_set = set(aired_nums)
    present_set = set(int(e) for e in (present_eps or []))

    # 3. 缺集 = 已播出 - 已有
    missing = sorted(aired_set - present_set)
    present_in_range = sorted(aired_set & present_set)

    # 4. 判断状态
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


def build_fallback_episodes(season_number: int, episode_count: int) -> list[EpisodeInfo]:
    """
    生成"退化版"集列表（TMDB 查询失败时的兜底方案）

    假设集号 1..episode_count 连续，播出日期填 2000-01-01（表示早已播出）。
    这样所有集都被当作已播出参与缺集计算（宁多勿漏）。
    只在数据源临时故障时使用。
    """
    return [
        EpisodeInfo(episode_number=n, air_date="2000-01-01", name="")
        for n in range(1, episode_count + 1)
    ]
