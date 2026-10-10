"""iterd CLI：serve / dev / worker / seed / info."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iterd", description="产品迭代式开发系统 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动 API 服务（含进程内 worker）")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true", help="开发模式热重载")

    dev = sub.add_parser("dev", help="开发模式启动（reload + debug）")
    dev.add_argument("--host", default=None)
    dev.add_argument("--port", type=int, default=None)

    worker = sub.add_parser("worker", help="启动独立任务 worker（可多实例）")
    worker.add_argument("--worker-id", default=None)

    sub.add_parser("seed", help="注入演示数据")

    sub.add_parser("info", help="查看版本与配置信息")
    return parser


def cmd_serve(host: str | None, port: int | None, reload: bool = False) -> None:
    """启动 API 服务。"""
    import uvicorn

    from iterd.core.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "iterd.app:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


def cmd_worker(worker_id: str | None) -> None:
    """启动独立 worker 进程。"""
    import uuid

    from iterd.core.database import reset_database
    from iterd.tasks import runner

    wid = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
    reset_database()
    asyncio.run(runner.worker_loop(wid))


def _prepare_db() -> None:
    """建表（seed/worker 前置）。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine
    from iterd.models import Base

    # 触发全部模型注册
    from iterd.plugins import accounts, artifacts, notify, projects, rules, trace  # noqa: F401
    from iterd.tasks import models as _task_models  # noqa: F401

    async def _create() -> None:
        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())


def cmd_seed() -> None:
    """注入演示数据。"""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.seed import seed

    _prepare_db()
    settings = get_settings()
    engine = get_engine(settings.database_url)
    factory = get_session_factory(engine)

    async def _run() -> None:
        async with factory() as session:
            await seed(session, admin_username=settings.admin_username, admin_password=settings.admin_password)
            await session.commit()

    asyncio.run(_run())
    print("演示数据注入完成")


def cmd_info() -> None:
    """输出版本与配置信息。"""
    from iterd import __version__
    from iterd.core.config import get_settings
    from iterd.tasks.executor import registered_types

    settings = get_settings()
    print(f"iterd {__version__}")
    print(f"database: {settings.database_url}")
    print(f"data_dir: {settings.data_dir}")
    print(f"task_worker_in_app: {settings.task_worker_in_app}")
    print(f"task_types: {registered_types() or '（启动 app 后注册）'}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        cmd_serve(args.host, args.port)
    elif args.command == "dev":
        from iterd.core.config import Settings, reset_settings

        reset_settings(Settings(debug=True))
        cmd_serve(args.host, args.port, reload=True)
    elif args.command == "worker":
        cmd_worker(args.worker_id)
    elif args.command == "seed":
        cmd_seed()
    elif args.command == "info":
        cmd_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
