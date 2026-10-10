"""worker 主循环：抢占 / 心跳 / 重试 / 僵尸任务判定.

API 进程与 worker 通过 DB 解耦；worker 可多实例（`iterd worker`）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.config import get_settings
from iterd.core.database import get_engine, get_session_factory
from iterd.tasks.executor import TaskResult, run_executor
from iterd.tasks.models import Task

logger = logging.getLogger("iterd.worker")

POLL_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 10.0


class _LiveContext:
    """执行期上下文实现：进度与日志写入内存，结束时随任务回写."""

    def __init__(self) -> None:
        self.progress_data: dict[str, Any] = {"stage": "", "percent": 0}
        self.log_entries: list[dict[str, str]] = []

    def progress(self, stage: str, percent: int) -> None:
        """记录进度（percent 0-100）。"""
        self.progress_data = {"stage": stage, "percent": max(0, min(100, percent))}

    def log(self, level: str, message: str) -> None:
        """追加日志条目。"""
        self.log_entries.append({"level": level, "message": message})


async def claim_next_task(session: AsyncSession, worker_id: str) -> Task | None:
    """事务内抢占一个 pending 任务（priority 高者先，同优先级按 id 先进先出）。"""
    now = datetime.now(UTC)
    stmt = (
        update(Task)
        .where(
            Task.id
            == select(Task.id)
            .where(Task.status == "pending")
            .order_by(Task.priority.desc(), Task.id)
            .limit(1)
            .scalar_subquery()
        )
        .values(status="running", worker_id=worker_id, started_at=now, heartbeat_at=now, attempts=Task.attempts + 1)
        .returning(Task.id)
    )
    claimed = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    if claimed is None:
        return None
    return await session.get(Task, claimed)


async def _heartbeat_loop(task_id: int) -> None:
    """心跳：running 状态每 10s 刷新 heartbeat_at."""
    factory = get_session_factory(get_engine(get_settings().database_url))
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            async with factory() as session:
                await session.execute(
                    update(Task)
                    .where(Task.id == task_id, Task.status == "running")
                    .values(heartbeat_at=datetime.now(UTC))
                )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("心跳更新失败 task_id=%s", task_id)


async def execute_task(session: AsyncSession, task: Task, _worker_id: str) -> None:
    """执行单个任务：成功/失败/重试回写（执行器必须支持重复执行——幂等）."""
    task_id = task.id
    ctx = _LiveContext()
    heartbeat = asyncio.create_task(_heartbeat_loop(task_id))
    try:
        result: TaskResult = await run_executor(session, task.task_type, dict(task.payload), ctx)
        await session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status="succeeded" if result.success else "failed",
                progress=ctx.progress_data,
                logs=ctx.log_entries,
                error=result.error,
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await _handle_failure(task_id, ctx, f"{type(exc).__name__}: {exc}")
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _handle_failure(task_id: int, ctx: _LiveContext, error: str) -> None:
    """失败处理：attempts < max_attempts 退避重试回 pending，否则终态 failed."""
    factory = get_session_factory(get_engine(get_settings().database_url))
    async with factory() as session:
        task = await session.get(Task, task_id)
        if task is None:
            return
        values: dict[str, Any] = {
            "status": "failed",
            "progress": ctx.progress_data,
            "logs": ctx.log_entries,
            "error": error,
            "finished_at": datetime.now(UTC),
        }
        if task.attempts < task.max_attempts:
            values |= {"status": "pending", "worker_id": None, "heartbeat_at": None}
            logger.warning("任务重试 task_id=%s attempts=%s", task_id, task.attempts)
        await session.execute(update(Task).where(Task.id == task_id).values(**values))
        await session.commit()


async def reap_stale_tasks(session: AsyncSession) -> int:
    """将心跳超时的 running 任务判失败（attempts+1，可重试回 pending）."""
    timeout = get_settings().task_heartbeat_timeout
    deadline = datetime.now(UTC) - timedelta(seconds=timeout)
    stale = list(
        (await session.execute(select(Task).where(Task.status == "running", Task.heartbeat_at < deadline))).scalars()
    )
    for task in stale:
        task.status = "pending" if task.attempts < task.max_attempts else "failed"
        if task.status == "pending":
            task.attempts += 1
            task.worker_id = None
            task.heartbeat_at = None
        else:
            task.finished_at = datetime.now(UTC)
            task.error = "worker 心跳超时"
    await session.commit()
    return len(stale)


async def worker_loop(worker_id: str, *, stop: asyncio.Event | None = None) -> None:
    """worker 主循环：抢占→执行→循环；stop 事件触发退出。"""
    factory = get_session_factory(get_engine(get_settings().database_url))
    logger.info("worker 启动 worker_id=%s", worker_id)
    while stop is None or not stop.is_set():
        async with factory() as session:
            await reap_stale_tasks(session)
            task = await claim_next_task(session, worker_id)
        if task is None:
            await asyncio.sleep(POLL_INTERVAL)
            continue
        async with factory() as session:
            fresh = await session.get(Task, task.id)
            if fresh is not None:
                await execute_task(session, fresh, worker_id)


async def run_one_shot(session: AsyncSession, task: Task, worker_id: str) -> None:
    """单次执行（同步触发场景与测试用）：直接执行并回写状态."""
    await execute_task(session, task, worker_id)


async def start_in_app_worker() -> asyncio.Task[None]:
    """在 API 进程内启动后台 worker（task_worker_in_app=True 时由 lifespan 调用）。"""
    return asyncio.create_task(worker_loop("in-app"))


async def stop_in_app_worker(worker_task: asyncio.Task[None]) -> None:
    """优雅停止进程内 worker."""
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task


def utcnow() -> datetime:
    """当前 UTC 时间（辅助）。"""
    return datetime.now(UTC)


async def list_tasks(session: AsyncSession, *, status: str | None = None, limit: int = 50) -> list[Task]:
    """任务列表（监控用）。"""
    stmt = select(Task).order_by(Task.id.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    return list((await session.execute(stmt)).scalars())
