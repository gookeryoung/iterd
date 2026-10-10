"""tasks API：任务查询与 WebSocket 进度/日志推送."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import IterdError
from iterd.tasks import runner
from iterd.tasks.models import Task

router = APIRouter(prefix="/api/v1", tags=["tasks"])


class TaskOut(BaseModel):
    """任务对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    payload: dict[str, Any]
    status: str
    priority: int
    progress: dict[str, Any] | None
    logs: list[dict[str, Any]] | None
    attempts: int
    max_attempts: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    _user: CurrentUser, session: SessionDep, status: str | None = None, limit: int = 50
) -> list[TaskOut]:
    """任务列表（监控用）。"""
    tasks = await runner.list_tasks(session, status=status, limit=limit)
    return [TaskOut.model_validate(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, _user: CurrentUser, session: SessionDep) -> TaskOut:
    """任务详情。"""
    task = await session.get(Task, task_id)
    if task is None:
        raise IterdError(f"任务不存在: {task_id}", code="ITERD-NOT_FOUND", status_code=404)
    return TaskOut.model_validate(task)


@router.websocket("/ws/tasks/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: int) -> None:
    """任务进度/日志流：轮询任务行推送直至终态。"""
    await websocket.accept()
    last_status = None
    try:
        while True:
            from iterd.core.config import get_settings
            from iterd.core.database import get_engine, get_session_factory

            factory = get_session_factory(get_engine(get_settings().database_url))
            async with factory() as session:
                task = await session.get(Task, task_id)
                if task is None:
                    await websocket.send_json({"error": "task not found"})
                    break
                state = {
                    "id": task.id,
                    "status": task.status,
                    "progress": task.progress,
                    "logs": task.logs,
                    "error": task.error,
                }
            if state["status"] != last_status or state["status"] in ("running",):
                await websocket.send_json(state)
                last_status = state["status"]
            if state["status"] in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    with contextlib.suppress(Exception):
        await websocket.close()
