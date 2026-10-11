"""simulation 服务层：模板 / 作业 / 求解执行与阈值评估."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError, not_found
from iterd.plugins.notify import audit
from iterd.plugins.simulation.models import SimJob, SimResult, SimTemplate
from iterd.solvers import Metric, SimInput, default_inputs, get_solver


async def get_template(session: AsyncSession, template_id: int) -> SimTemplate:
    """取仿真模板，不存在抛 404."""
    template = await session.get(SimTemplate, template_id)
    if template is None:
        raise not_found(f"仿真模板不存在: {template_id}")
    return template


async def list_templates(session: AsyncSession, *, project_id: int | None = None) -> list[SimTemplate]:
    """模板列表：给定项目时含全局（project_id IS NULL）。"""
    stmt = select(SimTemplate).order_by(SimTemplate.id)
    if project_id is not None:
        stmt = stmt.where((SimTemplate.project_id == project_id) | (SimTemplate.project_id.is_(None)))
    return list((await session.execute(stmt)).scalars())


async def create_template(session: AsyncSession, *, actor_id: int, **fields: object) -> SimTemplate:
    """创建仿真模板（code 唯一），注册溯源节点."""
    dup = (
        await session.execute(select(SimTemplate.id).where(SimTemplate.code == str(fields["code"])))
    ).scalar_one_or_none()
    if dup is not None:
        raise IterdError(f"仿真模板编码已存在: {fields['code']}", code="ITERD-DUPLICATE_CODE")
    get_solver(str(fields["solver_type"]))  # 求解器未注册时提前 422
    template = SimTemplate(**fields)  # type: ignore[arg-type]
    session.add(template)
    await session.flush()
    from iterd.plugins.trace import register

    await register(
        session,
        node_type="sim_template",
        ref_table="sim_templates",
        ref_id=template.id,
        display_name=f"{template.code} {template.name}",
    )
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="sim_template.create",
        resource_type="sim_template",
        resource_id=template.id,
        after={"code": template.code, "solver_type": template.solver_type},
    )
    return template


# ---- 仿真作业 ----


async def create_sim_job(  # noqa: PLR0913 - 作业字段
    session: AsyncSession,
    *,
    actor_id: int,
    iteration_id: int,
    template_id: int,
    artifact_version_id: int | None = None,
    inputs: dict[str, Any] | None = None,
) -> tuple[SimJob, Any]:
    """创建仿真作业 + 任务记录（同事务，status=pending）。"""
    from iterd.plugins.artifacts.models import ArtifactVersion
    from iterd.plugins.projects.models import Iteration
    from iterd.tasks.models import Task

    if await session.get(Iteration, iteration_id) is None:
        raise not_found(f"迭代不存在: {iteration_id}")
    template = await get_template(session, template_id)
    if not template.enabled:
        raise IterdError(f"仿真模板已停用: {template.code}", code="ITERD-INVALID_STATE")
    if artifact_version_id is not None and await session.get(ArtifactVersion, artifact_version_id) is None:
        raise not_found(f"产物版本不存在: {artifact_version_id}")

    job = SimJob(
        iteration_id=iteration_id,
        template_id=template_id,
        artifact_version_id=artifact_version_id,
        status="pending",
        inputs=inputs,
        created_by=actor_id,
    )
    session.add(job)
    await session.flush()
    task = Task(task_type="sim_job", payload={"sim_job_id": job.id}, status="pending")
    session.add(task)
    await session.flush()
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="sim_job.create",
        resource_type="sim_job",
        resource_id=job.id,
        after={"iteration_id": iteration_id, "template_id": template_id},
    )
    return job, task


async def get_sim_job(session: AsyncSession, job_id: int) -> SimJob:
    """取作业，不存在抛 404."""
    job = await session.get(SimJob, job_id)
    if job is None:
        raise not_found(f"仿真作业不存在: {job_id}")
    return job


async def list_sim_jobs(session: AsyncSession, *, iteration_id: int) -> list[SimJob]:
    """迭代下仿真作业列表（按 id 升序）。"""
    return list(
        (await session.execute(select(SimJob).where(SimJob.iteration_id == iteration_id).order_by(SimJob.id))).scalars()
    )


async def get_result(session: AsyncSession, job_id: int) -> SimResult | None:
    """取作业结果（未产出时返回 None）。"""
    return (await session.execute(select(SimResult).where(SimResult.sim_job_id == job_id))).scalar_one_or_none()


async def get_job_task_id(session: AsyncSession, job_id: int) -> int | None:
    """取作业对应的任务 id（前端 WS 订阅进度用）。"""
    from iterd.tasks.models import Task

    row = (
        await session.execute(
            select(Task.id).where(
                Task.task_type == "sim_job",
                Task.payload["sim_job_id"].as_integer() == job_id,
            )
        )
    ).scalar_one_or_none()
    return int(row) if row is not None else None


async def job_display_map(session: AsyncSession, job_ids: list[int]) -> dict[int, dict[str, Any]]:
    """批量取作业展示信息：模板名/求解器/被验证产物编码与版本号。"""
    if not job_ids:
        return {}
    from iterd.plugins.artifacts.models import Artifact, ArtifactVersion

    rows = (
        await session.execute(
            select(SimJob.id, SimTemplate.name, SimTemplate.solver_type, Artifact.code, ArtifactVersion.version_no)
            .join(SimTemplate, SimTemplate.id == SimJob.template_id)
            .outerjoin(ArtifactVersion, ArtifactVersion.id == SimJob.artifact_version_id)
            .outerjoin(Artifact, Artifact.id == ArtifactVersion.artifact_id)
            .where(SimJob.id.in_(job_ids))
        )
    ).all()
    return {
        int(row[0]): {
            "template_name": row[1],
            "solver_type": row[2],
            "artifact_code": row[3] or "",
            "version_no": row[4],
        }
        for row in rows
    }


# ---- 阈值评估 ----


def evaluate(metrics: list[Metric], thresholds: dict[str, Any]) -> tuple[str, int, list[dict[str, Any]]]:
    """按模板阈值逐项评估：返回 (verdict, failures, detail)。

    阈值形如 `{"max_stress": {"max": 200}, "safety_factor": {"min": 1.5}}`，仅支持 min/max。
    """
    detail: list[dict[str, Any]] = []
    failures = 0
    for metric in metrics:
        rule = thresholds.get(metric.key) or {}
        minimum = _to_float(rule.get("min"))
        maximum = _to_float(rule.get("max"))
        passed = True
        if minimum is not None and metric.value < minimum:
            passed = False
        if maximum is not None and metric.value > maximum:
            passed = False
        if not passed:
            failures += 1
        detail.append(
            {
                "key": metric.key,
                "label": metric.label or metric.key,
                "value": metric.value,
                "unit": metric.unit,
                "min": minimum,
                "max": maximum,
                "passed": passed,
            }
        )
    return ("pass" if failures == 0 else "fail"), failures, detail


def _to_float(value: Any) -> float | None:
    """阈值数值化（非法值视为未设置）。"""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# ---- 求解执行（worker 侧）----


async def _artifact_context(session: AsyncSession, version_id: int | None) -> tuple[str, str, int]:
    """取被验证产物的编码/名称/版本号（未绑定版本时返回空）。"""
    if version_id is None:
        return "", "", 0
    from iterd.plugins.artifacts.models import Artifact, ArtifactVersion

    version = await session.get(ArtifactVersion, version_id)
    if version is None:
        return "", "", 0
    artifact = await session.get(Artifact, version.artifact_id)
    if artifact is None:
        return "", "", version.version_no
    return artifact.code, artifact.name, version.version_no


async def execute_sim_job(
    session: AsyncSession, *, job_id: int, progress: Any = None, log: Any = None
) -> dict[str, Any]:
    """执行仿真：合并参数 → 求解 → 阈值评估 → 写结果（幂等覆盖）→ 溯源.

    求解异常时作业显式置 failed 并抛出异常（由执行器转为任务失败，不重试）。
    """
    job = await session.get(SimJob, job_id)
    if job is None:
        raise not_found(f"仿真作业不存在: {job_id}")
    job.status = "running"
    job.started_at = datetime.now(UTC)
    job.error = None
    await session.commit()

    try:
        if progress is not None:
            progress("加载模板与参数", 10)
        template = await get_template(session, job.template_id)
        solver = get_solver(template.solver_type)
        artifact_code, artifact_name, version_no = await _artifact_context(session, job.artifact_version_id)
        inputs = {**default_inputs(template.solver_type), **(template.params or {}), **(job.inputs or {})}
        if log is not None:
            log("info", f"求解器 {template.solver_type} 输入 {inputs}")

        if progress is not None:
            progress("求解计算", 50)
        metrics = solver.run(
            SimInput(
                job_id=job.id,
                artifact_code=artifact_code,
                artifact_name=artifact_name,
                version_no=version_no,
                inputs=inputs,
            )
        )
        if progress is not None:
            progress("阈值评估", 80)
        verdict, failures, detail = evaluate(metrics, dict(template.thresholds or {}))

        await session.execute(delete(SimResult).where(SimResult.sim_job_id == job.id))
        result = SimResult(
            sim_job_id=job.id,
            metrics={m.key: m.value for m in metrics},
            verdict=verdict,
            failures=failures,
            detail=detail,
        )
        session.add(result)
        await session.flush()

        summary = {"metrics": len(metrics), "failures": failures, "verdict": verdict}
        job.summary = summary
        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        await _trace_result(session, job=job, result=result, version_id=job.artifact_version_id)
        await session.commit()
        if progress is not None:
            progress("完成", 100)
        return summary
    except Exception as exc:
        await session.rollback()
        failed = await session.get(SimJob, job_id)
        if failed is not None:
            failed.status = "failed"
            failed.error = f"{type(exc).__name__}: {exc}"[:1000]
            failed.summary = {"verdict": "fail"}
            failed.finished_at = datetime.now(UTC)
            await session.commit()
        raise


async def _trace_result(session: AsyncSession, *, job: SimJob, result: SimResult, version_id: int | None) -> None:
    """溯源：sim_job 节点（绑定版本时 simulated_by）→ sim_result 节点（produced）。"""
    from iterd.plugins.trace import ensure_link, register
    from iterd.plugins.trace.models import TraceNode

    job_urn = await register(
        session,
        node_type="sim_job",
        ref_table="sim_jobs",
        ref_id=job.id,
        display_name=f"仿真作业 #{job.id}",
    )
    result_urn = await register(
        session,
        node_type="sim_result",
        ref_table="sim_results",
        ref_id=result.id,
        display_name=f"仿真结果 {result.verdict}",
    )
    await ensure_link(session, src=job_urn, dst=result_urn, link_type="produced")
    if version_id is not None:
        version_urn = (
            await session.execute(
                select(TraceNode.urn).where(
                    TraceNode.ref_table == "artifact_versions", TraceNode.ref_id == str(version_id)
                )
            )
        ).scalar_one_or_none()
        if version_urn:
            await ensure_link(session, src=version_urn, dst=job_urn, link_type="simulated_by")


async def _sim_job_executor(session: AsyncSession, payload: dict[str, Any], ctx: Any) -> Any:
    """sim_job 任务执行器：包装 execute_sim_job 供 worker 调度."""
    from iterd.tasks.executor import TaskResult

    try:
        summary = await execute_sim_job(session, job_id=payload["sim_job_id"], progress=ctx.progress, log=ctx.log)
    except Exception as exc:  # 作业内部已置 failed，此处仅回传错误（不触发重试）
        return TaskResult(success=False, error=f"{type(exc).__name__}: {exc}"[:1000])
    return TaskResult(success=True, summary=summary)


def register_executors() -> None:
    """向任务框架注册本插件的执行器（app 启动时调用）。"""
    from iterd.tasks.executor import register_executor

    register_executor("sim_job", _sim_job_executor)
