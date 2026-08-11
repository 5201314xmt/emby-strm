"""
============================================================
数据库结构 / 迁移测试
运行方法：在项目根目录执行  python -m pytest tests/test_database.py -v

覆盖：
  - 新库结构完整（8 张表）
  - WAL 模式开启
  - 索引设计（seasons.status / subscribe_map 唯一约束）
  - 订阅唯一约束生效（拒绝重复行）
  - 旧库自动升级（去重 + 索引 + WAL）
  - 升级前自动备份
  - 已是最新版本不重复升级
  - 现有代码的 SQL 完全兼容
============================================================
"""

import os
import sqlite3
import tempfile

import pytest

from app import database as _db
from app import migrations

TABLES = ("settings", "shows", "seasons", "ignored",
          "subscribe_map", "logs", "unrecognized", "sessions")


@pytest.fixture()
def tmp_db():
    """把数据库指到全新临时目录（测完自动恢复，不影响开发库）"""
    tmp = tempfile.mkdtemp()
    saved = (_db.DATA_DIR, _db.DB_PATH)
    _db.DATA_DIR = tmp
    _db.DB_PATH = os.path.join(tmp, "queji.db")
    _db.close_thread_connections()
    yield tmp
    _db.DATA_DIR, _db.DB_PATH = saved
    _db.close_thread_connections()


def _connect():
    return sqlite3.connect(_db.DB_PATH)


