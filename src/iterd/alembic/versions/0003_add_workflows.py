"""新增 workflows 三表（审查模板 / 审查运行 / 流水线作业）

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """当前库已有表名（存量 create_all 库 stamp 基线后升级时，表已存在则跳过建表）."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """建 workflows / workflow_runs / workflow_jobs 三表与索引（已存在则跳过，幂等）."""
    existing = _existing_tables()
    if "workflows" in existing:
        return
    op.create_table(
        "workflows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_workflows_project_id"), "workflows", ["project_id"], unique=False)

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("iteration_id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("workflow_code", sa.String(length=64), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", SQLiteJSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["iteration_id"], ["iterations.id"]),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_runs_iteration_id"), "workflow_runs", ["iteration_id"], unique=False)
    op.create_index(op.f("ix_workflow_runs_status"), "workflow_runs", ["status"], unique=False)

    op.create_table(
        "workflow_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("job_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("job_type", sa.String(length=16), nullable=False),
        sa.Column("needs", SQLiteJSON(), nullable=True),
        sa.Column("config", SQLiteJSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("conclusion", sa.String(length=16), nullable=True),
        sa.Column("check_run_id", sa.Integer(), nullable=True),
        sa.Column("sim_job_id", sa.Integer(), nullable=True),
        sa.Column("logs", SQLiteJSON(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.ForeignKeyConstraint(["check_run_id"], ["check_runs.id"]),
        sa.ForeignKeyConstraint(["sim_job_id"], ["sim_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "job_key", name="uq_workflow_job_key"),
    )
    op.create_index(op.f("ix_workflow_jobs_run_id"), "workflow_jobs", ["run_id"], unique=False)


def downgrade() -> None:
    """回滚三表（表不存在时跳过，幂等）."""
    existing = _existing_tables()
    if "workflow_jobs" in existing:
        op.drop_index(op.f("ix_workflow_jobs_run_id"), table_name="workflow_jobs")
        op.drop_table("workflow_jobs")
    if "workflow_runs" in existing:
        op.drop_index(op.f("ix_workflow_runs_status"), table_name="workflow_runs")
        op.drop_index(op.f("ix_workflow_runs_iteration_id"), table_name="workflow_runs")
        op.drop_table("workflow_runs")
    if "workflows" in existing:
        op.drop_index(op.f("ix_workflows_project_id"), table_name="workflows")
        op.drop_table("workflows")
