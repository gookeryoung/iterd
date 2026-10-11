"""alembic 迁移测试：新库升级、幂等性、存量 create_all 库 stamp 兼容."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from iterd.core.config import get_settings
from iterd.core.migrations import build_config, to_sync_url, upgrade_head


def _head_revision() -> str:
    """当前迁移 head 版本号（断言用，避免新增迁移后改测试）。"""
    return str(ScriptDirectory.from_config(build_config()).get_current_head())


def _sync_url() -> str:
    """当前测试库的同步驱动 URL."""
    return to_sync_url(get_settings().database_url)


def _table_names(url: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_to_sync_url_converts_async_drivers() -> None:
    """异步驱动 URL 映射为同步驱动，未知驱动原样返回."""
    assert to_sync_url("sqlite+aiosqlite:///a.db") == "sqlite:///a.db"
    assert to_sync_url("postgresql+asyncpg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert to_sync_url("mysql+aiomysql://u:p@h/db") == "mysql+pymysql://u:p@h/db"
    assert to_sync_url("mysql+pymysql://u:p@h/db") == "mysql+pymysql://u:p@h/db"


def test_upgrade_head_creates_all_tables_and_idempotent(env: Path) -> None:
    """空库升级后包含全部业务表与 alembic_version，且重复升级幂等."""
    from iterd.models import Base

    upgrade_head()
    upgrade_head()  # 幂等：再次升级无异常
    names = _table_names(_sync_url())
    assert "alembic_version" in names
    assert set(Base.metadata.tables) <= names


def test_upgrade_head_stamps_legacy_create_all_db(env: Path) -> None:
    """存量 create_all 库（有业务表、无 alembic_version）自动 stamp 基线后升级成功.

    模拟 0001 时代库结构（users 无 role 列），stamp 0001 后升级到最新补齐全部增量。
    """
    import asyncio

    from iterd.models import Base

    # 模拟历史版本：create_all 直接建表
    async def _create() -> None:
        from iterd.core.database import get_engine

        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    # 剥离 0002 新增列，还原为 0001 时代的存量库结构
    engine = sa.create_engine(_sync_url())
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("DROP INDEX IF EXISTS ix_users_role"))
            conn.execute(sa.text("ALTER TABLE users DROP COLUMN role"))
    finally:
        engine.dispose()
    assert "alembic_version" not in _table_names(_sync_url())

    upgrade_head()
    engine = sa.create_engine(_sync_url())
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
            columns = {c["name"] for c in sa.inspect(conn).get_columns("users")}
    finally:
        engine.dispose()
    assert version == _head_revision()
    assert "role" in columns


def test_0004_upgrade_and_downgrade_roundtrip(env: Path) -> None:
    """0004 升级：建提交/步骤表、workflow_runs 增列、删基线三表；降级：反向还原结构."""
    from alembic import command

    cfg = build_config()

    # 升级到 0003（前置版本）
    command.upgrade(cfg, "0003")
    url = _sync_url()
    tables = _table_names(url)
    assert {"baselines", "baseline_items", "rule_set_bindings"} <= tables
    assert "iteration_submissions" not in tables

    # 升级到 0004
    command.upgrade(cfg, "0004")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            assert {"iteration_submissions", "workflow_job_steps"} <= tables
            assert not {"baselines", "baseline_items", "rule_set_bindings"} & tables
            run_cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
            assert {"submission_id", "trigger"} <= run_cols
            assert "ix_workflow_runs_submission_id" in {ix["name"] for ix in inspector.get_indexes("workflow_runs")}
            step_cols = {c["name"] for c in inspector.get_columns("workflow_job_steps")}
            assert {"job_id", "step_key", "status", "conclusion", "order_index", "logs"} <= step_cols
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    assert version == "0004"

    # 降级回 0003：删新表与新列，重建基线三表结构（数据不恢复）
    command.downgrade(cfg, "0003")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            assert not {"iteration_submissions", "workflow_job_steps"} & tables
            assert {"baselines", "baseline_items", "rule_set_bindings"} <= tables
            run_cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
            assert not {"submission_id", "trigger"} & run_cols
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    assert version == "0003"

    # 再次升级到 head 幂等无异常
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    assert version == _head_revision()


def test_load_example_db_is_versioned_and_serve_ready(tmp_path: Path) -> None:
    """载入脚本建库走 alembic（E2E 回归）：库带版本号，serve 启动迁移幂等.

    修复前 create_all 建出"当前结构但无 alembic_version"的库，
    serve 启动 stamp 基线后升级，因 users.role 列已存在而崩溃。
    """
    repo_root = Path(__file__).resolve().parents[1]
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'example' / 'iterd.db'}"
    env = {k: v for k, v in os.environ.items() if not k.startswith("ITERD_")}
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "load_example.py"),
            "--data-dir",
            str(tmp_path / "example"),
            "--database-url",
            db_url,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=repo_root,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    # 载入产物库已版本化到当前 head
    engine = sa.create_engine(to_sync_url(db_url))
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    assert version == _head_revision()

    # serve 启动路径（lifespan 自动迁移）在该库上幂等无异常
    upgrade_head(db_url)
