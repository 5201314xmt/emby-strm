"""
============================================================
pytest 公共配置：运行测试前初始化数据库
（因为扫描器内部会写日志到数据库）
============================================================
"""

import pytest

from app import database


@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    """整个测试会话开始前，初始化数据库"""
    database.init_db()
    yield
