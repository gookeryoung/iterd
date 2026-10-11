"""users 增加 role 列（三员角色：system_admin/security_admin/audit_admin/user）

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """users 增加 role 列，存量用户统一回填为普通用户（user）。"""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=32), nullable=False, server_default="user", comment="三员角色")
        )
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)


def downgrade() -> None:
    """回滚 role 列."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_column("role")
