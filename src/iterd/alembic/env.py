"""Alembic 迁移环境：target_metadata 取 iterd 全部 ORM 模型."""

from __future__ import annotations

from alembic import context

from iterd.models import Base

# 显式导入各插件 models 与任务模型，确保 metadata 覆盖所有表
# （autogenerate 与 upgrade 均依赖；部分插件包 __init__ 不导入 models）
from iterd.plugins.accounts import models as _accounts_models  # noqa: F401
from iterd.plugins.artifacts import models as _artifacts_models  # noqa: F401
from iterd.plugins.bom import models as _bom_models  # noqa: F401
from iterd.plugins.notify import models as _notify_models  # noqa: F401
from iterd.plugins.projects import models as _projects_models  # noqa: F401
from iterd.plugins.rules import models as _rules_models  # noqa: F401
from iterd.plugins.simulation import models as _simulation_models  # noqa: F401
from iterd.plugins.trace import models as _trace_models  # noqa: F401
from iterd.tasks import models as _task_models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL 脚本，不连库."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite ALTER 限制：批量模式重建表
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移."""
    from sqlalchemy import create_engine, pool

    url = config.get_main_option("sqlalchemy.url") or ""
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER 限制：批量模式重建表
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
