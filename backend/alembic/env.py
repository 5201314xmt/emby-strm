"""
Alembic 环境配置文件

负责连接数据库、读取模型元数据、自动生成迁移脚本。
每个迁移运行前先备份数据库到 data/backups/。
"""
import os
import shutil
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config 对象（读取 alembic.ini）
config = context.config

# 设置日志格式
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ========== 读取数据库 URL ==========
# 从 config.py 的 Settings 中获取数据库路径
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

# 同步 SQLAlchemy URL（alembic 用同步引擎）
db_path = settings.database_path
sync_url = f"sqlite:///{db_path}"
config.set_main_option("sqlalchemy.url", sync_url)

# ========== 设置模型元数据 ==========
# 告诉 Alembic 哪些表需要迁移
from app.models import Base
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并执行迁移"""
    # 迁移前先备份数据库
    _backup_database(db_path)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


def _backup_database(db_path: str):
    """迁移前备份数据库到 data/backups/ 目录"""
    if not os.path.exists(db_path):
        return
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"queji_backup_{timestamp}.db")
    try:
        shutil.copy2(db_path, backup_path)
        print(f"[迁移] 已备份数据库到 {backup_path}")
    except Exception as e:
        print(f"[迁移] 备份失败：{e}（迁移继续执行）")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
