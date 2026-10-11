"""iterd Web 应用（FastAPI）装配：插件路由 / lifespan / SPA 同源托管."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from fastapi_offline import FastAPIOffline
from starlette.exceptions import HTTPException
from starlette.types import Scope

from iterd.core.config import get_settings
from iterd.core.database import get_engine, get_session_factory
from iterd.core.errors import register_error_handlers

logger = logging.getLogger("iterd.app")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动：alembic 迁移至最新 → 确保管理员 → 进程内 worker."""
    settings = get_settings()
    # 导入全部模型确保 metadata 完整（迁移 env.py 自行导入，此处供种子与 worker 使用）
    from iterd.plugins import accounts, artifacts, notify, projects, rules, simulation, trace, workflows  # noqa: F401
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.simulation import services as sim_services
    from iterd.plugins.workflows import services as workflow_services
    from iterd.tasks import models as task_models  # noqa: F401

    rule_services.register_executors()
    sim_services.register_executors()
    workflow_services.register_executors()

    # lifespan 自动迁移（cndb 模式）：同步执行，含存量 create_all 库 stamp 兼容
    from iterd.core.migrations import upgrade_head

    await asyncio.to_thread(upgrade_head)
    engine = get_engine(settings.database_url)
    factory = get_session_factory(engine)
    async with factory() as session:
        from iterd.seed import ensure_admin

        await ensure_admin(session, settings.admin_username, settings.admin_password)
        await session.commit()

    worker = None
    if settings.task_worker_in_app:
        from iterd.tasks import runner

        worker = await runner.start_in_app_worker()

    if settings.backup_interval_hours > 0:
        from iterd.core.backup import BackupError, auto_backup_if_due

        try:
            await asyncio.to_thread(auto_backup_if_due)
        except BackupError:
            logger.warning("启动自动备份失败，服务继续启动", exc_info=True)

    logger.info("iterd 启动完成 database=%s", settings.database_url)
    yield
    if worker is not None:
        from iterd.tasks import runner

        await runner.stop_in_app_worker(worker)
    await engine.dispose()


def create_app() -> FastAPI:
    """创建应用实例：挂载插件路由、静态 SPA 与 WebSocket."""
    settings = get_settings()
    app = FastAPIOffline(title="iterd", description="产品迭代式开发系统.", lifespan=lifespan, debug=settings.debug)

    register_error_handlers(app)

    from iterd.plugins.accounts import routers as accounts_routers
    from iterd.plugins.artifacts import routers as artifacts_routers
    from iterd.plugins.notify import routers as notify_routers
    from iterd.plugins.projects import routers as projects_routers
    from iterd.plugins.rules import routers as rules_routers
    from iterd.plugins.simulation import routers as simulation_routers
    from iterd.plugins.trace import routers as trace_routers
    from iterd.plugins.workflows import routers as workflows_routers
    from iterd.tasks import api as tasks_api

    app.include_router(accounts_routers.router)
    app.include_router(accounts_routers.admin_router)
    app.include_router(projects_routers.router)
    app.include_router(artifacts_routers.router)
    app.include_router(rules_routers.router)
    app.include_router(simulation_routers.router)
    app.include_router(trace_routers.router)
    app.include_router(notify_routers.router)
    app.include_router(workflows_routers.router)
    app.include_router(tasks_api.router)

    static_dir = Path(__file__).parent / "static"
    has_build = (static_dir / "index.html").is_file()

    if not has_build:
        # 无前端构建产物时根路径保留 JSON 健康检查；有产物时由 SPA 挂载接管（对齐 cndb serve）
        @app.get("/", include_in_schema=False)
        def read_root() -> dict[str, str]:
            """根路径健康检查."""
            return {"status": "ok", "project": "iterd"}

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """同源托管前端构建产物 static/（存在才挂载，dev 模式由 Vite 代理）。"""
    static_dir = Path(__file__).parent / "static"
    if (static_dir / "index.html").exists():

        class _SpaFiles(StaticFiles):
            """history 回退：未命中的非 API 路径返回 index.html（前端路由接管）。"""

            async def get_response(self, path: str, scope: Scope) -> Response:  # type: ignore[override]
                try:
                    return await super().get_response(path, scope)
                except HTTPException as exc:
                    # starlette 0.50 未命中路径以 HTTPException(404) 抛出而非返回 404 响应；
                    # Windows 下 path 分隔符被规范为 os.sep 且可能带前导斜杠，统一归一化后判断
                    normalized = path.replace("\\", "/").lstrip("/")
                    if exc.status_code == 404 and not normalized.startswith("api/"):
                        return await super().get_response("index.html", scope)
                    raise

        app.mount("/", _SpaFiles(directory=str(static_dir), html=True), name="spa")


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("iterd.app:app", host="0.0.0.0", port=8000, reload=True)
