"""数据库引擎与会话管理."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    """确保 SQLite 数据库文件的父目录存在（SQLite 无法在不存在的目录中建库）."""
    parsed = urlparse(database_url)
    if not parsed.scheme.startswith("sqlite"):
        return
    database = parsed.path.lstrip("/")
    if database and database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)


def _apply_sqlite_pragmas(dbapi_connection: Any, busy_timeout_ms: int) -> None:
    """为新建立的 SQLite 连接设置 WAL 日志模式与 busy_timeout.

    WAL 允许读写并发、降低多 worker 并发写时的锁冲突；
    busy_timeout 让被锁阻塞的写操作等待重试而非立即报 database is locked。
    兼容 aiosqlite（async 适配器）与同步 sqlite3 两种连接形态。
    """
    pragmas = (f"PRAGMA journal_mode=WAL", f"PRAGMA busy_timeout={busy_timeout_ms}")
    if hasattr(dbapi_connection, "await_"):
        for pragma in pragmas:
            cursor = dbapi_connection.execute(pragma)
            dbapi_connection.await_(cursor.fetchall())
            dbapi_connection.await_(cursor.close())
    else:
        cursor = dbapi_connection.cursor()
        for pragma in pragmas:
            cursor.execute(pragma)
        cursor.close()


def get_engine(database_url: str, *, sqlite_busy_timeout_ms: int = 5000) -> AsyncEngine:
    """创建（或复用）全局异步引擎；SQLite 启用外键、WAL 与 busy_timeout."""
    global _engine  # noqa: PLW0603 - 模块级单例
    if _engine is None:
        kwargs: dict[str, object] = {"echo": False}
        if database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"timeout": 30}
            _ensure_sqlite_parent_dir(database_url)
            _engine = create_async_engine(database_url, **kwargs)  # pyright: ignore[reportArgumentType]
            event.listen(
                _engine.sync_engine,
                "connect",
                lambda dbapi_conn, _record: _apply_sqlite_pragmas(dbapi_conn, sqlite_busy_timeout_ms),
            )
            return _engine
        _engine = create_async_engine(database_url, **kwargs)  # pyright: ignore[reportArgumentType]
    return _engine


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """返回全局会话工厂（首次调用时创建）。"""
    global _session_factory  # noqa: PLW0603 - 模块级单例
    if _session_factory is None:
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


def reset_database() -> None:
    """重置全局引擎与会话工厂（测试用：切换配置后必须调用）."""
    global _engine, _session_factory  # noqa: PLW0603 - 模块级单例
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个会话."""
    from iterd.core.config import get_settings

    settings = get_settings()
    factory = get_session_factory(get_engine(settings.database_url, sqlite_busy_timeout_ms=settings.sqlite_busy_timeout_ms))
    async with factory() as session:
        yield session
