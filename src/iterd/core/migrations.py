"""Alembic 迁移基础设施：程序化配置 + 启动自动升级（cndb lifespan 模式）."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

__all__ = ["build_config", "to_sync_url", "upgrade_head"]

# 迁移脚本目录：包内 alembic/（随 wheel 分发，安装后仍可用）
SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic"

# 存量库判定基准表：历史版本由 create_all 建表，无 alembic_version 记录
_CORE_TABLE = "users"

# 存量库 stamp 基线版本：对应 create_all 时代的初始表结构。
# 后续新增迁移（如 0002 users.role）会在此基础上继续升级，存量库不漏迁移。
_BASELINE_REVISION = "0001"

# 异步驱动 → 同步驱动映射（alembic 迁移运行在同步引擎上）
_ASYNC_DRIVERS = {
    "+aiosqlite": "",
    "+asyncpg": "",
    "+asyncmy": "+pymysql",
    "+aiomysql": "+pymysql",
    "+aioodbc": "+pyodbc",
}


def to_sync_url(database_url: str) -> str:
    """将异步驱动数据库 URL 转换为同步驱动等价 URL."""
    for async_driver, sync_driver in _ASYNC_DRIVERS.items():
        if async_driver in database_url:
            return database_url.replace(async_driver, sync_driver, 1)
    return database_url


def build_config(database_url: str | None = None) -> Config:
    """构建程序化 Alembic 配置：脚本目录指向包内 alembic/，URL 取自配置."""
    from iterd.core.config import get_settings

    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", to_sync_url(database_url or get_settings().database_url))
    cfg.set_main_option("file_template", "%%(rev)s_%%(slug)s")
    return cfg


def upgrade_head(database_url: str | None = None) -> None:
    """升级数据库到最新迁移（幂等，serve/seed/worker 启动前调用）.

    存量库兼容：若业务表已存在但无 alembic_version 记录（历史 create_all 建表），
    先 stamp 到基线版本（0001）再升级，避免重复建表且不漏后续迁移；
    新库直接 upgrade head。
    """
    import sqlalchemy
    from sqlalchemy.engine import make_url

    cfg = build_config(database_url)
    url = cfg.get_main_option("sqlalchemy.url") or ""
    # SQLite 数据库文件父目录必须存在（迁移引擎不经过 database.py 的目录保障）
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = sqlalchemy.create_engine(url)
    try:
        inspector = sqlalchemy.inspect(engine)
        if _CORE_TABLE in inspector.get_table_names() and not inspector.has_table("alembic_version"):
            command.stamp(cfg, _BASELINE_REVISION)
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
