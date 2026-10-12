"""站内信通知：notifications 表（面向单用户的事件触达记录）

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """当前库已有表名（存量 create_all 库 stamp 基线后升级时，表已存在则跳过建表）."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """建 notifications 表（收件人 + 类型 + 已读状态索引）。"""
    if "notifications" in _existing_tables():
        return
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ntype", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=1024), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("link", sa.String(length=200), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_notifications_ntype"), "notifications", ["ntype"], unique=False)
    op.create_index(op.f("ix_notifications_project_id"), "notifications", ["project_id"], unique=False)


def downgrade() -> None:
    """回滚：删除 notifications 表."""
    if "notifications" not in _existing_tables():
        return
    op.drop_index(op.f("ix_notifications_project_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_ntype"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
