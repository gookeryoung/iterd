"""workflows 服务层：审查模板 CRUD / 运行发起（引用解析与快照）/ 编排执行."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError, not_found, permission_denied
from iterd.plugins.notify import audit
from iterd.plugins.workflows.definition import (
    JobDef,
    WorkflowDefinition,
    WorkflowDefinitionError,
    parse_definition,
    topo_layers,
)
from iterd.plugins.workflows.models import (
    JOB_STEP_SEQUENCES,
    IterationSubmission,
    WorkflowJob,
    WorkflowJobStep,
    WorkflowRun,
    WorkflowTemplate,
)


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
    elif job.uses == "simulation/run":
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
    else:  # approval/request
        config["approvers"] = [str(a) for a in job.with_["approvers"]]
        config["min_count"] = int(job.with_.get("min_count", 1))
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
    trigger: str = "manual",
    submission_id: int | None = None,
) -> tuple[WorkflowRun, Any]:
    """以给定定义文本发起运行：快照固化 + 逐 job 引用解析 + 步骤生成 + Task 创建（同事务）。"""
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
        submission_id=submission_id,
        trigger=trigger,
    )
    session.add(run)
    await session.flush()

    job_map = definition.job_map()
    order = 0
    created_jobs: list[WorkflowJob] = []
    for layer in topo_layers(definition):
        for key in layer:
            job_def = job_map[key]
            config = await _resolve_job_config(session, job=job_def, iteration_id=iteration_id)
            job = WorkflowJob(
                run_id=run.id,
                job_key=key,
                name=job_def.name,
                job_type=job_def.uses.split("/")[0],
                needs=job_def.needs,
                config=config,
                status="pending",
                order_index=order,
            )
            session.add(job)
            created_jobs.append(job)
            order += 1
    await session.flush()

    # 平台内置步骤序列：作业创建时同步生成（全 pending）
    for job in created_jobs:
        for step_index, (step_key, step_name) in enumerate(JOB_STEP_SEQUENCES.get(job.job_type, ())):
            session.add(
                WorkflowJobStep(
                    job_id=job.id,
                    step_key=step_key,
                    name=step_name,
                    status="pending",
                    order_index=step_index,
                )
            )
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
    """以运行快照重新执行（生成新 run，对齐 GitHub Re-run 新 attempt 语义；继承提交归属）。"""
    return await _create_run_from(
        session,
        actor_id=actor_id,
        iteration_id=run.iteration_id,
        workflow_id=run.workflow_id,
        workflow_code=run.workflow_code,
        definition_text=run.definition,
        action="workflow_run.rerun",
        trigger="rerun",
        submission_id=run.submission_id,
    )


# ---- 提交方案 ----


async def create_submission(
    session: AsyncSession, *, actor_id: int, iteration_id: int, title: str, note: str
) -> tuple[IterationSubmission, list[WorkflowRun]]:
    """提交迭代方案：为项目可见的每个启用模板各创建一条运行（trigger=submission）."""
    from iterd.plugins.projects.models import Iteration
    from iterd.plugins.trace import register

    iteration = await session.get(Iteration, iteration_id)
    if iteration is None:
        raise not_found(f"迭代不存在: {iteration_id}")
    if iteration.status != "active":
        raise IterdError(
            f"迭代状态为 {iteration.status}，仅 active 迭代可提交方案",
            code="ITERD-INVALID_STATE",
            status_code=422,
        )
    submission = IterationSubmission(iteration_id=iteration_id, title=title, note=note, submitted_by=actor_id)
    session.add(submission)
    await session.flush()
    await register(
        session,
        node_type="submission",
        ref_table="iteration_submissions",
        ref_id=submission.id,
        display_name=f"{iteration.title} · {title}",
    )
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="submission.create",
        resource_type="iteration_submission",
        resource_id=submission.id,
        after={"iteration_id": iteration_id, "title": title},
    )
    templates = [
        template for template in await list_templates(session, project_id=iteration.project_id) if template.enabled
    ]
    runs: list[WorkflowRun] = []
    for template in templates:
        run, _task = await _create_run_from(
            session,
            actor_id=actor_id,
            iteration_id=iteration_id,
            workflow_id=template.id,
            workflow_code=template.code,
            definition_text=template.definition,
            action="workflow_run.create",
            trigger="submission",
            submission_id=submission.id,
        )
        runs.append(run)
    return submission, runs


async def get_submission(session: AsyncSession, submission_id: int) -> IterationSubmission:
    """取提交方案，不存在抛 404."""
    submission = await session.get(IterationSubmission, submission_id)
    if submission is None:
        raise not_found(f"提交方案不存在: {submission_id}")
    return submission


async def list_submissions(session: AsyncSession, *, iteration_id: int) -> list[IterationSubmission]:
    """迭代下提交方案列表（按 id 降序，最近提交在前）。"""
    return list(
        (
            await session.execute(
                select(IterationSubmission)
                .where(IterationSubmission.iteration_id == iteration_id)
                .order_by(IterationSubmission.id.desc())
            )
        ).scalars()
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


async def list_project_runs(session: AsyncSession, *, project_id: int) -> list[dict[str, Any]]:
    """项目级运行列表（跨迭代汇总，join 迭代序号与标题，按 id 倒序）。"""
    from iterd.plugins.projects.models import Iteration

    rows = (
        await session.execute(
            select(WorkflowRun, Iteration.number, Iteration.title)
            .join(Iteration, WorkflowRun.iteration_id == Iteration.id)
            .where(Iteration.project_id == project_id)
            .order_by(WorkflowRun.id.desc())
        )
    ).all()
    return [
        {
            "id": run.id,
            "iteration_id": run.iteration_id,
            "iteration_number": int(number),
            "iteration_title": str(title),
            "workflow_id": run.workflow_id,
            "workflow_code": run.workflow_code,
            "status": run.status,
            "summary": run.summary,
            "trigger": run.trigger,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "created_at": run.created_at,
        }
        for run, number, title in rows
    ]


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


def _step_ts(job: WorkflowJob) -> float:
    """日志行相对时间戳：相对作业开始时刻的秒数（顺序调用保证非降序）."""
    started = job.started_at
    if started is None:
        return 0.0
    if started.tzinfo is None:  # SQLite 读回 naive，按 UTC 归一
        started = started.replace(tzinfo=UTC)
    return round(max((datetime.now(UTC) - started).total_seconds(), 0.0), 3)


def _append_log(job: WorkflowJob, level: str, message: str) -> None:
    """追加作业级日志（生命周期事件；JSON 字段整体重赋值以触发脏检测）。"""
    job.logs = [*(job.logs or []), {"ts": _step_ts(job), "level": level, "message": message}]


def _append_step_log(step: WorkflowJobStep, job: WorkflowJob, level: str, message: str) -> None:
    """追加步骤日志（ts 为相对作业开始秒数）。"""
    step.logs = [*(step.logs or []), {"ts": _step_ts(job), "level": level, "message": message}]


async def job_steps(session: AsyncSession, *, job_ids: list[int]) -> dict[int, list[WorkflowJobStep]]:
    """批量取作业步骤（按 job 分组，order_index 升序）。"""
    if not job_ids:
        return {}
    grouped: dict[int, list[WorkflowJobStep]] = {}
    rows = (
        await session.execute(
            select(WorkflowJobStep)
            .where(WorkflowJobStep.job_id.in_(job_ids))
            .order_by(WorkflowJobStep.job_id, WorkflowJobStep.order_index)
        )
    ).scalars()
    for step in rows:
        grouped.setdefault(int(step.job_id), []).append(step)
    return grouped


async def _start_step(session: AsyncSession, step: WorkflowJobStep) -> None:
    """步骤进入 running（先行提交，异常兜底可定位失败步骤）。"""
    step.status = "running"
    step.started_at = datetime.now(UTC)
    await session.commit()


def _finish_step(step: WorkflowJobStep, *, conclusion: str) -> None:
    """步骤执行完毕（report/evaluate 判定 failure 时 status 仍为 succeeded，红 X 落在 conclusion）。"""
    step.status = "succeeded"
    step.conclusion = conclusion
    step.finished_at = datetime.now(UTC)


async def _run_rules_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> None:
    """静态规则检查作业：setup（解析配置建 CheckRun）→ check（执行）→ report（判定结论）."""
    from iterd.plugins.rules import services as rule_services
    from iterd.plugins.rules.models import CheckRun, RuleSet

    steps = {s.step_key: s for s in (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])}
    setup, check, report = steps["setup"], steps["check"], steps["report"]
    config = job.config or {}

    # setup：解析配置（规则集解析与固化）
    await _start_step(session, setup)
    rule_set = await session.get(RuleSet, int(config["rule_set_id"]))
    if rule_set is None:
        raise IterdError(f"规则集不存在: {config['rule_set_id']}", code="ITERD-INVALID_STATE", status_code=422)
    check_run = CheckRun(iteration_id=run.iteration_id, rule_set_id=int(config["rule_set_id"]), status="pending")
    session.add(check_run)
    await session.flush()
    job.check_run_id = int(check_run.id)
    _append_step_log(setup, job, "info", f"规则集 {rule_set.name} → 检查运行 #{check_run.id}")
    _finish_step(setup, conclusion="success")
    await session.commit()

    # check：执行规则检查
    await _start_step(session, check)
    summary = await rule_services.execute_check_run(session, check_run_id=int(check_run.id))
    errors = int((summary or {}).get("error") or 0)
    warnings = int((summary or {}).get("warning") or 0)
    infos = int((summary or {}).get("info") or 0)
    _append_step_log(check, job, "info", f"发现项 error={errors} warning={warnings} info={infos}")
    _finish_step(check, conclusion="success")
    await session.commit()

    # report：判定结论（error>0 → failure，红 X 落在本步骤）
    await _start_step(session, report)
    conclusion = "success" if errors == 0 else "failure"
    if errors > 0:
        _append_step_log(report, job, "error", f"存在 {errors} 条 error 级发现项，判定为 failure")
    _finish_step(report, conclusion=conclusion)
    job.status = "succeeded"
    job.conclusion = conclusion
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def _run_simulation_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> None:
    """动态仿真作业：setup（解析配置建 SimJob）→ solve（执行仿真）→ evaluate（阈值判定）."""
    from iterd.plugins.simulation import services as sim_services
    from iterd.plugins.simulation.models import SimJob, SimTemplate

    steps = {s.step_key: s for s in (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])}
    setup, solve, evaluate = steps["setup"], steps["solve"], steps["evaluate"]
    config = job.config or {}

    # setup：解析配置（模板/产物版本）
    await _start_step(session, setup)
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
    _append_step_log(setup, job, "info", f"仿真模板 {label} → 仿真作业 #{sim_job.id}")
    _finish_step(setup, conclusion="success")
    await session.commit()

    # solve：执行仿真
    await _start_step(session, solve)
    summary = await sim_services.execute_sim_job(session, job_id=int(sim_job.id))
    verdict = str((summary or {}).get("verdict") or "fail")
    _append_step_log(solve, job, "info", f"求解完成 verdict={verdict} failures={(summary or {}).get('failures', 0)}")
    _finish_step(solve, conclusion="success")
    await session.commit()

    # evaluate：阈值判定（verdict=fail → failure，红 X 落在本步骤）
    await _start_step(session, evaluate)
    conclusion = "success" if verdict == "pass" else "failure"
    if verdict != "pass":
        _append_step_log(
            evaluate, job, "error", f"存在超阈指标（failures={(summary or {}).get('failures', 0)}），判定为 failure"
        )
    _finish_step(evaluate, conclusion=conclusion)
    job.status = "succeeded"
    job.conclusion = conclusion
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def _fail_running_step(session: AsyncSession, job: WorkflowJob, exc: Exception) -> None:
    """作业异常兜底：running 步骤置 failed + error 日志，未执行步骤 skipped，作业置 failure."""
    steps = (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])
    for step in steps:
        if step.status == "running":
            step.status = "failed"
            step.conclusion = "failure"
            step.finished_at = datetime.now(UTC)
            _append_step_log(step, job, "error", f"执行异常: {type(exc).__name__}: {exc}"[:500])
        elif step.status == "pending":
            step.status = "skipped"
            step.conclusion = "skipped"
    job.status = "failed"
    job.conclusion = "failure"
    job.finished_at = datetime.now(UTC)
    _append_log(job, "error", f"作业失败: {type(exc).__name__}: {exc}"[:500])
    await _mark_bound_failure(session, job)
    await session.commit()


async def _execute_job(session: AsyncSession, *, run: WorkflowRun, job: WorkflowJob) -> str | None:
    """执行单作业：步骤化推进；异常兜底记 failure 并继续（不中断整链）.

    返回 "waiting" 表示审批作业进入等待人签（编排暂停，审批决定后恢复）。
    """
    job_id = int(job.id)  # 固化主键：rollback 后实例过期，禁止再访问 job.id
    job.status = "running"
    job.started_at = job.started_at or datetime.now(UTC)
    await session.commit()
    try:
        if job.job_type == "rules":
            await _run_rules_job(session, run=run, job=job)
        elif job.job_type == "approval":
            return await _open_approval_job(session, job=job)
        else:
            await _run_simulation_job(session, run=run, job=job)
    except Exception as exc:
        await session.rollback()
        failed = await session.get(WorkflowJob, job_id)
        if failed is not None:
            await _fail_running_step(session, failed, exc)
    return None


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


async def _advance_layer_job(  # noqa: PLR0913 - 单作业推进参数
    session: AsyncSession,
    *,
    run_id: int,
    job_ids: dict[str, int],
    key: str,
    job: WorkflowJob,
    conclusions: dict[str, str | None],
    done: int,
    total: int,
    progress: Any,
    log: Any,
) -> tuple[str, dict[str, Any] | None]:
    """推进拓扑层内单个作业.

    返回 (state, waiting_summary)：state ∈ {"skipped", "done", "waiting"}；
    waiting 时 waiting_summary 为暂停摘要（其余为 None）。
    """
    needs = list(job.needs or [])
    if any(conclusions.get(dep) != "success" for dep in needs if dep in conclusions):
        job.status = "skipped"
        job.conclusion = "skipped"
        _append_log(job, "warning", "上游作业未通过，本作业跳过")
        for step in (await job_steps(session, job_ids=[job_ids[key]])).get(job_ids[key], []):
            step.status = "skipped"
            step.conclusion = "skipped"
        await session.commit()
        return "skipped", None
    if log is not None:
        log("info", f"执行作业 {job.name}")
    current = await session.get(WorkflowRun, run_id)  # 刷新 run：防上游 rollback 过期
    if current is not None:
        waiting = await _execute_job(session, run=current, job=job)
        if waiting == "waiting":
            # 审批等待人签：运行暂停（终态判定延后到审批决定触发续跑）
            current.status = "waiting"
            await session.commit()
            if progress is not None:
                progress(f"等待审批 {job.name}", int(100 * done / total))
            return "waiting", {
                "status": "waiting",
                "awaiting_job_key": key,
                "awaiting_job": job.name,
                "awaiting_job_id": int(job.id),
            }
    return "done", None


async def execute_workflow_run(
    session: AsyncSession, *, run_id: int, progress: Any = None, log: Any = None
) -> dict[str, Any]:
    """编排执行：拓扑分层串行跑作业，needs 门禁（上游非 success → skipped），聚合结论.

    可恢复：已有结论（success/failure/skipped）的作业跳过不重跑；
    审批作业等待人签时运行置 waiting 并暂停，审批决定后再次进入本函数续跑。
    """
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise not_found(f"审查运行不存在: {run_id}")
    if run.status in ("succeeded", "failed"):  # 幂等：终态运行不重跑
        return dict(run.summary or {"conclusion": run.status})
    definition = _validated(run.definition)
    layers = topo_layers(definition)
    run.status = "running"
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    await session.commit()

    jobs = await list_jobs(session, run_id=run_id)
    job_ids = {job.job_key: int(job.id) for job in jobs}
    total = max(len(jobs), 1)
    done = sum(1 for job in jobs if job.conclusion is not None)
    conclusions: dict[str, str | None] = {job.job_key: job.conclusion for job in jobs if job.conclusion is not None}
    for layer in layers:
        for key in layer:
            if key not in job_ids:
                continue
            # 每次迭代重新载入：上游作业异常 rollback 会过期 identity map 中的实例
            job = await session.get(WorkflowJob, job_ids[key])
            if job is None or job.conclusion is not None:  # 恢复续跑：已定结论的作业跳过
                continue
            state, waiting_summary = await _advance_layer_job(
                session,
                run_id=run_id,
                job_ids=job_ids,
                key=key,
                job=job,
                conclusions=conclusions,
                done=done,
                total=total,
                progress=progress,
                log=log,
            )
            if waiting_summary is not None:
                return waiting_summary
            done += 1
            if progress is not None:
                progress(f"作业 {job.name}", int(100 * done / total))
            if state == "skipped":
                conclusions[key] = "skipped"
            else:
                refreshed = await session.get(WorkflowJob, job_ids[key])
                conclusions[key] = refreshed.conclusion if refreshed is not None else None

    jobs = await list_jobs(session, run_id=run_id)
    summary = await _aggregate_summary(session, jobs)
    run = await session.get(WorkflowRun, run_id) or run
    run.summary = summary
    run.status = "failed" if summary["conclusion"] == "failure" else "succeeded"
    run.finished_at = datetime.now(UTC)
    await _notify_run_finished(session, run=run, summary=summary)
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


# ---- 审批会签（流水线内审批作业）----


async def _open_approval_job(session: AsyncSession, *, job: WorkflowJob) -> str:
    """审批作业首次推进：setup（解析配置）→ collect（挂起等待人签）；返回 "waiting"."""
    steps = {s.step_key: s for s in (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])}
    setup, collect, _decide = steps["setup"], steps["collect"], steps["decide"]
    config = job.config or {}
    approvers = ", ".join(str(a) for a in config.get("approvers", []))
    min_count = int(config.get("min_count", 1))

    await _start_step(session, setup)
    _append_step_log(setup, job, "info", f"审批人范围: {approvers}；会签通过需 {min_count} 人")
    _finish_step(setup, conclusion="success")
    await session.commit()

    await _start_step(session, collect)
    _append_step_log(collect, job, "info", f"等待审批意见（0/{min_count}）")
    job.status = "waiting"
    _append_log(job, "warning", f"等待人工审批（需 {min_count} 人通过）")
    await _notify_approval_pending(session, job=job)
    await session.commit()
    return "waiting"


async def _project_role_for_job(session: AsyncSession, job: WorkflowJob, user: Any) -> tuple[int | None, Any]:
    """取审批作业所属项目 id 与用户在该项目的角色（供路由鉴权与资格判定复用）。"""
    from iterd.plugins.accounts.models import User
    from iterd.plugins.projects import rbac
    from iterd.plugins.projects.models import Iteration

    run = await session.get(WorkflowRun, job.run_id)
    iteration = await session.get(Iteration, run.iteration_id) if run is not None else None
    project_id = int(iteration.project_id) if iteration is not None else None
    user_obj = user if isinstance(user, User) else None
    if project_id is None or user_obj is None:
        return project_id, None
    role = await rbac.get_project_role(session, project_id, int(user_obj.id), user_obj.is_superuser)
    return project_id, role


async def _hit_approvers_scope(session: AsyncSession, *, job: WorkflowJob, user: Any) -> bool:
    """approvers 清单命中判断：用户名直接命中，或角色达到清单中任一角色门槛."""
    from iterd.plugins.accounts.models import User
    from iterd.plugins.projects import rbac

    if isinstance(user, User) and user.is_superuser:
        return True
    approvers = [str(a) for a in (job.config or {}).get("approvers", [])]
    username = getattr(user, "username", "") or ""
    if username in approvers:
        return True
    role_names = [a for a in approvers if a in rbac.Role.__members__]
    if not role_names:
        return False
    _project_id, role = await _project_role_for_job(session, job, user)
    return role is not None and any(rbac.role_at_least(role, rbac.Role(name)) for name in role_names)


async def job_approvals(session: AsyncSession, *, job_id: int) -> list[Any]:
    """作业的审批记录（按 id 升序）。"""
    from iterd.plugins.workflows.models import ApprovalRecord

    return list(
        (
            await session.execute(
                select(ApprovalRecord).where(ApprovalRecord.job_id == job_id).order_by(ApprovalRecord.id)
            )
        ).scalars()
    )


async def get_approval_job(session: AsyncSession, job_id: int) -> WorkflowJob:
    """取作业，不存在抛 404。"""
    job = await session.get(WorkflowJob, job_id)
    if job is None:
        raise not_found(f"流水线作业不存在: {job_id}")
    return job


async def _close_approval_job(session: AsyncSession, *, job: WorkflowJob, conclusion: str, note: str) -> None:
    """审批判定落定：collect 收口 → decide 结论 → 作业终态."""
    steps = {s.step_key: s for s in (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])}
    collect, decide = steps["collect"], steps["decide"]
    _finish_step(collect, conclusion="success")
    await _start_step(session, decide)
    level = "info" if conclusion == "success" else "error"
    _append_step_log(decide, job, level, note)
    _finish_step(decide, conclusion=conclusion)
    job.status = "succeeded"
    job.conclusion = conclusion
    job.finished_at = datetime.now(UTC)
    _append_log(job, level, note)
    await session.commit()


async def record_approval(
    session: AsyncSession, *, actor: Any, job_id: int, decision: str, comment: str
) -> tuple[Any, dict[str, Any] | None]:
    """记录一次审批决定；达成会签条件或遇驳回时恢复流水线续跑.

    返回 (审批记录, 恢复后的运行摘要)；未达会签条件时摘要为 None。
    """
    from iterd.plugins.notify import audit
    from iterd.plugins.workflows.models import APPROVAL_DECISIONS, ApprovalRecord

    if decision not in APPROVAL_DECISIONS:
        raise IterdError(f"非法审批决定: {decision!r}", code="ITERD-INVALID_STATE", status_code=422)
    job = await get_approval_job(session, job_id)
    if job.job_type != "approval" or job.status != "waiting":
        raise IterdError(
            f"作业当前状态为 {job.status}，仅等待审批（waiting）的审批作业可签",
            code="ITERD-INVALID_STATE",
            status_code=422,
        )
    if not await _hit_approvers_scope(session, job=job, user=actor):
        raise permission_denied("当前用户不在本作业审批人范围（approvers）内")

    dup = (
        await session.execute(
            select(ApprovalRecord.id).where(ApprovalRecord.job_id == job_id, ApprovalRecord.approver_id == actor.id)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise IterdError("同一审批人对同一作业仅可签署一次", code="ITERD-DUPLICATE_APPROVAL", status_code=422)

    record = ApprovalRecord(
        job_id=job_id,
        run_id=int(job.run_id),
        approver_id=int(actor.id),
        approver_name=str(actor.username),
        decision=decision,
        comment=comment,
    )
    session.add(record)
    await audit(
        session,
        actor_id=int(actor.id),
        actor_name=str(actor.username),
        action="approval.record",
        resource_type="workflow_job",
        resource_id=job_id,
        after={"decision": decision, "comment": comment},
    )
    approval_run = await session.get(WorkflowRun, job.run_id)
    if approval_run is not None:
        await _notify_approval_recorded(session, run=approval_run, actor=actor, decision=decision)
    await session.commit()  # 先落记录再推进，续跑异常不丢签署

    config = job.config or {}
    min_count = int(config.get("min_count", 1))
    if decision == "rejected":
        await _close_approval_job(
            session, job=job, conclusion="failure", note=f"{actor.username} 驳回：{comment or '无意见'}"
        )
        summary = await execute_workflow_run(session, run_id=int(job.run_id))
        return record, summary
    approvals = await job_approvals(session, job_id=job_id)
    passed = sum(1 for r in approvals if r.decision == "approved")
    if passed >= min_count:
        await _close_approval_job(session, job=job, conclusion="success", note=f"会签通过（{passed}/{min_count}）")
        summary = await execute_workflow_run(session, run_id=int(job.run_id))
        return record, summary
    steps = (await job_steps(session, job_ids=[int(job.id)])).get(int(job.id), [])
    for step in steps:
        if step.step_key == "collect" and step.status == "running":
            step.logs = [
                *(step.logs or []),
                {"ts": _step_ts(job), "level": "info", "message": f"已收 {passed}/{min_count} 项通过，继续等待"},
            ]
    await session.commit()
    return record, None


async def list_pending_approvals(
    session: AsyncSession, *, user: Any, project_id: int | None = None
) -> list[dict[str, Any]]:
    """当前用户可见的待审批作业列表（waiting 态审批作业，跨运行汇总）.

    可见性：超级管理员全部；否则须对所属项目具备 viewer+ 角色（含父项目继承）。
    """
    from iterd.plugins.projects import rbac
    from iterd.plugins.projects.models import Iteration

    stmt = (
        select(WorkflowJob, WorkflowRun, Iteration)
        .join(WorkflowRun, WorkflowJob.run_id == WorkflowRun.id)
        .join(Iteration, WorkflowRun.iteration_id == Iteration.id)
        .where(WorkflowJob.job_type == "approval", WorkflowJob.status == "waiting")
        .order_by(WorkflowJob.id)
    )
    if project_id is not None:
        stmt = stmt.where(Iteration.project_id == project_id)
    rows = (await session.execute(stmt)).all()
    items: list[dict[str, Any]] = []
    for job, run, iteration in rows:
        if not user.is_superuser:
            role = await rbac.get_project_role(
                session, int(iteration.project_id), int(user.id), False, include_ancestor=True
            )
            if role is None or not rbac.role_at_least(role, rbac.Role.viewer):
                continue
        approvals = await job_approvals(session, job_id=int(job.id))
        eligible = await _hit_approvers_scope(session, job=job, user=user)
        config = job.config or {}
        items.append(
            {
                "job_id": int(job.id),
                "run_id": int(run.id),
                "workflow_code": run.workflow_code,
                "iteration_id": int(iteration.id),
                "project_id": int(iteration.project_id),
                "job_key": job.job_key,
                "job_name": job.name,
                "approvers": [str(a) for a in config.get("approvers", [])],
                "min_count": int(config.get("min_count", 1)),
                "approved_count": sum(1 for r in approvals if r.decision == "approved"),
                "approvals": [
                    {
                        "approver_name": r.approver_name,
                        "decision": r.decision,
                        "comment": r.comment,
                        "created_at": r.created_at,
                    }
                    for r in approvals
                ],
                "can_approve": eligible,
                "created_at": job.created_at,
            }
        )
    return items


def register_executors() -> None:
    """向任务框架注册本插件的执行器（app 启动时调用）。"""
    from iterd.tasks.executor import register_executor

    register_executor("workflow_run", _workflow_run_executor)


# ---- 域事件 → 站内信（迭代 2：运行终态 / 审批待办 / 审批结果三类事件源）----


async def _notify_run_finished(session: AsyncSession, *, run: WorkflowRun, summary: dict[str, Any]) -> None:
    """运行到达终态：站内信通知运行触发者（含结论与计数摘要）。"""
    from iterd.plugins.notify import notify
    from iterd.plugins.projects.models import Iteration

    if run.created_by is None:
        return
    iteration = await session.get(Iteration, run.iteration_id)
    jobs = summary.get("jobs") or {}
    findings = summary.get("findings") or {}
    conclusion = str(summary.get("conclusion", run.status))
    body = (
        f"结论 {conclusion}；作业 {jobs.get('success', 0)} 成功 / {jobs.get('failure', 0)} 失败 /"
        f" {jobs.get('skipped', 0)} 跳过；发现 error {findings.get('error', 0)} 条"
    )
    await notify(
        session,
        user_id=int(run.created_by),
        ntype="run.completed",
        title=f"审查运行 {run.workflow_code} #{run.id} 已完成",
        body=body,
        project_id=int(iteration.project_id) if iteration is not None else None,
        link=f"/iterations/{run.iteration_id}",
        resource_type="workflow_run",
        resource_id=run.id,
    )


async def _notify_approval_pending(session: AsyncSession, *, job: WorkflowJob) -> None:
    """审批作业挂起：站内信通知 approvers 范围内可签署的项目成员（沿项目树继承判定）."""
    from iterd.plugins.accounts.models import User
    from iterd.plugins.notify import notify
    from iterd.plugins.projects.models import Iteration, ProjectMember

    run = await session.get(WorkflowRun, job.run_id)
    iteration = await session.get(Iteration, run.iteration_id) if run is not None else None
    if run is None or iteration is None:
        return
    config = job.config or {}
    min_count = int(config.get("min_count", 1))
    members = (
        (
            await session.execute(
                select(User)
                .join(ProjectMember, ProjectMember.user_id == User.id)
                .where(ProjectMember.project_id == iteration.project_id)
            )
        )
        .scalars()
        .all()
    )
    for user in members:
        if not await _hit_approvers_scope(session, job=job, user=user):
            continue
        await notify(
            session,
            user_id=int(user.id),
            ntype="approval.pending",
            title=f"会签待办：{run.workflow_code} #{run.id} {job.name}",
            body=f"作业「{job.name}」等待会签（需 {min_count} 人通过），请前往审批待办中心签署。",
            project_id=int(iteration.project_id),
            link="/approvals",
            resource_type="workflow_job",
            resource_id=job.id,
        )


async def _notify_approval_recorded(session: AsyncSession, *, run: WorkflowRun, actor: Any, decision: str) -> None:
    """审批签署落定：站内信通知运行触发者（触发者本人签署时不自扰）。"""
    from iterd.plugins.notify import notify
    from iterd.plugins.projects.models import Iteration

    if run.created_by is None or int(run.created_by) == int(actor.id):
        return
    iteration = await session.get(Iteration, run.iteration_id)
    decision_text = "通过" if decision == "approved" else "驳回"
    await notify(
        session,
        user_id=int(run.created_by),
        ntype="approval.recorded",
        title=f"会签进展：{run.workflow_code} #{run.id}（{actor.username} {decision_text}）",
        body=f"{actor.username} 签署意见：{decision_text}。流水线将按会签结果自动推进。",
        project_id=int(iteration.project_id) if iteration is not None else None,
        link=f"/iterations/{run.iteration_id}",
        resource_type="workflow_run",
        resource_id=run.id,
    )
