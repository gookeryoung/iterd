"""workflows 服务层：审查模板 CRUD / 运行发起（引用解析与快照）/ 编排执行."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError, not_found
from iterd.plugins.notify import audit
from iterd.plugins.workflows.definition import (
    JobDef,
    WorkflowDefinition,
    WorkflowDefinitionError,
    parse_definition,
    topo_layers,
)
from iterd.plugins.workflows.models import WorkflowJob, WorkflowRun, WorkflowTemplate


def _validated(text: str) -> WorkflowDefinition:
    """解析并校验 YAML 定义，失败映射为 422 业务异常."""

    try:
        return parse_definition(text)
    except WorkflowDefinitionError as exc:
        raise IterdError(str(exc), code="ITERD-INVALID_DEFINITION", status_code=422) from exc


# ---- 模板 CRUD ----


async def get_template(session: AsyncSession, template_id: int) -> WorkflowTemplate:
    """取审查模板，不存在抛 404."""
    template = await session.get(WorkflowTemplate, template_id)
    if template is None:
        raise not_found(f"审查模板不存在: {template_id}")
    return template


async def list_templates(session: AsyncSession, *, project_id: int | None = None) -> list[WorkflowTemplate]:
    """模板列表：给定 project 时含全局（project_id IS NULL）。"""
    stmt = select(WorkflowTemplate).order_by(WorkflowTemplate.id)
    if project_id is not None:
        stmt = stmt.where((WorkflowTemplate.project_id == project_id) | (WorkflowTemplate.project_id.is_(None)))
    return list((await session.execute(stmt)).scalars())


async def create_template(session: AsyncSession, *, actor_id: int, **fields: object) -> WorkflowTemplate:
    """创建审查模板（code 唯一、YAML 校验），注册溯源节点."""
    dup = (
        await session.execute(select(WorkflowTemplate.id).where(WorkflowTemplate.code == str(fields["code"])))
    ).scalar_one_or_none()
    if dup is not None:
        raise IterdError(f"审查模板编码已存在: {fields['code']}", code="ITERD-DUPLICATE_CODE")
    _validated(str(fields["definition"]))
    template = WorkflowTemplate(**fields)  # type: ignore[arg-type]
    session.add(template)
    await session.flush()
    from iterd.plugins.trace import register

    await register(
        session,
        node_type="workflow",
        ref_table="workflows",
        ref_id=template.id,
        display_name=f"{template.code} {template.name}",
    )
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="workflow.create",
        resource_type="workflow",
        resource_id=template.id,
        after={"code": template.code},
    )
    return template


async def update_template(
    session: AsyncSession, *, actor_id: int, template: WorkflowTemplate, fields: dict[str, object]
) -> WorkflowTemplate:
    """更新审查模板（definition 变更时重新校验）。"""
    if "definition" in fields:
        _validated(str(fields["definition"]))
    for key, value in fields.items():
        setattr(template, key, value)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="workflow.update",
        resource_type="workflow",
        resource_id=template.id,
        after=dict(fields),
    )
    return template


# ---- 运行发起（引用解析与快照固化）----


async def _resolve_rule_set(session: AsyncSession, ref: str | int) -> Any:
    """规则集引用解析：int 按 id，str 按名称（多个同名取 id 最小）。"""
    from iterd.plugins.rules.models import RuleSet

    if isinstance(ref, int):
        return await session.get(RuleSet, ref)
    rows = (await session.execute(select(RuleSet).where(RuleSet.name == ref).order_by(RuleSet.id))).scalars()
    return rows.first()


async def _resolve_sim_template(session: AsyncSession, ref: str | int) -> Any:
    """仿真模板引用解析：int 按 id，str 按编码。"""
    from iterd.plugins.simulation.models import SimTemplate

    if isinstance(ref, int):
        return await session.get(SimTemplate, ref)
    rows = (await session.execute(select(SimTemplate).where(SimTemplate.code == ref))).scalars()
    return rows.first()


async def _resolve_artifact_version(session: AsyncSession, *, iteration_id: int, code: str) -> int | None:
    """迭代内产物编码 → 当前版本 id（无版本返回 None）。"""
    from iterd.plugins.artifacts.models import Artifact

    row = (
        await session.execute(
            select(Artifact.current_version_id).where(
                Artifact.iteration_id == iteration_id,
                Artifact.code == code,
                Artifact.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def _resolve_job_config(session: AsyncSession, *, job: JobDef, iteration_id: int) -> dict[str, Any]:
    """解析 with 引用为 ID 并固化（发起时早失败，对齐 workflow lint）。"""
    location = f"jobs.{job.key}.with"
    config: dict[str, Any] = {"uses": job.uses}
    if job.uses == "rules/check":
        rule_set = await _resolve_rule_set(session, job.with_["rule_set"])
        if rule_set is None:
            raise IterdError(
                f"{location}.rule_set: 规则集不存在: {job.with_['rule_set']!r}",
                code="ITERD-INVALID_DEFINITION",
                status_code=422,
            )
        config["rule_set_id"] = int(rule_set.id)
        config["rule_set_name"] = rule_set.name
    else:  # simulation/run
        template = await _resolve_sim_template(session, job.with_["template"])
        if template is None:
            raise IterdError(
                f"{location}.template: 仿真模板不存在: {job.with_['template']!r}",
                code="ITERD-INVALID_DEFINITION",
                status_code=422,
            )
        if not template.enabled:
            raise IterdError(
                f"{location}.template: 仿真模板已停用: {template.code}",
                code="ITERD-INVALID_DEFINITION",
                status_code=422,
            )
        config["template_id"] = int(template.id)
        config["template_code"] = template.code
        if "artifact" in job.with_:
            version_id = await _resolve_artifact_version(
                session, iteration_id=iteration_id, code=str(job.with_["artifact"])
            )
            if version_id is None:
                raise IterdError(
                    f"{location}.artifact: 迭代内产物不存在或无版本: {job.with_['artifact']!r}",
                    code="ITERD-INVALID_DEFINITION",
                    status_code=422,
                )
            config["artifact_version_id"] = version_id
        if "inputs" in job.with_:
            config["inputs"] = dict(job.with_["inputs"])
    return config


async def _create_run_from(  # noqa: PLR0913 - 快照发起参数
    session: AsyncSession,
    *,
    actor_id: int,
    iteration_id: int,
    workflow_id: int,
    workflow_code: str,
    definition_text: str,
    action: str,
) -> tuple[WorkflowRun, Any]:
    """以给定定义文本发起运行：快照固化 + 逐 job 引用解析 + Task 创建（同事务）。"""
    from iterd.plugins.projects.models import Iteration
    from iterd.tasks.models import Task

    if await session.get(Iteration, iteration_id) is None:
        raise not_found(f"迭代不存在: {iteration_id}")
    definition = _validated(definition_text)
    run = WorkflowRun(
        iteration_id=iteration_id,
        workflow_id=workflow_id,
        workflow_code=workflow_code,
        definition=definition_text,
        status="pending",
        created_by=actor_id,
    )
    session.add(run)
    await session.flush()

    job_map = definition.job_map()
    order = 0
    for layer in topo_layers(definition):
        for key in layer:
            job_def = job_map[key]
            config = await _resolve_job_config(session, job=job_def, iteration_id=iteration_id)
            session.add(
                WorkflowJob(
                    run_id=run.id,
                    job_key=key,
                    name=job_def.name,
                    job_type=job_def.uses.split("/")[0],
                    needs=job_def.needs,
                    config=config,
                    status="pending",
                    order_index=order,
                )
            )
            order += 1
    await session.flush()

    task = Task(task_type="workflow_run", payload={"workflow_run_id": run.id}, status="pending")
    session.add(task)
    await session.flush()
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action=action,
        resource_type="workflow_run",
        resource_id=run.id,
        after={"iteration_id": iteration_id, "workflow_code": workflow_code},
    )
    return run, task


async def create_workflow_run(
    session: AsyncSession, *, actor_id: int, iteration_id: int, template_id: int
) -> tuple[WorkflowRun, Any]:
    """从模板发起运行（definition 取模板当前文本，发起后模板变更不影响本运行）。"""
    template = await get_template(session, template_id)
    if not template.enabled:
        raise IterdError(f"审查模板已停用: {template.code}", code="ITERD-INVALID_STATE")
    return await _create_run_from(
        session,
        actor_id=actor_id,
        iteration_id=iteration_id,
        workflow_id=template.id,
        workflow_code=template.code,
        definition_text=template.definition,
        action="workflow_run.create",
    )


async def rerun_workflow_run(session: AsyncSession, *, actor_id: int, run: WorkflowRun) -> tuple[WorkflowRun, Any]:
    """以运行快照重新执行（生成新 run，对齐 GitHub Re-run 新 attempt 语义）。"""
    return await _create_run_from(
        session,
        actor_id=actor_id,
        iteration_id=run.iteration_id,
        workflow_id=run.workflow_id,
        workflow_code=run.workflow_code,
        definition_text=run.definition,
        action="workflow_run.rerun",
    )


async def get_run(session: AsyncSession, run_id: int) -> WorkflowRun:
    """取运行，不存在抛 404."""
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise not_found(f"审查运行不存在: {run_id}")
    return run


async def list_runs(session: AsyncSession, *, iteration_id: int) -> list[WorkflowRun]:
    """迭代下运行列表（按 id 升序）。"""
    return list(
        (
            await session.execute(
                select(WorkflowRun).where(WorkflowRun.iteration_id == iteration_id).order_by(WorkflowRun.id)
            )
        ).scalars()
    )


async def list_jobs(session: AsyncSession, *, run_id: int) -> list[WorkflowJob]:
    """运行下全部作业（按 order_index）。"""
    return list(
        (
            await session.execute(
                select(WorkflowJob).where(WorkflowJob.run_id == run_id).order_by(WorkflowJob.order_index)
            )
        ).scalars()
    )


async def get_run_task_id(session: AsyncSession, run_id: int) -> int | None:
    """取运行对应任务 id（前端 WS 订阅进度用）。"""
    from iterd.tasks.models import Task

    row = (
        await session.execute(
            select(Task.id).where(
                Task.task_type == "workflow_run",
                Task.payload["workflow_run_id"].as_integer() == run_id,
            )
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def job_display_map(session: AsyncSession, jobs: list[WorkflowJob]) -> dict[int, dict[str, Any]]:
    """批量取作业绑定展示信息：规则集名 / 模板编码名求解器 / 产物编码版本号。"""
    from iterd.plugins.artifacts.models import Artifact, ArtifactVersion
    from iterd.plugins.rules.models import RuleSet
    from iterd.plugins.simulation.models import SimTemplate

    displays: dict[int, dict[str, Any]] = {}
    rule_set_ids = [int(j.config["rule_set_id"]) for j in jobs if j.config and "rule_set_id" in (j.config or {})]
    template_ids = [int(j.config["template_id"]) for j in jobs if j.config and "template_id" in (j.config or {})]
    version_ids = [
        int(j.config["artifact_version_id"]) for j in jobs if j.config and "artifact_version_id" in (j.config or {})
    ]

    rule_sets: dict[int, str] = {}
    if rule_set_ids:
        rows = (await session.execute(select(RuleSet.id, RuleSet.name).where(RuleSet.id.in_(rule_set_ids)))).all()
        rule_sets = {int(r[0]): str(r[1]) for r in rows}
    templates: dict[int, tuple[str, str, str]] = {}
    if template_ids:
        rows = (
            await session.execute(
                select(SimTemplate.id, SimTemplate.code, SimTemplate.name, SimTemplate.solver_type).where(
                    SimTemplate.id.in_(template_ids)
                )
            )
        ).all()
        templates = {int(r[0]): (str(r[1]), str(r[2]), str(r[3])) for r in rows}
    versions: dict[int, tuple[str, int]] = {}
    if version_ids:
        rows = (
            await session.execute(
                select(Artifact.code, ArtifactVersion.version_no, ArtifactVersion.id)
                .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
                .where(ArtifactVersion.id.in_(version_ids))
            )
        ).all()
        versions = {int(r[2]): (str(r[0]), int(r[1])) for r in rows}

    for job in jobs:
        config = job.config or {}
        display: dict[str, Any] = {
            "rule_set_name": rule_sets.get(int(config["rule_set_id"]), "") if "rule_set_id" in config else "",
            "template_code": "",
            "template_name": "",
            "solver_type": "",
            "artifact_code": "",
            "version_no": None,
        }
        if "template_id" in config and int(config["template_id"]) in templates:
            code, name, solver = templates[int(config["template_id"])]
            display["template_code"] = code
            display["template_name"] = name
            display["solver_type"] = solver
        if "artifact_version_id" in config and int(config["artifact_version_id"]) in versions:
            acode, vno = versions[int(config["artifact_version_id"])]
            display["artifact_code"] = acode
            display["version_no"] = vno
        displays[int(job.id)] = display
    return displays


# ---- 编排执行（worker 侧）----


def _append_log(job: WorkflowJob, level: str, message: str) -> None:
    """追加作业日志（JSON 字段整体重赋值以触发脏检测）。"""
    job.logs = [*(job.logs or []), {"level": level, "message": message}]


async def _run_rules_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> None:
    """静态规则检查作业：直建 CheckRun（不建 Task，避免嵌套调度）+ 复用 execute_check_run."""
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.rules.models import CheckRun, RuleSet

    config = job.config or {}
    rule_set = await session.get(RuleSet, int(config["rule_set_id"]))
    check_run = CheckRun(iteration_id=run.iteration_id, rule_set_id=int(config["rule_set_id"]), status="pending")
    session.add(check_run)
    await session.flush()
    job.check_run_id = int(check_run.id)
    _append_log(
        job, "info", f"规则集 {rule_set.name if rule_set else config['rule_set_id']} → 检查运行 #{check_run.id}"
    )
    await session.commit()

    summary = await rule_services.execute_check_run(session, check_run_id=int(check_run.id))
    errors = int((summary or {}).get("error") or 0)
    warnings = int((summary or {}).get("warning") or 0)
    infos = int((summary or {}).get("info") or 0)
    _append_log(job, "info", f"发现项 error={errors} warning={warnings} info={infos}")
    job.status = "succeeded"
    job.conclusion = "success" if errors == 0 else "failure"
    if errors > 0:
        _append_log(job, "error", f"存在 {errors} 条 error 级发现项，作业判定为 failure")
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def _run_simulation_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> None:
    """动态仿真作业：直建 SimJob（不建 Task）+ 复用 execute_sim_job."""
    from iterd.plugins.simulation import services as sim_services
    from iterd.plugins.simulation.models import SimJob, SimTemplate

    config = job.config or {}
    template = await session.get(SimTemplate, int(config["template_id"]))
    sim_job = SimJob(
        iteration_id=run.iteration_id,
        template_id=int(config["template_id"]),
        artifact_version_id=config.get("artifact_version_id"),
        inputs=config.get("inputs") or None,
        status="pending",
        created_by=run.created_by,
    )
    session.add(sim_job)
    await session.flush()
    job.sim_job_id = int(sim_job.id)
    label = f"{template.code} {template.name}" if template else str(config["template_id"])
    _append_log(job, "info", f"仿真模板 {label} → 仿真作业 #{sim_job.id}")
    await session.commit()

    summary = await sim_services.execute_sim_job(session, job_id=int(sim_job.id))
    verdict = str((summary or {}).get("verdict") or "fail")
    _append_log(job, "info", f"求解完成 verdict={verdict} failures={(summary or {}).get('failures', 0)}")
    job.status = "succeeded"
    job.conclusion = "success" if verdict == "pass" else "failure"
    if verdict != "pass":
        _append_log(job, "error", "存在超阈指标，作业判定为 failure")
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def _execute_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> None:
    """执行单作业：异常捕获记 failure 并继续（不中断整链）。"""
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()
    try:
        if job.job_type == "rules":
            await _run_rules_job(session, run=run, job=job)
        else:
            await _run_simulation_job(session, run=run, job=job)
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WorkflowJob, job.id)
        if failed is not None:
            failed.status = "failed"
            failed.conclusion = "failure"
            failed.finished_at = datetime.now(UTC)
            _append_log(failed, "error", f"执行异常: {type(exc).__name__}: {exc}"[:500])
            await _mark_bound_failure(session, failed)
            await session.commit()


async def _mark_bound_failure(session: AsyncSession, job: WorkflowJob) -> None:
    """作业异常时把绑定的 CheckRun/SimJob 一并置 failed（SimJob 异常路径已自置）。"""
    from iterd.plugins.rules.models import CheckRun
    from iterd.plugins.simulation.models import SimJob

    if job.check_run_id is not None:
        check_run = await session.get(CheckRun, job.check_run_id)
        if check_run is not None and check_run.status not in ("succeeded", "failed"):
            check_run.status = "failed"
            check_run.finished_at = datetime.now(UTC)
    if job.sim_job_id is not None:
        sim_job = await session.get(SimJob, job.sim_job_id)
        if sim_job is not None and sim_job.status not in ("succeeded", "failed"):
            sim_job.status = "failed"
            sim_job.finished_at = datetime.now(UTC)


async def _aggregate_summary(session: AsyncSession, jobs: list[WorkflowJob]) -> dict[str, Any]:
    """运行结论聚合：作业计数 + 发现项分级计数 + 仿真通过计数。"""
    from iterd.plugins.rules.models import CheckRun
    from iterd.plugins.simulation.models import SimJob

    findings = {"error": 0, "warning": 0, "info": 0}
    sims = {"pass": 0, "fail": 0}
    check_run_ids = [int(j.check_run_id) for j in jobs if j.check_run_id is not None]
    if check_run_ids:
        rows = (await session.execute(select(CheckRun.summary).where(CheckRun.id.in_(check_run_ids)))).scalars()
        for summary in rows:
            for level in findings:
                findings[level] += int((summary or {}).get(level) or 0)
    sim_job_ids = [int(j.sim_job_id) for j in jobs if j.sim_job_id is not None]
    if sim_job_ids:
        rows = (await session.execute(select(SimJob.summary).where(SimJob.id.in_(sim_job_ids)))).scalars()
        for summary in rows:
            verdict = str((summary or {}).get("verdict") or "")
            if verdict in sims:
                sims[verdict] += 1
    conclusion = "failure" if any(j.conclusion == "failure" for j in jobs) else "success"
    return {
        "conclusion": conclusion,
        "jobs": {
            "success": sum(1 for j in jobs if j.conclusion == "success"),
            "failure": sum(1 for j in jobs if j.conclusion == "failure"),
            "skipped": sum(1 for j in jobs if j.conclusion == "skipped"),
        },
        "findings": findings,
        "sims": sims,
    }


async def execute_workflow_run(
    session: AsyncSession, *, run_id: int, progress: Any = None, log: Any = None
) -> dict[str, Any]:
    """编排执行：拓扑分层串行跑作业，needs 门禁（上游非 success → skipped），聚合结论."""
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise not_found(f"审查运行不存在: {run_id}")
    definition = _validated(run.definition)
    layers = topo_layers(definition)
    run.status = "running"
    run.started_at = datetime.now(UTC)
    await session.commit()

    jobs = await list_jobs(session, run_id=run_id)
    job_map = {job.job_key: job for job in jobs}
    total = max(len(jobs), 1)
    done = 0
    for layer in layers:
        for key in layer:
            job = job_map.get(key)
            if job is None:
                continue
            needs = job.needs or []
            if any(job_map[dep].conclusion != "success" for dep in needs if dep in job_map):
                job.status = "skipped"
                job.conclusion = "skipped"
                _append_log(job, "warning", "上游作业未通过，本作业跳过")
                await session.commit()
                done += 1
                if progress is not None:
                    progress(f"作业 {job.name}", int(100 * done / total))
                continue
            if log is not None:
                log("info", f"执行作业 {job.name}")
            await _execute_job(session, run=run, job=job)
            done += 1
            if progress is not None:
                progress(f"作业 {job.name}", int(100 * done / total))

    jobs = await list_jobs(session, run_id=run_id)
    summary = await _aggregate_summary(session, jobs)
    run.summary = summary
    run.status = "failed" if summary["conclusion"] == "failure" else "succeeded"
    run.finished_at = datetime.now(UTC)
    await session.commit()
    if progress is not None:
        progress("完成", 100)
    return summary


async def _workflow_run_executor(session: AsyncSession, payload: dict[str, Any], ctx: Any) -> Any:
    """workflow_run 任务执行器：包装 execute_workflow_run 供 worker 调度."""
    from iterd.tasks.executor import TaskResult

    run_id = int(payload["workflow_run_id"])
    try:
        summary = await execute_workflow_run(session, run_id=run_id, progress=ctx.progress, log=ctx.log)
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WorkflowRun, run_id)
        if failed is not None:
            failed.status = "failed"
            failed.finished_at = datetime.now(UTC)
            await session.commit()
        return TaskResult(success=False, error=f"{type(exc).__name__}: {exc}"[:1000])
    return TaskResult(success=True, summary=summary)


def register_executors() -> None:
    """向任务框架注册本插件的执行器（app 启动时调用）。"""
    from iterd.tasks.executor import register_executor

    register_executor("workflow_run", _workflow_run_executor)
