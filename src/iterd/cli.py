"""iterd CLI：serve / dev / build / worker / seed / info."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import subprocess  # nosec B404 - dev/build 需管理前后端子进程，命令均来自内部常量
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

# 后端默认端口：须与 frontend/vite.config.ts 的 /api、/ws 代理目标一致
DEV_DEFAULT_PORT = 8000


def _frontend_dir() -> Path | None:
    """定位前端目录（仅源码仓库内存在）；wheel 安装形态返回 None."""
    root = Path(__file__).resolve().parents[2]
    frontend = root / "frontend"
    return frontend if (frontend / "package.json").is_file() else None


def _static_dir() -> Path:
    """返回前端构建产物目录（src/iterd/static，随包分发）."""
    return Path(__file__).resolve().parent / "static"


def _ensure_dev_env(frontend: Path | None) -> None:
    """开发/构建命令前置检查：确认处于源码仓库且 pnpm 可用."""
    if frontend is None:
        print("[error] 此命令需在 iterd 源码仓库内运行（未找到 frontend/ 目录）", file=sys.stderr)
        raise SystemExit(1)
    import shutil

    if shutil.which("pnpm") is None:
        print("[error] pnpm 未安装，请先安装 pnpm（https://pnpm.io/installation）", file=sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iterd", description="产品迭代式开发系统 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动 API 服务（含进程内 worker，托管前端构建产物）")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true", help="开发模式热重载")

    dev = sub.add_parser("dev", help="开发模式：同时启动前后端（后端 reload + 前端 vite 热更新）")
    dev.add_argument("--host", default="127.0.0.1")
    dev.add_argument("--port", type=int, default=None, help=f"后端端口（默认 {DEV_DEFAULT_PORT}，与 Vite 代理对齐）")

    sub.add_parser("build", help="构建前端并同步产物到 src/iterd/static（供 serve 托管与打包分发）")

    worker = sub.add_parser("worker", help="启动独立任务 worker（可多实例）")
    worker.add_argument("--worker-id", default=None)

    sub.add_parser("seed", help="注入演示数据")

    backup = sub.add_parser("backup", help="创建数据备份（.tar.gz 归档）")
    backup.add_argument("--output", default=None, help="归档输出路径，默认 ~/.iterd/backups")
    backup.add_argument("--no-objects", action="store_true", help="不包含 objects 对象存储")
    backup.add_argument("--keep", type=int, default=None, help="默认目录中保留的归档数上限")

    restore = sub.add_parser("restore", help="从备份归档还原（数据库 + 对象存储）")
    restore.add_argument("archive", help="备份归档路径（iterd-backup-*.tar.gz）")
    restore.add_argument("--no-objects", action="store_true", help="不还原 objects 对象存储")

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


def cmd_build() -> None:
    """构建前端并同步产物到 src/iterd/static（对标 cndb build）.

    执行 ``pnpm build``（tsc --noEmit + vite build），产物由 Vite outDir
    直接输出到 src/iterd/static/，供 ``iterd serve`` 同源托管与 wheel 打包。
    """
    frontend = _frontend_dir()
    _ensure_dev_env(frontend)
    assert frontend is not None

    print("[build] 构建前端（tsc 类型检查 + vite build）...")
    result = subprocess.run(["pnpm", "build"], cwd=frontend, check=False)  # nosec - 命令来自内部常量
    if result.returncode != 0:
        print("[error] 前端构建失败", file=sys.stderr)
        raise SystemExit(result.returncode)

    static_dir = _static_dir()
    if not (static_dir / "index.html").is_file():
        print(f"[error] 构建产物缺失: {static_dir / 'index.html'}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[ok] 前端构建完成 → {static_dir}")


def cmd_dev(host: str, port: int | None) -> None:
    """开发模式：同时启动后端 uvicorn --reload 与前端 vite dev server（对标 cndb dev）.

    后端端口默认 8000 与 frontend/vite.config.ts 的 /api、/ws 代理目标对齐；
    前端由 Vite 提供热更新与接口代理，本地调试访问前端地址即可。
    Ctrl+C 信号统一清理全部子进程后退出。
    """
    frontend = _frontend_dir()
    _ensure_dev_env(frontend)
    assert frontend is not None

    if not (frontend / "node_modules").is_dir():
        print("[dev] 前端依赖未安装，执行 pnpm install...")
        result = subprocess.run(["pnpm", "install"], cwd=frontend, check=False)  # nosec - 命令来自内部常量
        if result.returncode != 0:
            print("[error] 前端依赖安装失败", file=sys.stderr)
            raise SystemExit(result.returncode)

    backend_port = port or DEV_DEFAULT_PORT
    if backend_port != DEV_DEFAULT_PORT:
        print(
            f"[warn] 后端端口 {backend_port} 与 Vite 代理目标（{DEV_DEFAULT_PORT}）不一致，"
            "前端 /api 请求将无法代理，请调整 frontend/vite.config.ts 或改用默认端口",
            file=sys.stderr,
        )
    frontend_port = 5173

    processes: list[subprocess.Popen[Any]] = []

    def _terminate_all() -> None:
        """终止全部子进程（幂等）：POSIX 按进程组整树终止，Windows taskkill 杀进程树."""
        for proc in processes:
            if proc.poll() is not None:
                continue
            if sys.platform == "win32":
                with suppress(OSError):
                    subprocess.run(  # nosec - 命令来自内部常量
                        ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
                    )
            else:
                with suppress(OSError):
                    proc.terminate()
                # pnpm/npm 会派生孙进程（node vite），子进程以独立进程组启动，按组整树终止
                with suppress(OSError):
                    os.killpg(proc.pid, signal.SIGTERM)
        for proc in processes:
            with suppress(subprocess.TimeoutExpired, OSError):
                proc.wait(timeout=5)

    def _handle_sigint(_signum: Any, _frame: Any) -> None:
        """Ctrl+C：清理子进程后退出."""
        _terminate_all()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    print(f"[dev] 启动后端服务（http://{host}:{backend_port}，reload 已开启）...")
    backend = subprocess.Popen(  # nosec - 命令来自内部常量
        [
            sys.executable,
            "-m",
            "uvicorn",
            "iterd.app:app",
            "--host",
            host,
            "--port",
            str(backend_port),
            "--reload",
        ],
        start_new_session=True,
    )
    processes.append(backend)

    print(f"[dev] 启动前端开发服务器（http://{host}:{frontend_port}，vite 热更新）...")
    frontend_proc = subprocess.Popen(["pnpm", "dev"], cwd=frontend, start_new_session=True)  # nosec - 命令来自内部常量
    processes.append(frontend_proc)

    print()
    print(f"  前端:     http://{host}:{frontend_port}")
    print(f"  后端 API: http://{host}:{backend_port}/docs")
    print()
    print("按 Ctrl+C 停止所有服务")

    try:
        backend.wait()
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    finally:
        # 后端退出或异常时统一回收前端进程（幂等）
        _terminate_all()


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
    from iterd.plugins import (  # noqa: F401
        accounts,
        artifacts,
        notify,
        projects,
        rules,
        simulation,
        trace,
    )
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
    print(f"objects_dir: {settings.objects_dir}")
    print(f"backup_dir: {settings.backup_dir}")
    print(f"log_dir: {settings.log_dir}")
    print(f"task_worker_in_app: {settings.task_worker_in_app}")
    print(f"task_types: {registered_types() or '（启动 app 后注册）'}")


def cmd_backup(output: str | None, no_objects: bool, keep: int | None) -> None:
    """创建数据备份。"""
    from pathlib import Path

    from iterd.core.backup import BackupError, create_backup

    try:
        result = create_backup(
            Path(output) if output else None,
            include_objects=not no_objects,
            keep=keep,
        )
        print(f"备份成功: {result}")
    except BackupError as exc:
        print(f"备份失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def cmd_restore(archive: str, no_objects: bool) -> None:
    """从备份归档还原。"""
    from pathlib import Path

    from iterd.core.backup import RestoreError, restore_backup

    try:
        manifest = restore_backup(Path(archive), include_objects=not no_objects)
        print(f"还原成功: {archive}（{manifest['database']['row_counts']}）")
    except RestoreError as exc:
        print(f"还原失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)
    if args.command == "serve":
        cmd_serve(args.host, args.port)
    elif args.command == "dev":
        cmd_dev(args.host, args.port)
    elif args.command == "build":
        cmd_build()
    elif args.command == "worker":
        cmd_worker(args.worker_id)
    elif args.command == "seed":
        cmd_seed()
    elif args.command == "backup":
        cmd_backup(args.output, args.no_objects, args.keep)
    elif args.command == "restore":
        cmd_restore(args.archive, args.no_objects)
    elif args.command == "info":
        cmd_info()
    return 0


if __name__ == "__main__":
    sys.exit(main())
