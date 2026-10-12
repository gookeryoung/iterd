"""reports 服务层：迭代对比 diff / 审查报告 Markdown 生成 / 报告归档.

只读聚合：对比与报告所需数据均来自既有插件（artifacts / rules / simulation /
workflows / bom），本服务不落新表；归档复用 artifacts 服务上传 result 产物。
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.plugins.artifacts.models import Artifact, ArtifactVersion
from iterd.plugins.bom.models import BomItem
from iterd.plugins.projects.models import Iteration, Project
from iterd.plugins.reports.schemas import ApprovalSummary, EntryDiff, SeverityCounts, SimSnapshot
from iterd.plugins.rules.models import CheckFinding, CheckRun, RuleItem
from iterd.plugins.simulation.models import SimJob, SimResult
from iterd.plugins.workflows.models import ApprovalRecord, WorkflowJob, WorkflowRun

# 对比报告产物编码前缀（项目内唯一：RPT-IT<迭代序号>）
REPORT_CODE_TEMPLATE = "RPT-IT{number}"

_ARTIFACT_COMPARE_FIELDS = ("name", "category")
_BOM_COMPARE_FIELDS = ("part_name", "material", "spec", "quantity", "unit_weight", "note")


def _brief(iteration: Iteration) -> dict[str, Any]:
    """迭代简要信息。"""
    return {"id": iteration.id, "number": iteration.number, "title": iteration.title, "status": iteration.status}


async def select_baseline(session: AsyncSession, iteration: Iteration) -> Iteration | None:
    """自动选取基线：同项目内编号更小且已关闭的最近迭代；无则返回 None。"""
    stmt = (
        select(Iteration)
        .where(
            Iteration.project_id == iteration.project_id,
            Iteration.number < iteration.number,
            Iteration.status == "closed",
        )
        .order_by(Iteration.number.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _entity_diff(
    base_map: dict[str, dict[str, Any]],
    curr_map: dict[str, dict[str, Any]],
    compare: tuple[str, ...],
    label: str,
) -> dict[str, list[dict[str, Any]]]:
    """键控实体集合差异：新增 / 移除 / 字段级变更（label 为键名字，如 code / part_code）。"""
    changed: list[dict[str, Any]] = []
    for key, curr in curr_map.items():
        base = base_map.get(key)
        if base is None:
            continue
        for field in compare:
            if base.get(field) != curr.get(field):
                changed.append({label: key, "field": field, "base": base.get(field), "current": curr.get(field)})
    return {
        "added": [dict(curr, **{label: key}) for key, curr in curr_map.items() if key not in base_map],
        "removed": [dict(base, **{label: key}) for key, base in base_map.items() if key not in curr_map],
        "changed": changed,
    }


async def _artifact_snapshot(session: AsyncSession, iteration_id: int) -> dict[str, dict[str, Any]]:
    """产物快照：code → 名称/类别/当前版本元数据（元数据字段级参与对比）。"""
    from iterd.plugins.artifacts.services import list_artifacts

    snapshot: dict[str, dict[str, Any]] = {}
    for artifact in await list_artifacts(session, iteration_id=iteration_id):
        metadata: dict[str, Any] = {}
        if artifact.current_version_id is not None:
            version = await session.get(ArtifactVersion, artifact.current_version_id)
            if version is not None:
                metadata = dict(version.metadata_json or {})
        snapshot[artifact.code] = {
            "name": artifact.name,
            "category": artifact.category,
            **{f"元数据.{key}": value for key, value in metadata.items()},
        }
    return snapshot


async def _bom_snapshot(session: AsyncSession, iteration_id: int) -> dict[str, dict[str, Any]]:
    """BOM 快照：part_code → 台账字段。"""
    rows = (
        await session.execute(select(BomItem).where(BomItem.iteration_id == iteration_id).order_by(BomItem.id))
    ).scalars()
    return {item.part_code: {field: getattr(item, field) for field in _BOM_COMPARE_FIELDS} for item in rows}


async def _latest_run(session: AsyncSession, iteration_id: int) -> WorkflowRun | None:
    """迭代最近一次成功完成的审查运行（无则 None）。"""
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.iteration_id == iteration_id, WorkflowRun.status == "succeeded")
        .order_by(WorkflowRun.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _latest_check_run(session: AsyncSession, iteration_id: int) -> CheckRun | None:
    """迭代最近一次成功的检查运行。"""
    stmt = (
        select(CheckRun)
        .where(CheckRun.iteration_id == iteration_id, CheckRun.status == "succeeded")
        .order_by(CheckRun.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _latest_sim(session: AsyncSession, iteration_id: int) -> SimSnapshot | None:
    """迭代最近一次成功仿真作业的结论快照。"""
    stmt = (
        select(SimJob, SimResult)
        .join(SimResult, SimResult.sim_job_id == SimJob.id)
        .where(SimJob.iteration_id == iteration_id, SimJob.status == "succeeded")
        .order_by(SimJob.id.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    result = row[1]
    return SimSnapshot(verdict=result.verdict, failures=result.failures)


async def _approval_summary(session: AsyncSession, run: WorkflowRun | None) -> ApprovalSummary | None:
    """运行审批摘要：通过 / 驳回计数与仍在等待的审批作业数（无运行时 None）。"""
    if run is None:
        return None
    records = list((await session.execute(select(ApprovalRecord).where(ApprovalRecord.run_id == run.id))).scalars())
    waiting_jobs = (
        await session.execute(
            select(func.count())
            .select_from(WorkflowJob)
            .where(WorkflowJob.run_id == run.id, WorkflowJob.job_type == "approval", WorkflowJob.status == "waiting")
        )
    ).scalar_one()
    return ApprovalSummary(
        approved=sum(1 for r in records if r.decision == "approved"),
        rejected=sum(1 for r in records if r.decision == "rejected"),
        pending_jobs=int(waiting_jobs),
    )


def _severity_counts(check_run: CheckRun | None) -> SeverityCounts | None:
    """检查运行发现项计数（无检查运行时 None）。"""
    if check_run is None:
        return None
    summary = dict(check_run.summary or {})
    return SeverityCounts(**{level: int(summary.get(level, 0)) for level in ("error", "warning", "info")})


async def iteration_diff(session: AsyncSession, *, iteration: Iteration, baseline: Iteration | None) -> dict[str, Any]:
    """迭代 vs 基线的结构化差异（产物 / BOM / 结论计数 / 仿真 / 审批）."""
    base_artifacts: dict[str, dict[str, Any]] = {}
    base_bom: dict[str, dict[str, Any]] = {}
    base_findings = None
    base_sims = None
    base_approvals = None
    if baseline is not None:
        base_artifacts = await _artifact_snapshot(session, baseline.id)
        base_bom = await _bom_snapshot(session, baseline.id)
        base_findings = _severity_counts(await _latest_check_run(session, baseline.id))
        base_sims = await _latest_sim(session, baseline.id)
        base_approvals = await _approval_summary(session, await _latest_run(session, baseline.id))

    return {
        "iteration": _brief(iteration),
        "baseline": _brief(baseline) if baseline is not None else None,
        "note": "" if baseline is not None else "无可用基线（项目内不存在编号更小且已关闭的迭代）",
        "artifacts": EntryDiff(
            **_entity_diff(
                base_artifacts, await _artifact_snapshot(session, iteration.id), _ARTIFACT_COMPARE_FIELDS, "code"
            )
        ),
        "bom": EntryDiff(
            **_entity_diff(base_bom, await _bom_snapshot(session, iteration.id), _BOM_COMPARE_FIELDS, "part_code")
        ),
        "findings": {
            "baseline": base_findings,
            "current": _severity_counts(await _latest_check_run(session, iteration.id)),
        },
        "sims": {"baseline": base_sims, "current": await _latest_sim(session, iteration.id)},
        "approvals": {
            "baseline": base_approvals,
            "current": await _approval_summary(session, await _latest_run(session, iteration.id)),
        },
    }


def _fmt(value: Any) -> str:
    """Markdown 表格单元格格式化（None → -）。"""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


async def _report_findings_section(session: AsyncSession, check_run: CheckRun | None) -> list[str]:
    """报告「发现明细」段：最近一次检查运行的逐条发现项。"""
    if check_run is None:
        return ["（无检查运行）"]
    rows = (
        await session.execute(
            select(CheckFinding, RuleItem)
            .join(RuleItem, RuleItem.id == CheckFinding.rule_item_id)
            .where(CheckFinding.check_run_id == check_run.id)
            .order_by(CheckFinding.id)
            .limit(200)
        )
    ).all()
    if not rows:
        return ["（无发现项）"]
    lines = [
        "| 严重度 | 产物版本 | 位置 | 规则 | 消息 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for finding, rule in rows:
        lines.append(
            f"| {finding.severity} | {finding.artifact_version_id or '迭代级'}"
            f" | {_fmt(finding.location)} | {rule.code} {rule.name} | {_fmt(finding.message)} |"
        )
    return lines


async def _report_sims_section(session: AsyncSession, iteration_id: int) -> list[str]:
    """报告「仿真指标判定」段：迭代内全部成功仿真的逐项判定明细。"""
    jobs = (
        await session.execute(
            select(SimJob, SimResult)
            .join(SimResult, SimResult.sim_job_id == SimJob.id)
            .where(SimJob.iteration_id == iteration_id, SimJob.status == "succeeded")
            .order_by(SimJob.id)
        )
    ).all()
    if not jobs:
        return ["（无仿真作业）"]
    lines = ["| 仿真作业 | 结论 | 指标 | 值 | 阈值 | 判定 |", "| --- | --- | --- | --- | --- | --- |"]
    for job, result in jobs:
        if not result.detail:
            lines.append(f"| #{job.id} | {result.verdict} | - | - | - | - |")
            continue
        for item in result.detail:
            thresholds = " ".join(f"{op}={_fmt(item.get(op))}" for op in ("min", "max") if item.get(op) is not None)
            lines.append(
                f"| #{job.id} | {result.verdict} | {_fmt(item.get('label'))} | {_fmt(item.get('value'))}"
                f" {_fmt(item.get('unit'))} | {thresholds or '-'} | {'通过' if item.get('passed') else '超阈'} |"
            )
    return lines


async def build_report_markdown(session: AsyncSession, iteration: Iteration) -> str:
    """按迭代聚合生成审查报告 Markdown（检查汇总 / 发现明细 / 仿真判定 / 审批记录）."""
    project = await session.get(Project, iteration.project_id)
    run = await _latest_run(session, iteration.id)
    check_run = await _latest_check_run(session, iteration.id)
    approval_rows: list[ApprovalRecord] = []
    if run is not None:
        approval_rows = list(
            (
                await session.execute(
                    select(ApprovalRecord).where(ApprovalRecord.run_id == run.id).order_by(ApprovalRecord.id)
                )
            ).scalars()
        )

    summary = dict(check_run.summary or {}) if check_run is not None else {}
    counts = "、".join(f"{level} {int(summary.get(level, 0))}" for level in ("error", "warning", "info"))
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    lines = [
        f"# 审查报告：迭代 {iteration.number} {iteration.title}",
        "",
        f"- 项目：{project.code} {project.name}" if project is not None else "- 项目：-",
        f"- 生成时间：{generated_at}",
        f"- 最近审查运行：#{run.id}（{run.workflow_code}）" if run is not None else "- 最近审查运行：（无）",
        "",
        "## 一、检查汇总",
        "",
        f"- 最近检查运行：#{check_run.id}（结论 {check_run.status}）"
        if check_run is not None
        else "- 最近检查运行：（无）",
        f"- 发现项计数：{counts}" if check_run is not None else "- 发现项计数：-",
        "",
        "## 二、发现明细",
        "",
        *(await _report_findings_section(session, check_run)),
        "",
        "## 三、仿真指标判定",
        "",
        *(await _report_sims_section(session, iteration.id)),
        "",
        "## 四、审批记录",
        "",
    ]
    if not approval_rows:
        lines.append("（无审批记录）")
    else:
        lines += ["| 审批人 | 决定 | 意见 |", "| --- | --- | --- |"]
        lines += [
            f"| {record.approver_name} | {'通过' if record.decision == 'approved' else '驳回'} | {_fmt(record.comment)} |"
            for record in approval_rows
        ]
    return "\n".join(lines) + "\n"


async def archive_report(
    session: AsyncSession, *, actor_id: int, iteration: Iteration, markdown: str
) -> dict[str, Any]:
    """报告归档：以 result 产物上传（已存在同编码产物则追加上传新版本）."""
    from iterd.plugins.artifacts.services import create_artifact, upload_version

    code = REPORT_CODE_TEMPLATE.format(number=iteration.number)
    artifact = (
        await session.execute(
            select(Artifact).where(
                Artifact.project_id == iteration.project_id,
                Artifact.code == code,
                Artifact.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        artifact = await create_artifact(
            session,
            actor_id=actor_id,
            project_id=iteration.project_id,
            iteration_id=iteration.id,
            code=code,
            name=f"审查报告-迭代{iteration.number}",
            category="result",
            description=f"迭代 {iteration.number} 审查报告（平台自动归档）",
        )
    version = await upload_version(
        session,
        actor_id=actor_id,
        artifact=artifact,
        filename=f"{code}.md",
        content_type="text/markdown",
        stream=io.BytesIO(markdown.encode()),
        metadata={
            "kind": "review_report",
            "iteration_id": iteration.id,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        note="审查报告归档",
    )
    return {"artifact_id": artifact.id, "artifact_code": artifact.code, "version_no": version.version_no}


async def get_checked_iteration(
    session: AsyncSession, iteration_id: int, baseline_id: int | None
) -> tuple[Iteration, Iteration | None]:
    """取迭代与基线迭代（baseline 缺省自动选前序 closed 迭代；跨项目/自引用 422）。"""
    from iterd.core.errors import IterdError
    from iterd.plugins.projects import services as project_services

    iteration = await project_services.get_iteration(session, iteration_id)
    if baseline_id is None:
        return iteration, await select_baseline(session, iteration)
    baseline = await project_services.get_iteration(session, baseline_id)
    if baseline.project_id != iteration.project_id:
        raise IterdError("基线迭代须属于同一项目", code="ITERD-BASELINE_INVALID", status_code=422)
    if baseline.id == iteration.id:
        raise IterdError("基线迭代不能是当前迭代自身", code="ITERD-BASELINE_INVALID", status_code=422)
    return iteration, baseline


__all__ = [
    "REPORT_CODE_TEMPLATE",
    "archive_report",
    "build_report_markdown",
    "get_checked_iteration",
    "iteration_diff",
    "select_baseline",
]
