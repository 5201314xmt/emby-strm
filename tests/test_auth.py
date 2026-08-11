"""
============================================================
登录认证接口测试
运行方法：在项目根目录执行  python -m pytest tests/test_auth.py -v

说明：
  - 使用独立的临时数据库，不影响真实数据
  - 覆盖：未登录拦截 / 首次设置密码 / 登录 / 错误密码 /
          退出登录 / Token打码 / 打码不覆盖 / 修改密码 / 健康检查
============================================================
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# 先把数据库指到临时目录（必须在导入 app.main 之前，否则会读到真实数据）
from app import database as _db

_TMP = tempfile.mkdtemp()
_db.DATA_DIR = _TMP
_db.DB_PATH = os.path.join(_TMP, "test_auth.db")
_db.init_db()

from app.main import app  # noqa: E402

PASSWORD = "secret123"
NEW_PASSWORD = "newpass456"


@pytest.fixture()
def client():
    """每个测试一个全新的客户端（独立的 Cookie 状态）"""
    return TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def reset_auth_db():
    """认证测试前重置数据库（防止其他测试文件留下已初始化状态）"""
    _db.close_thread_connections()
    _db.execute("DELETE FROM settings")
    _db.execute("DELETE FROM sessions")
    yield


class TestAuth:
    def test_01_unauthenticated_api_returns_401(self, client):
        """未登录访问所有业务接口 → 401，且不影响扫描功能启动"""
        for path in ("/api/overview", "/api/shows", "/api/unrecognized",
                     "/api/status", "/api/settings", "/api/logs",
                     "/api/scan/status", "/api/subscriptions"):
            r = client.get(path)
            assert r.status_code == 401, f"{path} 未登录应返回 401"
            assert r.json()["success"] is False

        r = client.post("/api/scan")
        assert r.status_code == 401

    def test_02_setup_password_flow(self, client):
        """首次设置密码：太短拒绝；设置成功后自动登录"""
        r = client.post("/api/auth/setup", json={"password": "123"})
        assert r.json()["success"] is False

        r = client.post("/api/auth/setup", json={"password": PASSWORD})
        assert r.status_code == 200
        assert r.json()["success"] is True

        # 设置成功后自动登录，可以直接访问业务接口
        r = client.get("/api/overview")
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_03_setup_only_once(self, client):
        """已初始化后不能重复设置密码"""
        r = client.post("/api/auth/setup", json={"password": "another123"})
        assert r.json()["success"] is False

    def test_04_wrong_password(self, client):
        """错误密码登录失败"""
        r = client.post("/api/auth/login", json={"password": "wrong-pass"})
        assert r.json()["success"] is False

    def test_05_login_then_access(self, client):
        """正确密码登录后可访问 API，扫描功能正常启动"""
        r = client.post("/api/auth/login", json={"password": PASSWORD})
        assert r.json()["success"] is True

        r = client.get("/api/overview")
        assert r.status_code == 200

        r = client.post("/api/scan")
        assert r.json()["success"] is True  # 未配置目录时会后台报错，但接口正常

    def test_06_logout(self, client):
        """退出登录后再次访问 → 401"""
        client.post("/api/auth/login", json={"password": PASSWORD})
        r = client.post("/api/auth/logout")
        assert r.json()["success"] is True

        r = client.get("/api/overview")
        assert r.status_code == 401

    def test_07_settings_token_masked(self, client):
        """设置页读取：Token 打码显示，不泄露完整值"""
        client.post("/api/auth/login", json={"password": PASSWORD})
        client.post("/api/settings", json={"mp_token": "my-secret-token-1234"})

        r = client.get("/api/settings")
        items = {i["key"]: i for i in r.json()["data"]}
        val = items["mp_token"]["value"]
        assert val.startswith("******")
        assert "my-secret-token" not in val

    def test_08_masked_token_not_overwritten(self, client):
        """保存打码值不会覆盖真实 Token，其他设置正常保存"""
        client.post("/api/auth/login", json={"password": PASSWORD})
        client.post("/api/settings", json={"mp_token": "my-secret-token-1234"})

        # 模拟用户没改 Token 直接点保存（打码值传回后端）
        r = client.post("/api/settings", json={"mp_token": "******1234", "scan_interval": "6"})
        assert r.json()["success"] is True

        # 数据库里仍是真实 Token（打码值没有被写进去）
        row = _db.query_one("SELECT value FROM settings WHERE key='mp_token'")
        assert row["value"] == "my-secret-token-1234"

        # 网页读取时打码显示，其他设置正常保存
        r = client.get("/api/settings")
        items = {i["key"]: i for i in r.json()["data"]}
        assert items["mp_token"]["value"] == "******1234"
        assert items["scan_interval"]["value"] == "6"

    def test_09_change_password(self, client):
        """修改密码：当前密码错误拒绝；正确后新密码生效、旧密码失效"""
        client.post("/api/auth/login", json={"password": PASSWORD})

        r = client.post("/api/auth/change-password",
                        json={"old_password": "wrong", "new_password": NEW_PASSWORD})
        assert r.json()["success"] is False

        r = client.post("/api/auth/change-password",
                        json={"old_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert r.json()["success"] is True

        client.post("/api/auth/logout")
        r = client.post("/api/auth/login", json={"password": PASSWORD})
        assert r.json()["success"] is False  # 旧密码已失效

        r = client.post("/api/auth/login", json={"password": NEW_PASSWORD})
        assert r.json()["success"] is True  # 新密码可登录

    def test_10_health_public(self, client):
        """健康检查接口不需要登录（Docker 用）"""
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["success"] is True
