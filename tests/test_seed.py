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
    from iterd.plugins.bom import models as bom_models  # noqa: F401
    from iterd.plugins.notify import models as notify_models  # noqa: F401
    from iterd.plugins.projects import models as projects_models  # noqa: F401
    from iterd.plugins.rules import models as rules_models  # noqa: F401
    from iterd.plugins.simulation import models as simulation_models  # noqa: F401
    from iterd.plugins.trace import models as trace_models  # noqa: F401
    from iterd.plugins.workflows import models as workflows_models  # noqa: F401
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


def _row_tuples(stmt: Any) -> list[tuple[Any, ...]]:
    """在独立会话中执行多列 ORM 查询并返回 Row 列表."""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory

    async def _run() -> list[Any]:
        maker = get_session_factory(get_engine(get_settings().database_url))
        async with maker() as session:
            return list((await session.execute(stmt)).all())

    return asyncio.run(_run())


def test_seed_demo_flow_content(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """seed 后演示全流程内容齐备：账号 / 规则集 / 迭代激活 / 演示模板 / 提交方案与运行."""
    _maker, summary, _second = store

    # 首次 seed 摘要：全流程内容全部新建，提交方案已触发运行
    flow = summary["demo_flow"]
    assert flow["rule_set"] is True
    assert flow["activated"] is True
    assert flow["sim_template"] is True
    assert flow["workflow"] is True
    assert flow["submission_id"] is not None
    assert flow["runs"] >= 1

    # 账号：三员 + 普通用户（含 reviewer）
    names = {u["username"] for u in summary["users"]}
    assert {"sec_admin", "audit_admin", "designer", "reviewer", "demo"} <= names

    # 项目 / 迭代：首轮迭代已激活，另有规划态迭代供演示状态流转
    from iterd.plugins.projects.models import Iteration, Project
    from iterd.plugins.rules.models import CheckRun, RuleSet
    from iterd.plugins.workflows.models import WorkflowRun

    projects = _rows(select(Project))
    demo = next(p for p in projects if p.code == "DEMO")
    iters = _rows(select(Iteration).where(Iteration.project_id == demo.id).order_by(Iteration.number))
    assert len(iters) == 2
    assert iters[0].status == "active"
    assert iters[1].status == "planned"

    # 演示规则集（项目级）供规则检查作业引用
    sets = _rows(select(RuleSet))
    demo_set = next(rs for rs in sets if rs.name == "演示规则集")
    assert demo_set.project_id == demo.id

    # 预置提交方案：运行已触发（trigger=submission）且执行成功
    runs = _rows(select(WorkflowRun).where(WorkflowRun.iteration_id == iters[0].id))
    assert len(runs) == 1
    assert runs[0].submission_id == flow["submission_id"]
    assert runs[0].trigger == "submission"
    assert runs[0].status == "succeeded"

    # 流水线产出的检查运行：演示数据全绿（检查通过，无 error 发现项）
    checks = _rows(select(CheckRun).where(CheckRun.iteration_id == iters[0].id))
    assert len(checks) == 1
    assert checks[0].status == "succeeded"
    assert checks[0].summary is not None
    assert checks[0].summary["error"] == 0


def test_seed_overwrite_rebuild(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """重复 seed 覆盖重建：业务数据整体重建（演示流程全部重新生成），账号与审计日志保留."""
    from iterd.plugins.accounts.models import User
    from iterd.plugins.projects.models import Iteration, Project
    from iterd.plugins.rules.models import CheckRun, RuleItem, RuleSet
    from iterd.plugins.workflows.models import WorkflowRun

    _maker, _first, second = store

    # 二次执行摘要：覆盖重建后演示流程内容全部重新生成，提交方案与运行随之重建
    flow = second["demo_flow"]
    assert all(flow[key] is True for key in ("rule_set", "activated", "sim_template", "workflow"))
    assert flow["submission_id"] is not None and flow["runs"] >= 1
    assert all(not u["created"] for u in second["users"])  # 账号沿用，不重复建号

    # 无残留无重复：DEMO 项目仅 1 个、演示迭代 2 个、规则编码唯一、规则集仅演示 1 个 + 案例 N 个
    assert len([p for p in _rows(select(Project)) if p.code == "DEMO"]) == 1
    demo = next(p for p in _rows(select(Project)) if p.code == "DEMO")
    assert len(_rows(select(Iteration).where(Iteration.project_id == demo.id))) == 2
    rule_codes = [r.code for r in _rows(select(RuleItem))]
    assert len(rule_codes) == len(set(rule_codes))
    assert len(_rows(select(RuleSet))) == len({rs.name for rs in _rows(select(RuleSet))})

    # 演示迭代运行重建为 1 次（旧运行已随覆盖清空，二次 seed 不新增提交）
    demo_iters = _rows(select(Iteration).where(Iteration.project_id == demo.id).order_by(Iteration.number))
    runs = _rows(select(WorkflowRun).where(WorkflowRun.iteration_id == demo_iters[0].id))
    assert len(runs) == 1
    checks = _rows(select(CheckRun).where(CheckRun.iteration_id == demo_iters[0].id))
    assert len(checks) == 1

    # 用户与审计日志保留
    assert len(_rows(select(User))) >= 6


def test_seed_typical_cases(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """seed 载入全部典型案例：数据集项目齐备，检查/仿真已预执行至终态."""
    import json

    from iterd.example_datasets import list_datasets
    from iterd.plugins.artifacts.models import Artifact, ArtifactVersion
    from iterd.plugins.projects.models import Iteration, Project
    from iterd.plugins.rules.models import CheckFinding, CheckRun, RuleItem, RuleSet
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

    # 发现项与数据集基线一致：逐数据集比对 CheckRun summary 与 finding 明细
    # （规则/级别/产物/位置与消息，保证"检查问题存在发现项时界面上可见具体内容"）
    for dataset in list_datasets():
        baseline = json.loads((dataset / "预期检查结果.json").read_text(encoding="utf-8"))
        proj = _rows(select(Project).where(Project.code == baseline["iteration"]["project_code"]))[0]
        iteration = _rows(
            select(Iteration).where(
                Iteration.project_id == proj.id, Iteration.number == baseline["iteration"]["number"]
            )
        )[0]
        # 规则集可能是全局（project_id 为空）或项目级，通过 CheckRun 联 RuleSet 按名称定位
        check_runs = _row_tuples(
            select(CheckRun, RuleSet)
            .join(RuleSet, CheckRun.rule_set_id == RuleSet.id)
            .where(CheckRun.iteration_id == iteration.id, RuleSet.name == baseline["rule_set"])
        )
        if not check_runs:
            # 该数据集 runs 未预执行 rules/check（如 AXLE 全绿仿真演示），基线仅供手动门禁模板演示
            continue
        assert len(check_runs) == 1, f"{dataset.name}: 检查运行数量异常"
        check_run = check_runs[0][0]

        run_summary = dict(check_run.summary or {})
        for key, want in baseline["expected_summary"].items():
            assert run_summary.get(key) == want, f"{dataset.name}: summary.{key}={run_summary.get(key)} 期望 {want}"

        actual = [
            {
                "rule_code": rule_code,
                "severity": finding.severity,
                "artifact_code": artifact_code,
                "location": finding.location,
                "message": finding.message,
            }
            for finding, rule_code, artifact_code in _row_tuples(
                select(CheckFinding, RuleItem.code, Artifact.code)
                .join(RuleItem, CheckFinding.rule_item_id == RuleItem.id)
                .join(ArtifactVersion, CheckFinding.artifact_version_id == ArtifactVersion.id, isouter=True)
                .join(Artifact, ArtifactVersion.artifact_id == Artifact.id, isouter=True)
                .where(CheckFinding.check_run_id == check_run.id)
            )
        ]
        expected = baseline["expected_findings"]
        assert len(actual) == len(expected), f"{dataset.name}: 发现项 {len(actual)} 条，基线 {len(expected)} 条"
        for item in expected:
            matched = [
                a
                for a in actual
                if a["rule_code"] == item["rule_code"]
                and a["severity"] == item["severity"]
                and a["artifact_code"] == item["artifact_code"]
                and a["location"] == item["location"]
            ]
            assert matched, f"{dataset.name}: 基线发现项缺失 {item['rule_code']}@{item['artifact_code']}"
            assert any(item["message_contains"] in a["message"] for a in matched), (
                f"{dataset.name}: {item['rule_code']}@{item['artifact_code']} 消息不含 {item['message_contains']!r}"
            )


def test_seed_notifications_baseline(
    store: tuple[async_sessionmaker[AsyncSession], dict[str, Any], dict[str, Any]],
) -> None:
    """通知触达基线：数据集 expected_notifications 与实际站内信一致（按项目隔离计数）."""
    import json

    from iterd.example_datasets import list_datasets
    from iterd.plugins.accounts.models import User
    from iterd.plugins.notify.models import Notification
    from iterd.plugins.projects.models import Project

    if not list_datasets():
        pytest.skip("非源码仓库（无 examples/datasets），跳过典型案例断言")

    _maker, _summary, _second = store
    baselines = []
    for dataset in list_datasets():
        baseline = json.loads((dataset / "预期检查结果.json").read_text(encoding="utf-8"))
        if baseline.get("expected_notifications"):
            baselines.append((dataset, baseline))
    assert baselines, "至少一个数据集声明通知触达基线"

    for dataset, baseline in baselines:
        proj = _rows(select(Project).where(Project.code == baseline["iteration"]["project_code"]))[0]
        users = {u.username: u for u in _rows(select(User))}
        for username, wanted in baseline["expected_notifications"].items():
            notifications = _rows(
                select(Notification).where(
                    Notification.user_id == users[username].id,
                    Notification.project_id == proj.id,
                )
            )
            counts: dict[str, int] = {}
            for item in notifications:
                counts[item.ntype] = counts.get(item.ntype, 0) + 1
            want_counts = {w["ntype"]: int(w["count"]) for w in wanted}
            assert counts == want_counts, f"{dataset.name}: {username} 通知 {counts} 期望 {want_counts}"
