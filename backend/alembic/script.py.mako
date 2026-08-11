"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

说明：此文件由 alembic revision --autogenerate 自动生成。
      如需手动修改，请理解 SQLAlchemy + Alembic 的迁移语法。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# 版本标识
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """升级数据库（应用当前迁移）"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回滚数据库（撤销当前迁移）"""
    ${downgrades if downgrades else "pass"}
