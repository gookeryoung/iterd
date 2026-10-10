"""数据库引擎与会话管理."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str) -> AsyncEngine:
    """创建（或复用）全局异步引擎；SQLite 启用外键与串行化抢占."""
    global _engine  # noqa: PLW0603 - 模块级单例
    if _engine is None:
        kwargs: dict[str, object] = {"echo": False}
        if database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"timeout": 30}
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

    factory = get_session_factory(get_engine(get_settings().database_url))
    async with factory() as session:
        yield session
