"""
============================================================
数据库模块 - 负责 SQLite 数据库的连接和建表
============================================================
说明：
  - 使用 SQLite（一个文件存所有数据），无需安装数据库软件
  - 所有表的结构定义和升级在 migrations.py 里统一管理（版本化自动迁移）
  - 每次操作都用独立的短连接，简单可靠，不怕多线程
  - WAL 模式：读写互不阻塞，扫描写库时网页不卡
============================================================
"""

import os
import sqlite3
import threading
from contextlib import contextmanager

# 数据库文件路径（放在 data 目录下，data 目录会挂载到 Docker 数据卷）
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "queji.db")

# 模块一加载就创建数据目录（否则程序第一次启动时，建表前就要读写数据库会报错）
os.makedirs(DATA_DIR, exist_ok=True)

# 线程锁：SQLite 写操作时防止多线程同时写导致冲突
_db_lock = threading.Lock()

# 线程级连接复用：每个线程只开一次连接，重复使用（性能关键）
# 之前每次操作都开新连接，扫描 10 万部剧时要开 70 万个连接，慢 10 倍以上
_tls = threading.local()


def _get_thread_conn() -> sqlite3.Connection:
    """获取当前线程的复用连接（首次使用时创建）"""
    conn = getattr(_tls, "conn", None)
    if conn is None:
        conn = get_conn()
        _tls.conn = conn
    return conn


def close_thread_connections():
    """
    关闭当前线程的复用连接（测试切换数据库路径时用；
    正常运行时不需要调用，线程结束时连接自动释放）
    """
    conn = getattr(_tls, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _tls.conn = None


def init_db():
    """
    初始化数据库：
      1. 执行数据库迁移（自动升级到最新结构，旧数据先自动备份）
      2. 确保 WAL 模式开启（读写互不阻塞）
    程序启动时调用一次即可。
    """
    from . import migrations
    migrations.run_migrations()


def get_conn() -> sqlite3.Connection:
    """
    打开一个新的数据库连接（每个线程用独立的连接，安全）
    返回的连接需要调用方自己 close（推荐用 with 语句）。
    """
    conn = sqlite3.connect(DB_PATH, timeout=30)
    # 让查询结果支持按列名访问（如 row["name"]），写代码更不容易出错
    conn.row_factory = sqlite3.Row
    # WAL 模式下用 NORMAL 同步级别：比 FULL 快很多，崩溃时最多丢最近一次写入，不会损坏
    conn.execute("PRAGMA synchronous=NORMAL")
    # 写冲突时最多等 30 秒（而不是立刻报 database is locked）
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def execute(sql: str, params: tuple = ()) -> int:
    """
    执行一条写操作的 SQL（增删改）
    自动加锁防止多线程冲突，返回受影响的行数。
    """
    with _db_lock:
        conn = _get_thread_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
        except Exception:
            # 出错回滚，避免事务残留影响这个线程后续操作
            try:
                conn.rollback()
            except Exception:
                pass
            raise


def query(sql: str, params: tuple = ()) -> list:
    """
    执行一条查询 SQL，返回所有结果（列表，每行是 dict 风格的对象）
    """
    conn = _get_thread_conn()
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def query_one(sql: str, params: tuple = ()):
    """
    执行一条查询 SQL，只返回第一行（没有结果返回 None）
    """
    conn = _get_thread_conn()
    try:
        return conn.execute(sql, params).fetchone()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# ============================================================
# 批量写入（扫描性能优化用）
# ============================================================


@contextmanager
def transaction():
    """
    批量事务上下文管理器：
      一个连接内执行多条写操作，最后一次性 commit（比每条单独提交快几百倍）

    用法：
        with database.transaction() as conn:
            conn.execute(sql1, p1)
            conn.execute(sql2, p2)
        # 退出 with 时统一提交；中途出错自动回滚

    注意：这个连接只在 with 块内有效，不要把它存到别处
    """
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_many(sql: str, rows: list):
    """
    一次批量插入多条记录（executemany），比逐条 execute 快很多
    整批在一个事务里提交，任一行出错整批回滚（数据不会写一半）
    """
    if not rows:
        return
    with _db_lock:
        conn = _get_thread_conn()
        try:
            conn.execute("BEGIN")
            conn.executemany(sql, rows)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
