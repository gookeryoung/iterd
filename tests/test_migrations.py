"""alembic 迁移测试：新库升级、幂等性、存量 create_all 库 stamp 兼容."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from iterd.core.config import get_settings
from iterd.core.migrations import to_sync_url, upgrade_head


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
    """存量 create_all 库（有业务表、无 alembic_version）自动 stamp 后升级成功."""
    import asyncio

    from iterd.models import Base

    # 模拟历史版本：create_all 直接建表
    async def _create() -> None:
        from iterd.core.database import get_engine

        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    assert "alembic_version" not in _table_names(_sync_url())

    upgrade_head()
    engine = sa.create_engine(_sync_url())
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    assert version == "0001"
