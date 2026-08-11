"""
============================================================
TMDB 磁盘缓存测试
运行方法：在项目根目录执行  python -m pytest tests/test_tmdb_cache.py -v

覆盖：
  - 成功数据落盘（下次直接读缓存，不重复请求）
  - 重启（新实例）后缓存仍然可用
  - API 失败绝不覆盖旧数据（退回旧数据 + 标记 stale）
  - 清空缓存后重新请求
  - 序列化往返正确（剧信息 / 集列表）
============================================================
"""

import datetime
import os
import tempfile

import pytest

from app import database as _db
from app.models import EpisodeInfo, SeasonInfo, ShowInfo
from app.tmdb_source import TMDBSource, _eps_from_json, _eps_to_json, _show_from_json, _show_to_json


@pytest.fixture()
def tmp_db():
    """把数据库指到全新临时目录（测完恢复）"""
    tmp = tempfile.mkdtemp()
    saved = (_db.DATA_DIR, _db.DB_PATH)
    _db.DATA_DIR = tmp
    _db.DB_PATH = os.path.join(tmp, "queji.db")
    _db.close_thread_connections()
    _db.init_db()
    yield
    _db.DATA_DIR, _db.DB_PATH = saved
    _db.close_thread_connections()


def _make_show():
    return ShowInfo(tmdb_id=1399, name="权力的游戏", year="2011", poster="/x.jpg",
                    seasons=[SeasonInfo(1, 10), SeasonInfo(2, 8)])


def _make_eps():
    return [EpisodeInfo(n, "2024-01-01", f"EP{n}") for n in (1, 2, 3)]


class TestTmdbCache:
    def test_01_save_and_read_from_disk(self, tmp_db):
        """成功数据落盘：第二次查询走磁盘缓存，不再请求网络"""
        src = TMDBSource(None, "")
        calls = []

        def fetch():
            calls.append(1)
            return _make_show()

        data, stale = src._cached("show", 1399, -1, fetch, _show_to_json, _show_from_json)
        assert stale is False
        data2, stale2 = src._cached("show", 1399, -1, fetch, _show_to_json, _show_from_json)
        assert len(calls) == 1          # 第二次没再请求
        assert stale2 is False
        assert data2.name == "权力的游戏"
        assert len(data2.seasons) == 2

    def test_02_cache_survives_restart(self, tmp_db):
        """模拟程序重启（新实例）：磁盘缓存仍然有效"""
        src1 = TMDBSource(None, "")
        src1._cached("eps", 1399, 1, lambda: _make_eps(), _eps_to_json, _eps_from_json)

        src2 = TMDBSource(None, "")     # 全新实例 = 内存缓存已丢失
        calls = []

        def fetch():
            calls.append(1)
            return _make_eps()

        data, stale = src2._cached("eps", 1399, 1, fetch, _eps_to_json, _eps_from_json)
        assert stale is False
        assert len(calls) == 0          # 没发网络请求，读的磁盘缓存
        assert [e.episode_number for e in data] == [1, 2, 3]

    def test_03_fail_never_overwrites_old_data(self, tmp_db):
        """API 失败：不覆盖旧数据，退回旧缓存并标记 stale"""
        src1 = TMDBSource(None, "")
        src1._cached("eps", 5, 1, lambda: _make_eps(), _eps_to_json, _eps_from_json)

        # 把缓存改成 25 小时前（过期 → 才会触发重新请求）
        old = (datetime.datetime.now() - datetime.timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        _db.execute("UPDATE tmdb_cache SET created_at=? WHERE tmdb_id=5 AND season=1", (old,))

        src2 = TMDBSource(None, "")

        def bad_fetch():
            raise RuntimeError("network down")

        data, stale = src2._cached("eps", 5, 1, bad_fetch, _eps_to_json, _eps_from_json)
        assert stale is True            # 明确标记：这是旧数据
        assert data is not None         # 数据没丢
        assert data[0].episode_number == 1

    def test_04_fail_with_no_cache_returns_none(self, tmp_db):
        """API 失败且没有旧缓存：返回 None（调用方标记该剧为 error）"""
        src = TMDBSource(None, "")

        def bad_fetch():
            raise RuntimeError("network down")

        data, stale = src._cached("eps", 999, 1, bad_fetch, _eps_to_json, _eps_from_json)
        assert data is None
        assert stale is False

    def test_05_clear_cache(self, tmp_db):
        """清空缓存后重新请求（手动刷新用）"""
        src = TMDBSource(None, "")
        calls = []

        def fetch():
            calls.append(1)
            return _make_show()

        src._cached("show", 1399, -1, fetch, _show_to_json, _show_from_json)
        assert calls == [1]
        src._cached("show", 1399, -1, fetch, _show_to_json, _show_from_json)
        assert calls == [1]             # 缓存命中

        n = src.clear_cache(1399)       # 只清这一部
        assert n >= 1
        src._cached("show", 1399, -1, fetch, _show_to_json, _show_from_json)
        assert len(calls) == 2          # 重新请求了

    def test_06_show_roundtrip(self):
        """剧信息序列化往返"""
        show = _make_show()
        back = _show_from_json(_show_to_json(show))
        assert back.tmdb_id == 1399
        assert back.name == "权力的游戏"
        assert back.year == "2011"
        assert back.poster == "/x.jpg"
        assert [(s.season_number, s.episode_count) for s in back.seasons] == [(1, 10), (2, 8)]

    def test_07_eps_roundtrip(self):
        """集列表序列化往返"""
        eps = _make_eps()
        back = _eps_from_json(_eps_to_json(eps))
        assert [(e.episode_number, e.air_date, e.name) for e in back] == \
               [(1, "2024-01-01", "EP1"), (2, "2024-01-01", "EP2"), (3, "2024-01-01", "EP3")]

    def test_08_fresh_cache_within_ttl_no_refetch(self, tmp_db):
        """24 小时内：即使实例更换，也直接读缓存，不发请求"""
        src1 = TMDBSource(None, "")
        src1._cached("eps", 7, 1, lambda: _make_eps(), _eps_to_json, _eps_from_json)

        src2 = TMDBSource(None, "")
        calls = []

        def fetch():
            calls.append(1)
            return _make_eps()

        data, stale = src2._cached("eps", 7, 1, fetch, _eps_to_json, _eps_from_json)
        assert len(calls) == 0
        assert stale is False
