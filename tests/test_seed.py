"""seed 演示数据测试：全流程内容齐备 + 幂等."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from iterd.models import Base
from iterd.seed import seed


@pytest.fixture()
def store(env: Path) -> Generator[tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]], None, None]:
    """隔离数据库建表并连跑两次 seed（验证幂等），返回 (session factory, 首次摘要)."""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins import accounts, artifacts, notify, projects, rules, simulation, trace  # noqa: F401
    from iterd.tasks import models as task_models  # noqa: F401

    engine = get_engine(get_settings().database_url)

    async def _prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_prepare())
    maker = get_session_factory(engine)

    async def _run() -> dict[str, Any]:
        async with maker() as session:
            result = await seed(session, admin_username="admin", admin_password="admin1234")
            await session.commit()
            return result

    first = asyncio.run(_run())
    second = asyncio.run(_run())

    yield maker, first, second
    asyncio.run(engine.dispose())


def _rows(stmt: Any) -> list[Any]:
    """在独立会话中执行 ORM 查询并返回全部标量结果."""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory

    async def _run() -> list[Any]:
        maker = get_session_factory(get_engine(get_settings().database_url))
        async with maker() as session:
            return list((await session.execute(stmt)).scalars())

    return asyncio.run(_run())


def test_seed_demo_flow_content(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """seed 后演示全流程内容齐备：账号 / 规则集 / 绑定 / 迭代激活 / 基线 / 检查运行."""
    _maker, summary, _second = store

    # 首次 seed 摘要：全流程内容全部新建
    flow = summary["demo_flow"]
    assert flow["rule_set"] is True
    assert flow["binding"] is True
    assert flow["activated"] is True
    assert flow["baseline"] is True
    assert flow["check_run_id"] is not None

    # 账号：三员 + 普通用户（含 reviewer）
    names = {u["username"] for u in summary["users"]}
    assert {"sec_admin", "audit_admin", "designer", "reviewer", "demo"} <= names

    # 项目 / 迭代：首轮迭代已激活，另有规划态迭代供演示状态流转
    from iterd.plugins.projects.models import Baseline, Iteration, Project

    projects = _rows(select(Project))
    demo = next(p for p in projects if p.code == "DEMO")
    iters = _rows(select(Iteration).where(Iteration.project_id == demo.id).order_by(Iteration.number))
    assert len(iters) == 2
    assert iters[0].status == "active"
    assert iters[1].status == "planned"

    # 演示规则集（项目级）与首个迭代绑定
    from iterd.plugins.rules.models import RuleSet, RuleSetBinding

    sets = _rows(select(RuleSet))
    demo_set = next(rs for rs in sets if rs.name == "演示规则集")
    assert demo_set.project_id == demo.id
    bindings = _rows(select(RuleSetBinding))
    assert any(b.iteration_id == iters[0].id and b.rule_set_id == demo_set.id for b in bindings)

    # 基线
    baselines = _rows(select(Baseline).where(Baseline.iteration_id == iters[0].id))
    assert any(b.name == "BL-首轮迭代" for b in baselines)

    # 预置检查运行：已完成且含 DRAFT-001 error 发现项（演示文件名不合规）
    from iterd.plugins.rules.models import CheckFinding, CheckRun, RuleItem

    runs = _rows(select(CheckRun).where(CheckRun.iteration_id == iters[0].id))
    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].summary is not None
    assert runs[0].summary["error"] >= 1
    items = _rows(select(CheckFinding).where(CheckFinding.check_run_id == runs[0].id))
    assert len(items) >= 1
    rules = _rows(select(RuleItem))
    draft = next(r for r in rules if r.code == "DRAFT-001")
    assert any(f.rule_item_id == draft.id and f.severity == "error" for f in items)


def test_seed_idempotent(store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]]) -> None:
    """重复 seed 不产生重复数据：规则 2 条 / 规则集 1 个 / 迭代 2 个 / 检查运行 1 次."""
    _maker, _first, second = store
    from iterd.plugins.projects.models import Iteration
    from iterd.plugins.rules.models import CheckRun, RuleItem, RuleSet

    # 二次执行摘要：全部跳过
    assert second["demo_flow"] == {
        "rule_set": False,
        "binding": False,
        "activated": False,
        "baseline": False,
        "check_run_id": None,
    }
    assert len(_rows(select(RuleItem))) == 2
    assert len(_rows(select(RuleSet))) == 1
    assert len(_rows(select(Iteration))) == 2
    assert len(_rows(select(CheckRun))) == 1
