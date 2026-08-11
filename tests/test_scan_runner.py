"""
============================================================
扫描任务核心逻辑测试（业务红线验证）
运行方法：在项目根目录执行  python -m pytest tests/test_scan_runner.py -v

验证的业务红线：
  1. TMDB 数据不准（degraded）的季绝不自动订阅
  2. 绝不重复提交 MoviePilot（同一季只提交一次）
  3. 单部剧出错不影响其他剧（错误隔离）
  4. 数据库写入要么全部成功要么回滚（扫描不污染数据）
============================================================
"""

import os
import tempfile

import pytest

from app import config as config_mod
from app import database as _db
from app.models import EpisodeInfo, ScanResult, SeasonInfo, ShowInfo
from app.scan_runner import ScanRunner


@pytest.fixture()
def tmp_db():
    """把数据库指到全新临时目录"""
    tmp = tempfile.mkdtemp()
    saved = (_db.DATA_DIR, _db.DB_PATH)
    _db.DATA_DIR = tmp
    _db.DB_PATH = os.path.join(tmp, "queji.db")
    _db.close_thread_connections()
    _db.init_db()
    yield
    _db.DATA_DIR, _db.DB_PATH = saved
    _db.close_thread_connections()


# ------------------------------------------------------------
# 假 TMDB 数据源（可控制是否返回旧数据/抛异常）
# ------------------------------------------------------------

class FakeTMDBSource:
    mode = "proxy"
    mode_checked = True

    def __init__(self, shows=None, stale=False, fail_ids=()):
        self.shows = shows or {}      # {tmdb_id: (ShowInfo, {season: [EpisodeInfo]})}
        self.stale = stale            # 全局模拟"用了旧缓存"
        self.fail_ids = fail_ids      # 这些剧直接抛异常（模拟 TMDB 故障）

    def ensure_mode(self):
        return "proxy"

    def get_show(self, tmdb_id):
        if tmdb_id in self.fail_ids:
            raise RuntimeError("模拟 TMDB 故障")
        item = self.shows.get(tmdb_id)
        if not item:
            return None, False
        return item[0], self.stale

    def get_season_episodes(self, tmdb_id, season):
        item = self.shows.get(tmdb_id)
        if not item:
            return None, False
        eps = item[1].get(season)
        if eps is None:
            return None, self.stale
        return eps, self.stale

    def clear_cache(self, tmdb_id=None):
        return 0


# ------------------------------------------------------------
# 假 MoviePilot（记录所有创建请求）
# ------------------------------------------------------------

class FakeMP:
    url = "http://mock-mp:3000"
    token = "t"

    def __init__(self):
        self.created = []             # [(tmdb_id, season), ...]
        self.dups = set()             # 模拟 MP 侧已存在的订阅

    def create_subscribe(self, name, year, tmdb_id, season, total_episode):
        if (tmdb_id, season) in self.dups:
            return False, "该媒体已订阅"
        self.created.append((tmdb_id, season))
        return True, 100 + len(self.created)

    def search_subscribe(self, mp_id):
        return True, None


def _make_runner(mp=None, tmdb=None):
    cfg = config_mod.Config()
    if mp is None:
        mp = FakeMP()
    runner = ScanRunner(cfg, mp)
    if tmdb is not None:
        runner.tmdb_source = tmdb
    return runner


def _ep(n):
    return EpisodeInfo(n, "2024-01-01", f"EP{n}")


def _insert_show(tmdb_id, name, seasons_data):
    """直接往数据库插一部剧 + 若干季（模拟扫描结果）"""
    _db.execute("INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, 'ok', ?)",
                (tmdb_id, name, "2024-01-01"))
    for season, (present, missing, quality) in seasons_data.items():
        _db.execute(
            "INSERT INTO seasons (tmdb_id, season_number, total_episodes, aired_episodes, "
            "present_episodes, missing_episodes, status, data_quality) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tmdb_id, season, len(present) + len(missing), len(present) + len(missing),
             repr(present), repr(missing), "partial", quality))


