"""
============================================================
缺集计算单元测试
运行方法：在项目根目录执行  python -m pytest tests -v
============================================================
"""

import datetime

from app.analyzer import analyze_season, build_fallback_episodes
from app.models import EpisodeInfo

# 固定"今天"的日期，保证测试结果稳定
TODAY = datetime.date(2024, 6, 1)


def _ep(num, air_date="2024-01-01"):
    """快速生成一集 EpisodeInfo"""
    return EpisodeInfo(episode_number=num, air_date=air_date)


# ------------------------------------------------------------

class TestAnalyzeSeason:
    def test_missing_some(self):
        """已有 1,2,4，应有 1-6 → 缺 3,5,6，状态 partial"""
        eps = [_ep(n) for n in range(1, 7)]
        r = analyze_season(1, eps, [1, 2, 4], TODAY)
        assert r["missing_episodes"] == [3, 5, 6]
        assert r["present_episodes"] == [1, 2, 4]
        assert r["status"] == "partial"
        assert r["aired_episodes"] == 6

    def test_complete(self):
        """全集都有 → complete"""
        eps = [_ep(n) for n in range(1, 4)]
        r = analyze_season(1, eps, [1, 2, 3], TODAY)
        assert r["status"] == "complete"
        assert r["missing_episodes"] == []

    def test_full_missing(self):
        """一集都没有 → full_missing"""
        eps = [_ep(n) for n in range(1, 6)]
        r = analyze_season(2, eps, [], TODAY)
        assert r["status"] == "full_missing"
        assert r["missing_episodes"] == [1, 2, 3, 4, 5]

    def test_not_aired_yet(self):
        """整季都还没播出（播出日期在未来）→ 返回 None，不参与计算"""
        eps = [_ep(n, air_date="2025-01-01") for n in range(1, 5)]
        r = analyze_season(3, eps, [], TODAY)
        assert r is None

    def test_mixed_air_dates(self):
        """只有已播出的算缺集：5 集里 2 集没播 → 只算 3 集"""
        eps = [_ep(1), _ep(2), _ep(3), _ep(4, air_date="2025-01-01"), _ep(5, air_date="2025-01-01")]
        r = analyze_season(1, eps, [1], TODAY)
        assert r["aired_episodes"] == 3
        assert r["missing_episodes"] == [2, 3]

    def test_empty_air_date(self):
        """没有播出日期的集不算已播出"""
        eps = [_ep(1, air_date=""), _ep(2, air_date="2024-01-01")]
        r = analyze_season(1, eps, [], TODAY)
        assert r["aired_episodes"] == 1
        assert r["missing_episodes"] == [2]


class TestFallbackEpisodes:
    def test_build(self):
        """兜底集列表：1..N 全部算已播出"""
        eps = build_fallback_episodes(1, 5)
        assert len(eps) == 5
        r = analyze_season(1, eps, [1, 2], TODAY)
        assert r["missing_episodes"] == [3, 4, 5]
