"""
============================================================
API 接口测试（分页 / 缓存刷新 / 订阅预览 / 批量订阅 / 路径检查）
运行方法：在项目根目录执行  python -m pytest tests/test_api.py -v
============================================================
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# 先把数据库指到临时目录（必须在导入 app.main 之前）
from app import database as _db

_tmp = tempfile.mkdtemp()
_db.DATA_DIR = _tmp
_db.DB_PATH = os.path.join(_tmp, "test_api.db")
_db.init_db()

from app.main import app, runner  # noqa: E402

PWD = "testpass123"

RESET_SQL = (
    "DELETE FROM settings", "DELETE FROM sessions", "DELETE FROM subscribe_map",
    "DELETE FROM shows", "DELETE FROM seasons", "DELETE FROM ignored",
    "DELETE FROM unrecognized", "DELETE FROM logs", "DELETE FROM tmdb_cache",
)


class FakeMP:
    """假 MoviePilot：记录创建请求，模拟真实 MP 的去重拒绝"""
    url = "http://mock-mp"
    token = "t"

    def __init__(self):
        self.created = []

    def create_subscribe(self, name, year, tmdb_id, season, total_episode):
        if (tmdb_id, season) in self.created:
            return False, "该媒体已订阅"
        if tmdb_id == 999:
            return False, "模拟创建失败"
        self.created.append((tmdb_id, season))
        return True, 100 + len(self.created)

    def search_subscribe(self, mp_id):
        return True, None


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试前清空所有表（测试间完全隔离）"""
    _db.close_thread_connections()
    for sql in RESET_SQL:
        _db.execute(sql)
    yield


@pytest.fixture()
def client():
    """已登录的测试客户端"""
    c = TestClient(app)
    c.post("/api/auth/setup", json={"password": PWD})   # 已初始化时忽略失败
    r = c.post("/api/auth/login", json={"password": PWD})
    assert r.json()["success"] is True
    return c


def _insert_show(tmdb_id, name, season, present, missing, quality="normal"):
    _db.execute("INSERT INTO shows (tmdb_id, name, status, updated_at) VALUES (?, ?, 'ok', ?)",
                (tmdb_id, name, "2024-01-01"))
    n = len(present) + len(missing)
    _db.execute(
        "INSERT INTO seasons (tmdb_id, season_number, total_episodes, aired_episodes, "
        "present_episodes, missing_episodes, status, data_quality) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tmdb_id, season, n, n, repr(present), repr(missing), "partial", quality))


class TestApi:
    def test_01_shows_pagination(self, client):
        """缺集列表分页：limit/offset 生效，total 正确"""
        for i in range(1, 6):
            _insert_show(i, f"剧{i}", 1, [1], [2, 3])

        r = client.get("/api/shows?limit=2&offset=0")
        d = r.json()["data"]
        assert d["total"] == 5
        assert len(d["shows"]) == 2

        r = client.get("/api/shows?limit=2&offset=2")
        d = r.json()["data"]
        assert len(d["shows"]) == 2

        r = client.get("/api/shows?limit=2000")     # 超上限会被压到 200
        assert r.json()["data"]["total"] == 5

    def test_02_unrecognized_pagination(self, client):
        """未识别列表分页（items + total 结构）"""
        _db.execute_many(
            "INSERT INTO unrecognized (path, reason, updated_at) VALUES (?, ?, ?)",
            [(f"/path/{i}", "原因", "2024-01-01") for i in range(3)])
        r = client.get("/api/unrecognized?limit=2")
        d = r.json()["data"]
        assert d["total"] == 3
        assert len(d["items"]) == 2

    def test_03_cache_refresh(self, client):
        """清空 TMDB 缓存接口"""
        r = client.post("/api/cache/refresh")
        assert r.json()["success"] is True

    def test_04_check_path(self, client):
        """路径检查：存在/不存在/权限"""
        ok_dir = tempfile.mkdtemp()
        r = client.post("/api/settings/check-path", json={"path": ok_dir})
        assert r.json()["success"] is True
        r = client.post("/api/settings/check-path", json={"path": "/no/such/dir/xx"})
        assert r.json()["success"] is False
        r = client.post("/api/settings/check-path", json={"path": ""})
        assert r.json()["success"] is False

    def test_05_subscribe_preview(self, client):
        """订阅预览：列出待订阅项，degraded 单独计数且不进入清单"""
        _insert_show(100, "好剧", 1, [1], [2, 3], "normal")
        _insert_show(200, "不稳剧", 1, [1], [2, 3], "degraded")

        r = client.get("/api/subscribe/preview")
        d = r.json()["data"]
        assert d["total"] == 1                       # 只有 normal 的
        assert d["items"][0]["tmdb_id"] == 100
        assert d["degraded_count"] == 1              # degraded 单独提示
        assert d["degraded"][0]["tmdb_id"] == 200

    def test_06_subscribe_batch(self, client):
        """批量订阅（购物车提交）：多个季一次提交，重复提交被拦截"""
        _insert_show(100, "好剧", 1, [1], [2, 3], "normal")
        _insert_show(101, "好剧2", 1, [1], [2, 3], "normal")
        _insert_show(200, "不稳剧", 1, [1], [2, 3], "degraded")

        old_mp = runner.mp
        fake = FakeMP()
        runner.mp = fake
        try:
            r = client.post("/api/subscribe/batch", json={"items": [
                {"tmdb_id": 100, "season": 1},
                {"tmdb_id": 101, "season": 1},
                {"tmdb_id": 200, "season": 1},      # degraded 允许手动，但会提示
                {"tmdb_id": 999, "season": 1},      # 不存在的剧 → 失败计数
            ]})
            d = r.json()["data"]
            assert d["ok"] == 3
            assert d["fail"] == 1

            # 再提交一次相同项 → 全部拦截（不重复提交）
            r2 = client.post("/api/subscribe/batch", json={"items": [
                {"tmdb_id": 100, "season": 1}]})
            assert r2.json()["data"]["fail"] == 1
            assert fake.created.count((100, 1)) == 1   # 只提交过一次
        finally:
            runner.mp = old_mp

    def test_07_preview_excludes_subscribed(self, client):
        """订阅过的季不再出现在预览里"""
        _insert_show(100, "好剧", 1, [1], [2, 3], "normal")
        old_mp = runner.mp
        fake = FakeMP()
        runner.mp = fake
        try:
            client.post("/api/subscribe/batch", json={"items": [
                {"tmdb_id": 100, "season": 1}]})
        finally:
            runner.mp = old_mp

        r = client.get("/api/subscribe/preview")
        d = r.json()["data"]
        assert d["total"] == 0                      # 已订阅的从预览里消失
        assert all(i["tmdb_id"] != 100 for i in d["items"])
