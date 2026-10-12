"""数据库引擎测试：WAL / busy_timeout PRAGMA 与并发写竞争."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import text

from iterd.core import database as dbmod
from iterd.core.config import get_settings, reset_settings


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """隔离 SQLite 数据库文件（文件库，WAL 可生效）."""
    db_file = tmp_path / "t.db"
    monkeypatch.setenv("ITERD_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    reset_settings(None)
    dbmod.reset_database()
    yield db_file
    reset_settings(None)
    dbmod.reset_database()


def test_wal_and_busy_timeout_applied(isolated_db: Path) -> None:
    """新连接应自动设置 WAL 日志模式与 busy_timeout."""
    from iterd.core.database import get_engine

    engine = get_engine(get_settings().database_url, sqlite_busy_timeout_ms=7777)

    async def _run() -> tuple[object, object]:
        async with engine.connect() as conn:
            mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
            timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
        await engine.dispose()
        return mode, timeout

    mode, timeout = asyncio.run(_run())
    assert mode == "wal"
    assert timeout == 7777


def test_concurrent_writers_no_lock_failure(isolated_db: Path) -> None:
    """多协程并发写（8 写者 × 10 行）应全部成功，无 database is locked 失败."""
    from iterd.core.database import get_engine, get_session_factory

    engine = get_engine(get_settings().database_url)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, writer INTEGER)"))

    async def _writer(writer: int, rows: int = 10) -> None:
        factory = get_session_factory(engine)
        async with factory() as session:
            for i in range(rows):
                await session.execute(text("INSERT INTO t (writer) VALUES (:w)"), {"w": writer})
                await session.commit()
                await asyncio.sleep(0)  # 主动让出，制造并发竞争窗口

    async def _run() -> int:
        await _setup()
        await asyncio.gather(*(_writer(w) for w in range(8)))
        factory = get_session_factory(engine)
        async with factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM t"))
            return int(result.scalar_one())

    count = asyncio.run(_run())
    asyncio.run(engine.dispose())  # type: ignore[attr-defined]
    assert count == 80