class TestDatabase:
    def test_01_fresh_db_has_all_tables(self, tmp_db):
        """新库：8 张表全部建好"""
        _db.init_db()
        conn = _connect()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        for t in TABLES:
            assert t in tables, f"缺少表 {t}"

    def test_02_wal_mode_enabled(self, tmp_db):
        """WAL 模式开启（读写互不阻塞）"""
        _db.init_db()
        conn = _connect()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_03_indexes_created(self, tmp_db):
        """索引设计：seasons.status 查询索引 + subscribe_map 唯一约束"""
        _db.init_db()
        conn = _connect()
        idx_seasons = {r[1] for r in conn.execute("PRAGMA index_list('seasons')")}
        idx_sub = {r[1] for r in conn.execute("PRAGMA index_list('subscribe_map')")}
        # seasons 唯一约束（已有）+ status 查询索引（新增）
        assert "idx_seasons_status" in idx_seasons
        # subscribe_map 唯一约束
        assert "idx_subscribe_map_unique" in idx_sub
        uniq_cols = [r[2] for r in conn.execute(
            "PRAGMA index_info('idx_subscribe_map_unique')")]
        conn.close()
        assert uniq_cols == ["tmdb_id", "season"]

    def test_04_subscribe_map_unique_enforced(self, tmp_db):
        """唯一约束生效：同一 (tmdb_id, season) 不能插第二行"""
        _db.init_db()
        conn = _connect()
        conn.execute(
            "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
            "VALUES (1, 1, 10, '剧A', 'R', '2024-01-01')")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
                "VALUES (1, 1, 20, '剧A', 'S', '2024-01-01')")
            conn.commit()
        conn.close()

    def test_05_old_db_auto_upgrade_dedupe(self, tmp_db):
        """旧库（只有 v1 结构）自动升级：重复订阅记录被去重 + 索引建好"""
        conn = _connect()
        conn.executescript(migrations.MIGRATIONS[0]["sql"])
        # 塞两条重复的订阅记录（旧版本的常见残留）
        conn.execute(
            "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
            "VALUES (1, 1, 10, '剧A', 'R', '2024-01-01')")
        conn.execute(
            "INSERT INTO subscribe_map (tmdb_id, season, mp_id, name, state, created_at) "
            "VALUES (1, 1, 20, '剧A', 'S', '2024-01-01')")
        conn.commit()
        conn.close()

        _db.init_db()  # 触发自动迁移

        conn = _connect()
        rows = conn.execute("SELECT COUNT(*) FROM subscribe_map").fetchone()[0]
        assert rows == 1  # 只保留最早一条
        idx_sub = {r[1] for r in conn.execute("PRAGMA index_list('subscribe_map')")}
        assert "idx_subscribe_map_unique" in idx_sub
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_06_upgrade_creates_backup(self, tmp_db):
        """旧库升级前自动备份（回滚方案的基础）"""
        conn = _connect()
        conn.executescript(migrations.MIGRATIONS[0]["sql"])
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        _db.init_db()

        backup_dir = os.path.join(tmp_db, "backups")
        files = os.listdir(backup_dir) if os.path.exists(backup_dir) else []
        assert len(files) == 1
        assert files[0].startswith("database_backup_")

    def test_07_fresh_db_no_backup(self, tmp_db):
        """全新库不需要备份（没有旧数据）"""
        _db.init_db()
        _db.init_db()
        backup_dir = os.path.join(tmp_db, "backups")
        assert not os.path.exists(backup_dir)

    def test_08_latest_version_no_rerun(self, tmp_db):
        """已是最新版本：重复初始化不重复升级、不重复备份"""
        _db.init_db()
        # 造一个 v1 旧库并升级（产生备份），再跑一次 init_db
        _db.execute("INSERT INTO settings (key, value) VALUES ('mp_url', 'http://x')")
        _db.init_db()
        backup_dir = os.path.join(tmp_db, "backups")
        files = os.listdir(backup_dir) if os.path.exists(backup_dir) else []
        assert len(files) == 0  # 已是最新 → 不备份不升级

    def test_09_existing_code_sql_compatible(self, tmp_db):
        """现有代码的 SQL 全部兼容（扫描/订阅写入路径）"""
        _db.init_db()
        # 模拟 scan_runner 的写入
        _db.execute(
            "INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, ?, ?)",
            (1399, "测试剧", "ok", "2024-01-01"))
        _db.execute(
            "INSERT INTO seasons (tmdb_id, season_number, total_episodes, aired_episodes, "
            "present_episodes, missing_episodes, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1399, 1, 10, 10, "[1,2,3]", "[4,5]", "partial"))
        # INSERT OR REPLACE 与唯一索引共存：同键插入 = 替换而非报错
        _db.execute(
            "INSERT OR REPLACE INTO subscribe_map "
            "(tmdb_id, season, mp_id, name, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1399, 1, 99, "测试剧", "R", "2024-01-01"))
        _db.execute(
            "INSERT OR REPLACE INTO subscribe_map "
            "(tmdb_id, season, mp_id, name, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1399, 1, 100, "测试剧", "P", "2024-01-01"))
        rows = _db.query("SELECT * FROM subscribe_map WHERE tmdb_id=? AND season=?",
                         (1399, 1))
        assert len(rows) == 1
        assert rows[0]["mp_id"] == 100

        row = _db.query_one("SELECT name FROM shows WHERE tmdb_id=?", (1399,))
        assert row["name"] == "测试剧"

    def test_10_batch_transaction_rollback(self, tmp_db):
        """批量事务：中途出错整批回滚（不会写一半污染数据）"""
        _db.init_db()
        with pytest.raises(Exception):
            with _db.transaction() as conn:
                conn.execute(
                    "INSERT INTO shows (tmdb_id, name) VALUES (?, ?)", (1, "剧1"))
                conn.execute("INSERT INTO no_such_table (x) VALUES (1)")  # 故意报错
        row = _db.query_one("SELECT 1 FROM shows WHERE tmdb_id=?", (1,))
        assert row is None  # 回滚了，没有半条数据

    def test_11_execute_many(self, tmp_db):
        """批量插入（executemany）"""
        _db.init_db()
        rows = [(i, f"剧{i}", "ok", "2024-01-01") for i in range(1, 1001)]
        _db.execute_many(
            "INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, ?, ?)",
            rows)
        count = _db.query_one("SELECT COUNT(*) c FROM shows")["c"]
        assert count == 1000