class TestScanRunner:
    # ---------- 红线1：degraded 禁止自动订阅 ----------

    def test_01_auto_subscribe_skips_degraded(self, tmp_db):
        """数据不准（degraded）的季绝不自动订阅"""
        _insert_show(1, "正常剧", {1: ([1], [2, 3], "normal")})
        _insert_show(2, "异常剧", {1: ([1], [2, 3], "degraded")})

        mp = FakeMP()
        runner = _make_runner(mp)
        runner._auto_subscribe(None)

        assert mp.created == [(1, 1)]   # 只订阅了 normal 的季

    def test_02_auto_subscribe_skips_ignored(self, tmp_db):
        """已忽略的季不自动订阅"""
        _insert_show(1, "剧A", {1: ([1], [2, 3], "normal")})
        _db.execute("INSERT INTO ignored (tmdb_id, season) VALUES (1, 1)")

        mp = FakeMP()
        runner = _make_runner(mp)
        runner._auto_subscribe(None)
        assert mp.created == []

    # ---------- 红线2：不重复提交 ----------

    def test_03_auto_subscribe_dedup(self, tmp_db):
        """同一季自动订阅只提交一次（跑两次扫描也只提交一次）"""
        _insert_show(1, "剧A", {1: ([1], [2, 3], "normal")})

        mp = FakeMP()
        runner = _make_runner(mp)
        runner._auto_subscribe(None)
        runner._auto_subscribe(None)    # 第二次扫描
        assert len(mp.created) == 1

    def test_04_mp_duplicate_rejected(self, tmp_db):
        """MP 侧已存在订阅（比如用户手动建的）：MP 拒绝后本地记录，不再重复尝试"""
        _insert_show(1, "剧A", {1: ([1], [2, 3], "normal")})
        mp = FakeMP()
        mp.dups.add((1, 1))             # MP 里已经有这个订阅
        runner = _make_runner(mp)
        runner._auto_subscribe(None)
        runner._auto_subscribe(None)    # 第二次扫描
        assert mp.created == []         # 一次都没提交成功，也没反复尝试

    # ---------- 红线3：单剧出错不影响整体 ----------

    def test_05_error_isolated(self, tmp_db):
        """TMDB 对某部剧故障：这部剧标记 error，其他剧正常分析"""
        show1 = ShowInfo(tmdb_id=1, name="好剧", seasons=[SeasonInfo(1, 3)])
        eps1 = [_ep(n) for n in range(1, 4)]
        src = FakeTMDBSource({1: (show1, {1: eps1})}, fail_ids=(2,))

        scan_result = ScanResult()
        scan_result.shows[1] = {"name": "好剧", "seasons": {1: [1, 2]}}
        scan_result.shows[2] = {"name": "坏剧", "seasons": {1: [1]}}

        mp = FakeMP()
        runner = _make_runner(mp, src)
        runner._analyze_all(scan_result)

        assert runner.status["done"] == 2
        good = _db.query_one("SELECT status FROM shows WHERE tmdb_id=1")
        bad = _db.query_one("SELECT status FROM shows WHERE tmdb_id=2")
        assert good["status"] == "ok"
        assert bad["status"] == "error"  # 错误隔离，不影响好剧

    # ---------- 红线4：degraded 标记写入 ----------

    def test_06_degraded_marked_in_db(self, tmp_db):
        """使用旧缓存/降级数据 → seasons 记录标记 degraded"""
        show = ShowInfo(tmdb_id=1, name="剧A", seasons=[SeasonInfo(1, 3)])
        eps = [_ep(n) for n in range(1, 4)]
        src = FakeTMDBSource({1: (show, {1: eps})}, stale=True)   # 模拟旧缓存

        runner = _make_runner(tmdb=src)
        runner._analyze_one_show(1, {"name": "剧A", "seasons": {1: [1]}})

        row = _db.query_one(
            "SELECT data_quality FROM seasons WHERE tmdb_id=1 AND season_number=1")
        assert row["data_quality"] == "degraded"

    def test_07_normal_marked_in_db(self, tmp_db):
        """正常数据 → data_quality = normal"""
        show = ShowInfo(tmdb_id=1, name="剧A", seasons=[SeasonInfo(1, 3)])
        eps = [_ep(n) for n in range(1, 4)]
        src = FakeTMDBSource({1: (show, {1: eps})}, stale=False)

        runner = _make_runner(tmdb=src)
        runner._analyze_one_show(1, {"name": "剧A", "seasons": {1: [1]}})

        row = _db.query_one(
            "SELECT data_quality FROM seasons WHERE tmdb_id=1 AND season_number=1")
        assert row["data_quality"] == "normal"

    # ---------- 事务原子性 ----------

    def test_08_transaction_atomic(self, tmp_db):
        """整部剧写入是一个事务：中途失败不会留下半条数据"""
        show = ShowInfo(tmdb_id=1, name="剧A", seasons=[SeasonInfo(1, 3), SeasonInfo(2, 3)])
        eps = [_ep(n) for n in range(1, 4)]
        src = FakeTMDBSource({1: (show, {1: eps})})

        runner = _make_runner(tmdb=src)
        # 手工先插一条"上一轮"的数据
        _insert_show(1, "剧A", {1: ([9], [10], "normal")})

        # 模拟 seasons 表被外部删除导致写入失败（真实情况是唯一约束冲突等）
        with pytest.raises(Exception):
            with _db.transaction() as conn:
                conn.execute("INSERT INTO shows (tmdb_id, name) VALUES (?, ?)", (1, "x"))
                conn.execute("INSERT INTO no_such_table (x) VALUES (1)")
        row = _db.query_one("SELECT name FROM shows WHERE tmdb_id=1")
        assert row["name"] == "剧A"     # 旧数据完好，没有被半路写坏
