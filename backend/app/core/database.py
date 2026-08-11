"""
数据库模块 —— SQLAlchemy 异步引擎 + 会话管理

使用 aiiosqlite 作为 SQLite 的异步驱动。
WAL 模式 + NORMAL 同步级别 = 读不阻塞写。

全局约定：
  - 所有数据库操作都通过 AsyncSession 进行
  - 在 FastAPI 路由里用 Depends(get_db) 获取会话
  - 请求结束自动关闭会话（FastAPI 的 yield 机制）
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event

from ..config import settings

# ========== 创建异步引擎 ==========
# echo=False         不打印 SQL 日志（生产环境）
# connect_args       传给 aiosqlite 的额外参数
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={
        "check_same_thread": False,  # SQLite 默认不允许跨线程，异步下必须关掉
    },
)

# ========== 创建会话工厂 ==========
# expire_on_commit=False  提交后不使对象过期（避免再查一次数据库）
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ========== SQLite WAL 模式配置 ==========
# 在每次新连接时执行 PRAGMA，设置 WAL 模式和同步级别
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """每个新连接建立时自动设置 SQLite 参数"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")     # 写前日志模式：读不阻塞写
    cursor.execute("PRAGMA synchronous=NORMAL;")    # 同步级别：平衡安全与性能
    cursor.execute("PRAGMA foreign_keys=ON;")       # 开启外键约束
    cursor.close()


async def get_db() -> AsyncSession:
    """
    FastAPI 依赖注入函数 —— 获取数据库会话

    用法：
      @router.get("/api/xxx")
      async def xxx(db: AsyncSession = Depends(get_db)):
          ...

    请求期间创建会话，请求结束后自动关闭。
    """
    async with AsyncSessionLocal() as session:
        yield session


# ========== ORM 基类 ==========
# 所有模型类都继承自 Base，由它统一管理到 Alembic 迁移
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy ORM 基类 —— 所有模型继承它"""
    pass
