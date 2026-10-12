"""审批会签：approval_records 表（流水线内审批作业的人签记录）

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """当前库已有表名（存量 create_all 库 stamp 基线后升级时，表已存在则跳过建表）."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """建 approval_records 表（job_id + approver_id 唯一，同人同作业仅一条记录）."""
    if "approval_records" in _existing_tables():
        return
    op.create_table(
        "approval_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.Integer(), nullable=False),
        sa.Column("approver_name", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["workflow_jobs.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "approver_id", name="uq_approval_job_approver"),
    )
    op.create_index(op.f("ix_approval_records_job_id"), "approval_records", ["job_id"], unique=False)
    op.create_index(op.f("ix_approval_records_run_id"), "approval_records", ["run_id"], unique=False)


def downgrade() -> None:
    """回滚：删除 approval_records 表."""
    if "approval_records" not in _existing_tables():
        return
    op.drop_index(op.f("ix_approval_records_run_id"), table_name="approval_records")
    op.drop_index(op.f("ix_approval_records_job_id"), table_name="approval_records")
    op.drop_table("approval_records")
