"""BOM 实体化：bom_items 表 + check_findings.artifact_version_id 放宽为可空（迭代级发现项）

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """当前库已有表名（存量 create_all 库 stamp 基线后升级时，表已存在则跳过建表）."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """建 bom_items 表（项目/迭代维度 BOM 台账），放宽发现项产物版本外键为可空."""
    tables = _existing_tables()
    if "bom_items" not in tables:
        op.create_table(
            "bom_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("iteration_id", sa.Integer(), nullable=False),
            sa.Column("part_code", sa.String(length=64), nullable=False),
            sa.Column("part_name", sa.String(length=128), nullable=False),
            sa.Column("material", sa.String(length=64), nullable=False),
            sa.Column("spec", sa.String(length=255), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_weight", sa.Float(), nullable=True),
            sa.Column("note", sa.String(length=512), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["iteration_id"], ["iterations.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("iteration_id", "part_code", name="uq_bom_item_part"),
        )
        op.create_index(op.f("ix_bom_items_project_id"), "bom_items", ["project_id"], unique=False)
        op.create_index(op.f("ix_bom_items_iteration_id"), "bom_items", ["iteration_id"], unique=False)

    if "check_findings" in tables:
        with op.batch_alter_table("check_findings") as batch:
            batch.alter_column(
                "artifact_version_id",
                existing_type=sa.Integer(),
                nullable=True,
                existing_foreign_key="fk_check_findings_artifact_version_id_artifact_versions",
            )


def downgrade() -> None:
    """回滚：发现项产物版本恢复非空，删除 bom_items 表."""
    tables = _existing_tables()
    if "check_findings" in tables:
        with op.batch_alter_table("check_findings") as batch:
            batch.alter_column("artifact_version_id", existing_type=sa.Integer(), nullable=False)
    if "bom_items" in tables:
        op.drop_index(op.f("ix_bom_items_iteration_id"), table_name="bom_items")
        op.drop_index(op.f("ix_bom_items_project_id"), table_name="bom_items")
        op.drop_table("bom_items")
