"""
ORM 模型模块 —— 数据库表映射

每个文件定义一张表，全部通过 SQLAlchemy ORM 映射。
统一从 models/__init__.py 导入，其他地方不要直接 import 子文件。

迁移方式：
  模型改完后运行：  alembic revision --autogenerate -m "描述"
  应用到数据库：    alembic upgrade head
"""
from ..core.database import Base

# 导入所有模型（确保注册到 Base，Alembic 才能发现）
from .setting import Setting
from .source import Source
from .show import Show
from .season import Season
from .ignored import Ignored
from .subscription import Subscription
from .scan_job import ScanJob
from .log import Log
from .unrecognized import UnrecognizedFile
from .session import Session
from .tmdb_cache import TMDBCache

__all__ = [
    "Base",
    "Setting",
    "Source",
    "Show",
    "Season",
    "Ignored",
    "Subscription",
    "ScanJob",
    "Log",
    "UnrecognizedFile",
    "Session",
    "TMDBCache",
]
