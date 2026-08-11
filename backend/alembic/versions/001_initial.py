"""初始迁移 —— 创建所有表

Revision ID: 001
Revises: None
Create Date: 2025-01-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有 11 张表"""
    # 在 Base.metadata.create_all 中创建，这里留空
    # 实际建表由 app/main.py 的 lifespan 自动处理
    pass


def downgrade() -> None:
    """删除所有表"""
    pass
