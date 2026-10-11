"""提交方案与步骤层级；移除基线 / 规则集绑定（破坏性：基线数据不保留，升级前请备份）

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """当前库已有表名（存量 create_all 库 stamp 基线后升级时，表已存在则跳过建表）."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_columns(table: str) -> set[str]:
    """当前表已有列名（存量 create_all 库已含新列时跳过加列）."""
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """建 iteration_submissions / workflow_job_steps，workflow_runs 增列，删基线与绑定三表."""
    existing = _existing_tables()

    # 1. 提交方案表（workflow_runs.submission_id 的 FK 目标，须先建）
    if "iteration_submissions" not in existing:
        op.create_table(
            "iteration_submissions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("iteration_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=128), nullable=False),
            sa.Column("note", sa.String(length=1024), nullable=False),
            sa.Column("submitted_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["iteration_id"], ["iterations.id"]),
            sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_iteration_submissions_iteration_id"), "iteration_submissions", ["iteration_id"], unique=False
        )

    # 2. 作业步骤表
    if "workflow_job_steps" not in existing:
        op.create_table(
            "workflow_job_steps",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=False),
            sa.Column("step_key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("conclusion", sa.String(length=16), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=False),
            sa.Column("logs", SQLiteJSON(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["job_id"], ["workflow_jobs.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id", "step_key", name="uq_workflow_job_step"),
        )
        op.create_index(op.f("ix_workflow_job_steps_job_id"), "workflow_job_steps", ["job_id"], unique=False)

    # 3. workflow_runs 增列（batch 模式兼容 SQLite）
    if "workflow_runs" in existing:
        cols = _existing_columns("workflow_runs")
        with op.batch_alter_table("workflow_runs") as batch:
            if "submission_id" not in cols:
                batch.add_column(sa.Column("submission_id", sa.Integer(), nullable=True))
            if "trigger" not in cols:
                batch.add_column(sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"))
        cols = _existing_columns("workflow_runs")
        if "submission_id" in cols:
            existing_fk = {
                fk["constrained_columns"][0] if len(fk["constrained_columns"]) == 1 else None
                for fk in sa.inspect(op.get_bind()).get_foreign_keys("workflow_runs")
            }
            if "submission_id" not in existing_fk:
                with op.batch_alter_table("workflow_runs") as batch:
                    batch.create_foreign_key(
                        "fk_workflow_runs_submission_id_iteration_submissions",
                        "iteration_submissions",
                        ["submission_id"],
                        ["id"],
                    )
        if "submission_id" in cols:
            indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("workflow_runs")}
            if "ix_workflow_runs_submission_id" not in indexes:
                op.create_index(
                    op.f("ix_workflow_runs_submission_id"), "workflow_runs", ["submission_id"], unique=False
                )

    # 4. 删除基线与绑定三表（破坏性：数据不保留）
    for table in ("baseline_items", "rule_set_bindings", "baselines"):
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    """回滚：重建基线与绑定三表结构（数据不恢复），删步骤与提交表，workflow_runs 移除新列."""
    existing = _existing_tables()

    # 1. workflow_runs 移除新列（先删 submission_id 索引，避免 batch 重建表时对已删列建索引）
    if "workflow_runs" in existing:
        cols = _existing_columns("workflow_runs")
        indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("workflow_runs")}
        if "submission_id" in cols and "ix_workflow_runs_submission_id" in indexes:
            op.drop_index("ix_workflow_runs_submission_id", table_name="workflow_runs")
        with op.batch_alter_table("workflow_runs") as batch:
            if "submission_id" in cols:
                batch.drop_column("submission_id")
            if "trigger" in cols:
                batch.drop_column("trigger")

    # 2. 删步骤与提交表
    if "workflow_job_steps" in existing:
        op.drop_index(op.f("ix_workflow_job_steps_job_id"), table_name="workflow_job_steps")
        op.drop_table("workflow_job_steps")
    if "iteration_submissions" in existing:
        op.drop_index(op.f("ix_iteration_submissions_iteration_id"), table_name="iteration_submissions")
        op.drop_table("iteration_submissions")

    # 3. 重建基线与绑定三表结构（仅结构，历史数据不恢复）
    if "rule_set_bindings" not in existing:
        op.create_table(
            "rule_set_bindings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("rule_set_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("iteration_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["iteration_id"], ["iterations.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["rule_set_id"], ["rule_sets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_rule_set_bindings_rule_set_id"), "rule_set_bindings", ["rule_set_id"], unique=False)
    if "baselines" not in existing:
        op.create_table(
            "baselines",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("iteration_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("uid", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["iteration_id"], ["iterations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_baselines_iteration_id"), "baselines", ["iteration_id"], unique=False)
        op.create_index(op.f("ix_baselines_uid"), "baselines", ["uid"], unique=True)
    if "baseline_items" not in existing:
        op.create_table(
            "baseline_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("baseline_id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=False),
            sa.Column("artifact_version_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
            sa.ForeignKeyConstraint(["artifact_version_id"], ["artifact_versions.id"]),
            sa.ForeignKeyConstraint(["baseline_id"], ["baselines.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("baseline_id", "artifact_id", name="uq_baseline_item"),
        )
