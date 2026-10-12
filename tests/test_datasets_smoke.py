"""示例数据集冒烟回归（slow）：进程内载入数据集并执行审查流水线，断言预期检查结果.

参数化覆盖 examples/datasets/ 下含 ``预期检查结果.json`` 的全部数据集
（新数据集落盘即自动纳入回归，无需改本文件）；
数据载入与流水线执行与 CLI（scripts/load_example.py）/ seed 共用
:mod:`iterd.example_datasets` 实现，不新增载入路径。
未入流水线的检查运行（runs 无 rules/check 作业，如传动轴数据集）与仿真
（超载展示工况 / 会签挂起下游作业）按预期文件直接补跑，
与流水线作业共用同一服务层入口（execute_check_run / execute_sim_job）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from iterd.example_datasets import DEMO_USERS, list_datasets, load_dataset, read_json, run_workflows_sync


def _expected_datasets() -> list[Path]:
    """含预期检查结果的数据集目录（参数化来源，按名称排序）。"""
    return [d for d in list_datasets() if (d / "预期检查结果.json").is_file()]


def _dataset_id(path: Path) -> str:
    """参数化测试 ID：数据集目录名。"""
    return path.name


def _hint_float(value: Any) -> float:
    """metrics_hint 数值解析：数字直接取用，"≈1.23" 形态的字符串取数值部分。"""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    for prefix in ("≈", "~"):
        text = text.removeprefix(prefix).strip()
    return float(text)


@pytest.fixture()
def maker(env: Path) -> Generator[tuple[async_sessionmaker[AsyncSession], int], None, None]:
    """alembic 建库 + 管理员与演示用户就绪，返回 (会话工厂, 载入操作者 id)."""
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.core.migrations import upgrade_head
    from iterd.plugins import accounts, artifacts, bom, notify, projects, rules, simulation, trace, workflows  # noqa: F401
    from iterd.plugins.accounts.services import create_user, get_by_username
    from iterd.seed import ensure_admin

    upgrade_head()
    engine = get_engine(get_settings().database_url)
    factory = get_session_factory(engine)

    async def _prepare() -> int:
        async with factory() as session:
            await ensure_admin(session, "admin", "admin1234")
            for username, (password, email) in DEMO_USERS.items():
                if await get_by_username(session, username) is None:
                    await create_user(session, username=username, password=password, email=email)
            await session.commit()
            admin = await get_by_username(session, "admin")
            assert admin is not None
            return int(admin.id)

    actor_id = asyncio.run(_prepare())
    yield factory, actor_id
    asyncio.run(engine.dispose())


async def _execute_dataset(
    session: AsyncSession, dataset: Path, *, actor_id: int
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """载入数据集并预执行流水线，返回（预期文件, 检查摘要列表, 发现项列表, 仿真判定列表）.

    未入流水线的检查运行与仿真按预期文件补跑，断言所需数据一次收集齐。
    """
    from iterd.plugins.artifacts.models import Artifact, ArtifactVersion
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.rules.models import CheckFinding, CheckRun, RuleItem
    from iterd.plugins.simulation import services as sim_services
    from iterd.plugins.simulation.models import SimJob, SimResult, SimTemplate

    loaded = await load_dataset(session, dataset, actor_id=actor_id)
    expected = read_json(dataset / "预期检查结果.json")
    # 流水线作业失败会触发 session.rollback() 并使已载入 ORM 对象过期，
    # 所需 id 须在预执行前固化为普通 int（expire_on_commit=False 不覆盖 rollback）
    index = loaded["index"]
    iteration_key = (str(expected["iteration"]["project_code"]), int(expected["iteration"]["number"]))
    iteration_id = int(index["iterations"][iteration_key].id)
    rule_set_id = int(loaded["sets"][str(expected["rule_set"])].id)
    version_ids = {code: int(version.id) for code, version in loaded["versions"].items()}
    await run_workflows_sync(session, dataset, loaded, actor_id=actor_id)

    # 检查运行：流水线已产出的直接取用，runs 未覆盖时补跑一次
    runs = list(
        (
            await session.execute(
                select(CheckRun).where(CheckRun.iteration_id == iteration_id, CheckRun.rule_set_id == rule_set_id)
            )
        ).scalars()
    )
    if not runs:
        check_run = CheckRun(iteration_id=iteration_id, rule_set_id=rule_set_id, status="pending")
        session.add(check_run)
        await session.flush()
        await rule_services.execute_check_run(session, check_run_id=int(check_run.id))
        runs = [check_run]
    summaries = [dict(check_run.summary or {}) for check_run in runs]

    # 发现项：联表还原规则编码与产物编码（与预期文件同构）
    rows = list(
        (
            await session.execute(
                select(CheckFinding, RuleItem.code, Artifact.code)
                .join(RuleItem, CheckFinding.rule_item_id == RuleItem.id)
                .outerjoin(ArtifactVersion, CheckFinding.artifact_version_id == ArtifactVersion.id)
                .outerjoin(Artifact, ArtifactVersion.artifact_id == Artifact.id)
                .where(CheckFinding.check_run_id.in_(int(check_run.id) for check_run in runs))
            )
        ).all()
    )
    findings = [
        {
            "rule_code": rule_code,
            "severity": finding.severity,
            "artifact_code": artifact_code or "",
            "location": finding.location,
            "message": finding.message,
        }
        for finding, rule_code, artifact_code in rows
    ]

    # 仿真：流水线已产出的直接取用，未入流水线的按预期绑定补跑
    simulations: list[dict[str, Any]] = []
    for entry in expected.get("expected_simulations", []):
        template = (
            (await session.execute(select(SimTemplate).where(SimTemplate.code == entry["template_code"])))
            .scalars()
            .one()
        )
        job = (
            (
                await session.execute(
                    select(SimJob)
                    .where(SimJob.iteration_id == iteration_id, SimJob.template_id == template.id)
                    .order_by(SimJob.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if job is None:
            job = SimJob(
                iteration_id=iteration_id,
                template_id=template.id,
                artifact_version_id=version_ids.get(entry["bind_artifact_code"]),
                status="pending",
                created_by=actor_id,
            )
            session.add(job)
            await session.flush()
            await sim_services.execute_sim_job(session, job_id=int(job.id))
        await session.commit()
        result = (
            (await session.execute(select(SimResult).where(SimResult.sim_job_id == job.id))).scalars().one_or_none()
        )
        detail: list[dict[str, Any]] = list(result.detail or []) if result is not None else []
        simulations.append(
            {
                "entry": entry,
                "verdict": result.verdict if result is not None else str((job.summary or {}).get("verdict") or "fail"),
                "failed_keys": sorted(str(item["key"]) for item in detail if not item["passed"]),
                "metrics": dict(result.metrics or {}) if result is not None else {},
            }
        )
    return expected, summaries, findings, simulations


@pytest.mark.slow
@pytest.mark.parametrize("dataset", _expected_datasets(), ids=_dataset_id)
def test_dataset_expected_results(maker: tuple[async_sessionmaker[AsyncSession], int], dataset: Path) -> None:
    """数据集实跑结果与预期检查结果一致：检查摘要 / 发现项 / 仿真 verdict 与超阈键."""
    factory, actor_id = maker

    async def _run() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        async with factory() as session:
            return await _execute_dataset(session, dataset, actor_id=actor_id)

    expected, summaries, findings, simulations = asyncio.run(_run())

    # 检查运行摘要：全量一致（多次运行与补跑均为确定性结果）
    assert summaries, "未产生检查运行"
    assert summaries == [dict(expected["expected_summary"])] * len(summaries)

    # 发现项：逐条对上且数量无多余
    expected_findings = list(expected.get("expected_findings", []))
    assert len(findings) == len(expected_findings), f"发现项数量不符: {findings}"
    remaining = list(findings)
    for want in expected_findings:
        match = next(
            (
                got
                for got in remaining
                if got["rule_code"] == want["rule_code"]
                and got["severity"] == want["severity"]
                and (got["artifact_code"] or None) == want["artifact_code"]
                and want["message_contains"] in got["message"]
            ),
            None,
        )
        assert match is not None, f"缺少预期发现项: {want}（实际 {findings}）"
        remaining.remove(match)

    # 仿真：verdict / 超阈键 / 指标宽松比对（metrics_hint 为基线快照，≈x 形态仅保留 2-3 位有效数字，
    # 容差 1% 防公式四舍五入回填误报）
    for sim in simulations:
        entry = sim["entry"]
        assert sim["verdict"] == entry["verdict"], f"{entry['template_code']} verdict 不符"
        want_keys = entry.get("failed_keys")
        if want_keys is not None:
            assert sim["failed_keys"] == sorted(want_keys), f"{entry['template_code']} 超阈键不符: {sim['failed_keys']}"
        for key, hint in (entry.get("metrics_hint") or {}).items():
            assert key in sim["metrics"], f"{entry['template_code']} 缺少指标 {key}"
            assert sim["metrics"][key] == pytest.approx(_hint_float(hint), rel=1e-2)
