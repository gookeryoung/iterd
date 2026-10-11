"""tasks runner 单元测试：抢占 / 重试 / 僵尸任务 / 执行器注册表."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from iterd.core import database as dbmod
from iterd.core.config import get_settings, reset_settings
from iterd.tasks import runner
from iterd.tasks.executor import TaskResult, get_executor, register_executor, registered_types
from iterd.tasks.models import Task


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("ITERD_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    reset_settings(None)
    dbmod.reset_database()
    from iterd.models import Base

    async def _create() -> None:
        from iterd.plugins import accounts  # noqa: F401
        from iterd.tasks import models  # noqa: F401

        engine = dbmod.get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield
    reset_settings(None)
    dbmod.reset_database()


def test_executor_registry() -> None:
    async def fake(session, payload, ctx) -> TaskResult:  # type: ignore[no-untyped-def]
        return TaskResult(success=True)

    register_executor("dummy", fake)
    assert "dummy" in registered_types()
    assert get_executor("dummy") is fake
    with pytest.raises(KeyError):
        get_executor("missing")


def test_claim_and_execute(isolated_db: None) -> None:
    from iterd.core.database import get_engine, get_session_factory

    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            session.add(Task(task_type="noop", payload={}, status="pending"))
            session.add(Task(task_type="noop", payload={}, status="pending", priority=5))
            await session.commit()

        ran: list[dict[str, object]] = []

        async def executor(session, payload, ctx) -> TaskResult:  # type: ignore[no-untyped-def]
            ctx.progress("stage", 50)
            ctx.log("info", "done")
            ran.append(payload)
            return TaskResult(success=True)

        register_executor("noop", executor)
        async with factory() as session:
            first = await runner.claim_next_task(session, "w1")
            assert first is not None and first.priority == 5 and first.attempts == 1
            await runner.execute_task(session, first, "w1")
        assert ran == [{}]

        async with factory() as session:
            second = await runner.claim_next_task(session, "w1")
            assert second is not None
            await runner.execute_task(session, second, "w1")
            third = await runner.claim_next_task(session, "w1")
            assert third is None

    asyncio.run(_run())


def test_failure_retries_then_fails(isolated_db: None) -> None:
    from iterd.core.database import get_engine, get_session_factory

    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            task = Task(task_type="boom", payload={}, status="pending", max_attempts=1)
            session.add(task)
            await session.commit()
            task_id = task.id

        async def executor(session, payload, ctx) -> TaskResult:  # type: ignore[no-untyped-def]
            raise RuntimeError("explode")

        register_executor("boom", executor)
        async with factory() as session:
            claimed = await runner.claim_next_task(session, "w1")
            assert claimed is not None
            await runner.execute_task(session, claimed, "w1")
        async with factory() as session:
            final = await session.get(Task, task_id)
            assert final is not None
            assert final.status == "failed"
            assert "explode" in (final.error or "")

    asyncio.run(_run())


def test_reap_stale_tasks(isolated_db: None) -> None:
    from iterd.core.database import get_engine, get_session_factory

    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            session.add(
                Task(
                    task_type="x",
                    payload={},
                    status="running",
                    attempts=1,
                    max_attempts=3,
                    heartbeat_at=datetime.now(UTC) - timedelta(seconds=999),
                )
            )
            session.add(
                Task(
                    task_type="x",
                    payload={},
                    status="running",
                    attempts=3,
                    max_attempts=3,
                    heartbeat_at=datetime.now(UTC) - timedelta(seconds=999),
                )
            )
            session.add(Task(task_type="x", payload={}, status="running", heartbeat_at=datetime.now(UTC)))
            await session.commit()

        async with factory() as session:
            reaped = await runner.reap_stale_tasks(session)
            assert reaped == 2
        async with factory() as session:
            from sqlalchemy import select

            tasks = list((await session.execute(select(Task).order_by(Task.id))).scalars())
            assert tasks[0].status == "pending" and tasks[0].attempts == 2
            assert tasks[1].status == "failed"

    asyncio.run(_run())


def test_worker_loop_processes_and_stops(isolated_db: None) -> None:
    from iterd.core.database import get_engine, get_session_factory

    factory = get_session_factory(get_engine(get_settings().database_url))

    async def executor(session, payload, ctx) -> TaskResult:  # type: ignore[no-untyped-def]
        return TaskResult(success=True)

    register_executor("quick", executor)

    async def _run() -> None:
        async with factory() as session:
            session.add(Task(task_type="quick", payload={}, status="pending"))
            await session.commit()
        stop = asyncio.Event()
        loop = asyncio.create_task(runner.worker_loop("w-test", stop=stop))
        for _ in range(30):
            await asyncio.sleep(0.2)
            async with factory() as session:
                from sqlalchemy import select

                task = (await session.execute(select(Task))).scalar_one()
                if task.status == "succeeded":
                    break
        stop.set()
        await asyncio.wait_for(loop, timeout=5)

    asyncio.run(_run())


def test_in_app_worker_graceful_stop(isolated_db: None) -> None:
    """进程内 worker：协作式停止应正常退出且无异常冒出."""
    import logging

    async def _run() -> None:
        worker = await runner.start_in_app_worker()
        await runner.stop_in_app_worker(worker, timeout=5)
        assert worker.task.done() and not worker.task.cancelled()
        assert worker.task.exception() is None

    logging.getLogger("iterd.worker").setLevel(logging.CRITICAL)
    asyncio.run(_run())


def test_in_app_worker_crash_swallowed(isolated_db: None, caplog: Any) -> None:
    """worker 关闭阶段异常应降级为告警，不从 lifespan 冒泡."""
    import logging

    async def _run() -> None:
        async def _boom() -> None:
            raise RuntimeError("db readonly 模拟")

        task = asyncio.create_task(_boom())
        worker = runner.InAppWorker(task=task, stop=asyncio.Event())
        await asyncio.sleep(0)  # 让异常在 task 中落地
        with caplog.at_level(logging.WARNING, logger="iterd.worker"):
            await runner.stop_in_app_worker(worker, timeout=5)
        assert any("关闭异常" in r.message for r in caplog.records)

    asyncio.run(_run())


def test_in_app_worker_timeout_cancels(isolated_db: None) -> None:
    """worker 无视 stop 事件时，超时后应强制取消且不抛异常."""

    async def _run() -> None:
        async def _stubborn() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(_stubborn())
        worker = runner.InAppWorker(task=task, stop=asyncio.Event())
        await runner.stop_in_app_worker(worker, timeout=0.1)
        assert task.cancelled()

    asyncio.run(_run())


def test_utcnow() -> None:
    assert runner.utcnow().tzinfo is UTC
