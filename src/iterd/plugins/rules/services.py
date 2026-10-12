"""rules 服务层：规则库 / 规则集 / 检查执行."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.checkers import ArtifactRef, BomItemRef, Finding, get_checker
from iterd.core.errors import IterdError, not_found
from iterd.plugins.artifacts.models import Artifact, ArtifactVersion
from iterd.plugins.notify import audit
from iterd.plugins.rules.models import (
    CheckFinding,
    CheckRun,
    RuleItem,
    RuleSet,
    RuleSetItem,
)


async def get_rule(session: AsyncSession, rule_id: int) -> RuleItem:
    """取规则，不存在抛 404."""
    rule = await session.get(RuleItem, rule_id)
    if rule is None:
        raise not_found(f"规则不存在: {rule_id}")
    return rule


async def list_rules(session: AsyncSession, *, category: str | None = None) -> list[RuleItem]:
    """规则列表（按分类过滤）。"""
    stmt = select(RuleItem).order_by(RuleItem.id)
    if category is not None:
        stmt = stmt.where(RuleItem.category == category)
    return list((await session.execute(stmt)).scalars())


async def create_rule(session: AsyncSession, *, actor_id: int, **fields: object) -> RuleItem:
    """创建规则条目（code 唯一），注册溯源节点."""
    dup = (await session.execute(select(RuleItem.id).where(RuleItem.code == str(fields["code"])))).scalar_one_or_none()
    if dup is not None:
        raise IterdError(f"规则编码已存在: {fields['code']}", code="ITERD-DUPLICATE_CODE")
    rule = RuleItem(**fields)  # type: ignore[arg-type]
    session.add(rule)
    await session.flush()
    from iterd.plugins.trace import register

    await register(
        session, node_type="rule_item", ref_table="rule_items", ref_id=rule.id, display_name=f"{rule.code} {rule.name}"
    )
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="rule.create",
        resource_type="rule",
        resource_id=rule.id,
        after={"code": rule.code},
    )
    return rule


async def update_rule(session: AsyncSession, *, actor_id: int, rule: RuleItem, fields: dict[str, object]) -> RuleItem:
    """更新规则条目."""
    for key, value in fields.items():
        setattr(rule, key, value)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="rule.update",
        resource_type="rule",
        resource_id=rule.id,
        after=dict(fields),
    )
    return rule


# ---- 规则集 ----


async def get_rule_set(session: AsyncSession, rule_set_id: int) -> RuleSet:
    """取规则集，不存在抛 404."""
    rule_set = await session.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise not_found(f"规则集不存在: {rule_set_id}")
    return rule_set


async def get_rule_set_rules(session: AsyncSession, rule_set_id: int) -> list[int]:
    """规则集内的规则 id 列表。"""
    rows = (
        await session.execute(
            select(RuleSetItem.rule_item_id).where(RuleSetItem.rule_set_id == rule_set_id).order_by(RuleSetItem.id)
        )
    ).scalars()
    return [int(r) for r in rows]


async def set_rule_set_rules(session: AsyncSession, *, rule_set_id: int, rule_ids: list[int]) -> list[int]:
    """向规则集批量添加规则（幂等，已存在跳过）。"""
    await get_rule_set(session, rule_set_id)
    for rule_id in rule_ids:
        await add_rule_to_set(session, rule_set_id=rule_set_id, rule_id=rule_id)
    return await get_rule_set_rules(session, rule_set_id)


async def list_rule_sets(session: AsyncSession, *, project_id: int | None = None) -> list[RuleSet]:
    """规则集列表：给定 project 时含全局（project_id IS NULL）。"""
    stmt = select(RuleSet).order_by(RuleSet.id)
    if project_id is not None:
        stmt = stmt.where((RuleSet.project_id == project_id) | (RuleSet.project_id.is_(None)))
    return list((await session.execute(stmt)).scalars())


async def create_rule_set(  # noqa: PLR0913 - 规则集字段
    session: AsyncSession,
    *,
    actor_id: int,
    project_id: int | None,
    name: str,
    description: str = "",
    rule_ids: list[int] | None = None,
) -> RuleSet:
    """创建规则集并挂成员规则."""
    rule_set = RuleSet(project_id=project_id, name=name, description=description)
    session.add(rule_set)
    await session.flush()
    for rule_id in rule_ids or []:
        await add_rule_to_set(session, rule_set_id=rule_set.id, rule_id=rule_id)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="rule_set.create",
        resource_type="rule_set",
        resource_id=rule_set.id,
        after={"name": name},
    )
    return rule_set


async def add_rule_to_set(session: AsyncSession, *, rule_set_id: int, rule_id: int) -> RuleSetItem:
    """向规则集添加规则（幂等）。"""
    await get_rule(session, rule_id)
    existing = (
        await session.execute(
            select(RuleSetItem.id).where(RuleSetItem.rule_set_id == rule_set_id, RuleSetItem.rule_item_id == rule_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        item = RuleSetItem(rule_set_id=rule_set_id, rule_item_id=rule_id)
        session.add(item)
        await session.flush()
        return item
    return await session.get(RuleSetItem, existing)  # type: ignore[return-value]


@dataclass
class FindingRecord:
    """发现项 + 规则/产物展示信息（报告页免二次查询；迭代级发现项产物信息为 None）。"""

    finding: CheckFinding
    rule_code: str
    rule_name: str
    artifact_code: str | None
    artifact_name: str | None
    version_no: int | None


async def list_findings(  # noqa: PLR0913 - 过滤参数
    session: AsyncSession,
    *,
    check_run_id: int,
    severity: str | None = None,
    artifact_version_id: int | None = None,
    rule_item_id: int | None = None,
    limit: int = 500,
) -> list[FindingRecord]:
    """结构化报告查询：按严重级别/产物版本/规则过滤，联表带出规则与产物信息.

    context 检查器的迭代级发现项无产物版本关联（artifact_version_id 为空），产物信息经外联保留为空。
    """
    stmt = (
        select(CheckFinding, RuleItem, Artifact, ArtifactVersion)
        .join(RuleItem, RuleItem.id == CheckFinding.rule_item_id)
        .join(ArtifactVersion, ArtifactVersion.id == CheckFinding.artifact_version_id, isouter=True)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id, isouter=True)
        .where(CheckFinding.check_run_id == check_run_id)
    )
    if severity is not None:
        stmt = stmt.where(CheckFinding.severity == severity)
    if artifact_version_id is not None:
        stmt = stmt.where(CheckFinding.artifact_version_id == artifact_version_id)
    if rule_item_id is not None:
        stmt = stmt.where(CheckFinding.rule_item_id == rule_item_id)
    stmt = stmt.order_by(CheckFinding.id).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [
        FindingRecord(
            finding=finding,
            rule_code=rule.code,
            rule_name=rule.name,
            artifact_code=artifact.code if artifact is not None else None,
            artifact_name=artifact.name if artifact is not None else None,
            version_no=version.version_no if version is not None else None,
        )
        for finding, rule, artifact, version in rows
    ]


async def get_check_run_task_id(session: AsyncSession, check_run_id: int) -> int | None:
    """取检查运行对应的任务 id（用于前端 WS 订阅进度）。"""
    from iterd.tasks.models import Task

    row = (
        await session.execute(
            select(Task.id).where(
                Task.task_type == "check_run",
                Task.payload["check_run_id"].as_integer() == check_run_id,
            )
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


# ---- 检查执行（worker 侧）----


async def _load_artifact_refs(session: AsyncSession, iteration_id: int) -> list[ArtifactRef]:
    """加载迭代内全部产物当前版本为检查输入。"""
    stmt = (
        select(Artifact, ArtifactVersion)
        .join(ArtifactVersion, ArtifactVersion.id == Artifact.current_version_id)
        .where(Artifact.iteration_id == iteration_id, Artifact.deleted_at.is_(None))
        .order_by(Artifact.id)
    )
    refs: list[ArtifactRef] = []
    for artifact, version in (await session.execute(stmt)).all():
        refs.append(
            ArtifactRef(
                artifact_id=artifact.id,
                artifact_code=artifact.code,
                artifact_name=artifact.name,
                version_id=version.id,
                version_no=version.version_no,
                filename=version.filename,
                metadata=dict(version.metadata_json or {}),
                category=artifact.category,
            )
        )
    return refs


async def _load_bom_item_refs(session: AsyncSession, iteration_id: int) -> list[BomItemRef]:
    """加载迭代 BOM 行为跨产物检查输入（bom 插件未启用时为空）。"""
    from iterd.plugins.bom import services as bom_services

    items = await bom_services.list_bom(session, iteration_id=iteration_id)
    return [
        BomItemRef(
            part_code=item.part_code,
            part_name=item.part_name,
            material=item.material,
            spec=item.spec,
            quantity=item.quantity,
            unit_weight=item.unit_weight,
            note=item.note,
        )
        for item in items
    ]


async def _load_rule_refs(session: AsyncSession, rule_set_id: int) -> list[tuple[Any, RuleItem]]:
    """加载规则集内启用规则。"""
    stmt = (
        select(RuleSetItem, RuleItem)
        .join(RuleItem, RuleItem.id == RuleSetItem.rule_item_id)
        .where(RuleSetItem.rule_set_id == rule_set_id, RuleItem.enabled.is_(True))
        .order_by(RuleItem.id)
    )
    return [(item, rule) for item, rule in (await session.execute(stmt)).all()]


def _group_rules_by_checker(rules: list[RuleItem]) -> dict[str, list[RuleItem]]:
    """按 checker_type 分组。"""
    grouped: dict[str, list[RuleItem]] = {}
    for rule in rules:
        grouped.setdefault(rule.checker_type, []).append(rule)
    return grouped


async def execute_check_run(
    session: AsyncSession, *, check_run_id: int, progress: Any = None, log: Any = None
) -> dict[str, Any]:
    """执行检查：单产物规则逐产物分发、context 规则整迭代分发，findings 先清后写（幂等），聚合 summary."""
    from asyncio import Semaphore, gather

    from iterd.checkers import CheckContext
    from iterd.checkers.registry import checker_kind, get_context_checker
    from iterd.plugins.projects.models import Iteration

    check_run = await session.get(CheckRun, check_run_id)
    if check_run is None:
        raise not_found(f"检查运行不存在: {check_run_id}")
    check_run.status = "running"
    check_run.started_at = datetime.now(UTC)
    await session.commit()

    artifacts = await _load_artifact_refs(session, check_run.iteration_id)
    grouped_rules = _group_rules_by_checker([r for _, r in await _load_rule_refs(session, check_run.rule_set_id)])
    artifact_groups = {ct: rules for ct, rules in grouped_rules.items() if checker_kind(ct) == "artifact"}
    context_groups = {ct: rules for ct, rules in grouped_rules.items() if checker_kind(ct) == "context"}
    context: CheckContext | None = None
    if context_groups:
        iteration = await session.get(Iteration, check_run.iteration_id)
        if iteration is None:
            raise not_found(f"迭代不存在: {check_run.iteration_id}")
        context = CheckContext(
            project_id=iteration.project_id,
            iteration_id=iteration.id,
            iteration_no=iteration.number,
            iteration_title=iteration.title,
            artifacts=artifacts,
            bom_items=await _load_bom_item_refs(session, check_run.iteration_id),
        )
    if progress is not None:
        progress("加载产物与规则", 10)

    sem = Semaphore(4)

    async def check_one(
        artifact: ArtifactRef, checker_type: str, rules: list[RuleItem]
    ) -> list[tuple[ArtifactRef, Finding]]:
        async with sem:
            if log is not None:
                log("info", f"检查 {artifact.artifact_code} with {checker_type}")
            checker = get_checker(checker_type)
            rule_refs = [
                _rule_ref(rule)
                for rule in rules
                if not checker.supported_extensions()
                or artifact.filename.lower().endswith(checker.supported_extensions())
            ]
            return [(artifact, f) for f in checker.check(artifact, rule_refs)]

    tasks_total = sum(len(rules) for rules in grouped_rules.values()) * max(len(artifacts), 1)
    done = 0

    async def run_group(checker_type: str, rules: list[RuleItem]) -> list[tuple[ArtifactRef | None, Finding]]:
        nonlocal done
        results = await gather(*(check_one(a, checker_type, rules) for a in artifacts))
        done += len(artifacts)
        if progress is not None and tasks_total:
            progress("检查执行", int(10 + 80 * done / max(tasks_total, 1)))
        return [pair for part in results for pair in part]

    async def run_context_group(checker_type: str, rules: list[RuleItem]) -> list[tuple[ArtifactRef | None, Finding]]:
        """context 检查器整迭代执行一次（不逐产物分发）。"""
        if log is not None:
            log("info", f"跨产物检查 with {checker_type}")
        checker = get_context_checker(checker_type)
        assert context is not None
        rule_refs = [_rule_ref(rule) for rule in rules]
        return [(None, f) for f in checker.check(context, rule_refs)]

    group_results = await gather(
        *(
            [run_group(ct, rules) for ct, rules in artifact_groups.items()]
            + [run_context_group(ct, rules) for ct, rules in context_groups.items()]
        )
    )
    pairs: list[tuple[ArtifactRef | None, Finding]] = [p for part in group_results for p in part]
    findings = [f for _, f in pairs]

    if progress is not None:
        progress("写入报告", 95)
    # 幂等：重跑先清空自身 findings 再写入
    await session.execute(delete(CheckFinding).where(CheckFinding.check_run_id == check_run.id))
    for artifact, f in pairs:
        version_id = (
            f.artifact_version_id
            if f.artifact_version_id is not None
            else (artifact.version_id if artifact is not None else None)
        )
        session.add(
            CheckFinding(
                check_run_id=check_run.id,
                artifact_version_id=version_id,
                rule_item_id=f.rule_id,
                severity=f.severity,
                location=f.location,
                message=f.message,
            )
        )
    summary = {
        "error": sum(1 for f in findings if f.severity == "error"),
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "artifacts": len(artifacts),
        "rules": sum(len(rules) for rules in grouped_rules.values()),
    }
    check_run.summary = summary
    check_run.status = "succeeded"
    check_run.finished_at = datetime.now(UTC)

    # 溯源：finding → 产物版本 validated_by（迭代级发现项无版本关联，仅登记节点）
    await _trace_findings(session, check_run.id, artifacts)
    await session.commit()
    if progress is not None:
        progress("完成", 100)
    return summary


def _rule_ref(rule: RuleItem) -> Any:
    from iterd.checkers import RuleRef

    return RuleRef(
        rule_id=rule.id, code=rule.code, name=rule.name, params=dict(rule.params or {}), severity=rule.severity_default
    )


async def _trace_findings(session: AsyncSession, check_run_id: int, artifacts: list[ArtifactRef]) -> None:
    """检查完成后建立溯源：finding 节点 → 产物版本 validated_by."""
    from iterd.plugins.trace import ensure_link, register
    from iterd.plugins.trace.models import TraceNode

    findings = list(
        (await session.execute(select(CheckFinding).where(CheckFinding.check_run_id == check_run_id))).scalars()
    )
    version_urns: dict[str, str] = {}
    for ref in artifacts:
        u = (
            await session.execute(
                select(TraceNode.urn).where(
                    TraceNode.ref_table == "artifact_versions", TraceNode.ref_id == str(ref.version_id)
                )
            )
        ).scalar_one_or_none()
        if u:
            version_urns[str(ref.version_id)] = u
    for finding in findings:
        urn = await register(
            session,
            node_type="check_finding",
            ref_table="check_findings",
            ref_id=finding.id,
            display_name=finding.message[:80],
        )
        # 迭代级发现项（如 BOM 缺件）无版本关联，仅登记发现项节点
        target = version_urns.get(str(finding.artifact_version_id)) if finding.artifact_version_id is not None else None
        if target:
            await ensure_link(session, src=target, dst=urn, link_type="validated_by")


async def _check_run_executor(session: AsyncSession, payload: dict[str, Any], ctx: Any) -> Any:
    """check_run 任务执行器：包装 execute_check_run 供 worker 调度."""
    from iterd.tasks.executor import TaskResult

    summary = await execute_check_run(session, check_run_id=payload["check_run_id"], progress=ctx.progress, log=ctx.log)
    return TaskResult(success=True, summary=summary)


def register_executors() -> None:
    """向任务框架注册本插件的执行器（app 启动时调用）。"""
    from iterd.tasks.executor import register_executor

    register_executor("check_run", _check_run_executor)
