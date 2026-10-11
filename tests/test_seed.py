"""seed 演示数据测试：覆盖式重建 + 全流程内容齐备 + 典型案例载入."""

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
    """隔离数据库建表并连跑两次 seed（验证覆盖重建），返回 (session factory, 首次摘要)."""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.accounts import models as accounts_models  # noqa: F401
    from iterd.plugins.artifacts import models as artifacts_models  # noqa: F401
    from iterd.plugins.notify import models as notify_models  # noqa: F401
    from iterd.plugins.projects import models as projects_models  # noqa: F401
    from iterd.plugins.rules import models as rules_models  # noqa: F401
    from iterd.plugins.simulation import models as simulation_models  # noqa: F401
    from iterd.plugins.trace import models as trace_models  # noqa: F401
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


def test_seed_overwrite_rebuild(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """重复 seed 覆盖重建：业务数据清空重建无残留、无重复，账号与审计日志保留."""
    from iterd.plugins.accounts.models import User
    from iterd.plugins.projects.models import Iteration, Project
    from iterd.plugins.rules.models import CheckRun, RuleItem, RuleSet

    _maker, _first, second = store

    # 二次执行摘要：演示流程内容全部重建
    flow = second["demo_flow"]
    assert flow["rule_set"] is True
    assert flow["binding"] is True
    assert flow["activated"] is True
    assert flow["baseline"] is True
    assert flow["check_run_id"] is not None
    assert all(not u["created"] for u in second["users"])  # 账号沿用，不重复建号

    # 无残留无重复：DEMO 项目仅 1 个、演示迭代 2 个、规则编码唯一、规则集仅演示 1 个 + 案例 N 个
    assert len([p for p in _rows(select(Project)) if p.code == "DEMO"]) == 1
    demo = next(p for p in _rows(select(Project)) if p.code == "DEMO")
    assert len(_rows(select(Iteration).where(Iteration.project_id == demo.id))) == 2
    rule_codes = [r.code for r in _rows(select(RuleItem))]
    assert len(rule_codes) == len(set(rule_codes))
    assert len(_rows(select(RuleSet))) == len({rs.name for rs in _rows(select(RuleSet))})

    # 演示迭代检查运行重建为 1 次（旧运行已随覆盖清空）
    from iterd.plugins.projects.models import Iteration as IterationModel

    demo_iters = _rows(
        select(IterationModel).where(IterationModel.project_id == demo.id).order_by(IterationModel.number)
    )
    runs = _rows(select(CheckRun).where(CheckRun.iteration_id == demo_iters[0].id))
    assert len(runs) == 1

    # 用户与审计日志保留
    assert len(_rows(select(User))) >= 6


def test_seed_typical_cases(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """seed 载入全部典型案例：数据集项目齐备，检查/仿真已预执行至终态."""
    from iterd.example_datasets import list_datasets
    from iterd.plugins.projects.models import Project
    from iterd.plugins.rules.models import CheckRun
    from iterd.plugins.simulation.models import SimJob

    if not list_datasets():
        pytest.skip("非源码仓库（无 examples/datasets），跳过典型案例断言")

    _maker, summary, _second = store
    cases = summary["cases"]
    assert len(cases) == len(list_datasets())

    # 数据集项目齐备（CVY/TRL/AXLE/BND 四个典型场景）
    codes = {p.code for p in _rows(select(Project))}
    assert {"CVY-2026", "TRL-2026", "AXLE-2026", "BND-2026"} <= codes

    # 每个数据集的检查运行均已成功（发现项与仿真结论打开界面即见）
    runs = _rows(select(CheckRun))
    assert runs
    assert all(r.status == "succeeded" for r in runs)

    # 仿真作业均到终态（边界数据集的 failed 为预期结果）
    jobs = _rows(select(SimJob))
    assert jobs
    assert all(j.status in ("succeeded", "failed") for j in jobs)
