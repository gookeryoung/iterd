"""simulation 路由：求解器清单 / 仿真模板 / 作业发起与查询 / 结果评估."""

from __future__ import annotations

from fastapi import APIRouter

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import not_found, permission_denied
from iterd.plugins.accounts.models import User
from iterd.plugins.projects import rbac
from iterd.plugins.projects import services as project_services
from iterd.plugins.projects.models import Iteration
from iterd.plugins.simulation import schemas, services
from iterd.plugins.simulation.models import SimJob

router = APIRouter(prefix="/api/v1", tags=["simulation"])


@router.get("/solvers", response_model=list[dict[str, object]])
async def list_solvers(_user: CurrentUser) -> list[dict[str, object]]:
    """已注册求解器清单（含输入参数与输出指标规格，供前端动态表单）。"""
    from iterd.solvers import solver_manifest

    return solver_manifest()  # type: ignore[return-value]


# ---- 仿真模板 ----


@router.get("/sim-templates", response_model=list[schemas.SimTemplateOut])
async def list_templates(
    _user: CurrentUser, session: SessionDep, project_id: int | None = None
) -> list[schemas.SimTemplateOut]:
    """仿真模板列表（可按项目过滤，含全局）。"""
    return [
        schemas.SimTemplateOut.model_validate(t) for t in await services.list_templates(session, project_id=project_id)
    ]


@router.post("/sim-templates", response_model=schemas.SimTemplateOut, status_code=201)
async def create_template(
    body: schemas.SimTemplateIn, user: CurrentUser, session: SessionDep
) -> schemas.SimTemplateOut:
    """创建仿真模板（指定项目时需该项目 designer+；全局模板需超管）。"""
    if body.project_id is None:
        if not user.is_superuser:
            raise permission_denied("全局仿真模板仅超级管理员可创建")
    else:
        await rbac.require_project_role(session, body.project_id, user.id, "designer", is_superuser=user.is_superuser)
    template = await services.create_template(session, actor_id=user.id, **body.model_dump())
    await session.commit()
    return schemas.SimTemplateOut.model_validate(template)


@router.get("/sim-templates/{template_id}", response_model=schemas.SimTemplateOut)
async def get_template(template_id: int, user: CurrentUser, session: SessionDep) -> schemas.SimTemplateOut:
    """仿真模板详情（项目模板需 viewer+）。"""
    template = await services.get_template(session, template_id)
    if template.project_id is not None:
        await rbac.require_project_role(
            session,
            template.project_id,
            user.id,
            "viewer",
            is_superuser=user.is_superuser,
            include_ancestor=True,
        )
    return schemas.SimTemplateOut.model_validate(template)


@router.patch("/sim-templates/{template_id}", response_model=schemas.SimTemplateOut)
async def update_template(
    template_id: int, body: schemas.SimTemplateUpdateIn, user: CurrentUser, session: SessionDep
) -> schemas.SimTemplateOut:
    """更新仿真模板（部分更新；项目级 designer+，全局超管）。"""
    template = await services.get_template(session, template_id)
    if template.project_id is None:
        if not user.is_superuser:
            raise permission_denied("全局仿真模板仅超级管理员可维护")
    else:
        await rbac.require_project_role(
            session, template.project_id, user.id, "designer", is_superuser=user.is_superuser
        )
    updated = await services.update_template(
        session, actor_id=user.id, template=template, fields=body.model_dump(exclude_unset=True)
    )
    await session.commit()
    return schemas.SimTemplateOut.model_validate(updated)


# ---- 仿真作业 ----


async def _authorize_iteration(session: SessionDep, user: User, iteration_id: int, required: str) -> Iteration:
    """按迭代所属项目校验角色（返回迭代）。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(
        session,
        iteration.project_id,
        user.id,
        required,
        is_superuser=user.is_superuser,
        include_ancestor=True,
    )
    return iteration


async def _job_out(session: SessionDep, job: SimJob) -> schemas.SimJobOut:
    """组装作业输出：带任务 id 与模板/产物展示信息。"""
    out = schemas.SimJobOut.model_validate(job)
    out.task_id = await services.get_job_task_id(session, job.id)
    display = (await services.job_display_map(session, [job.id])).get(job.id)
    if display is not None:
        out.template_name = display["template_name"]
        out.solver_type = display["solver_type"]
        out.artifact_code = display["artifact_code"]
        out.version_no = display["version_no"]
    return out


@router.get("/iterations/{iteration_id}/sim-jobs", response_model=list[schemas.SimJobOut])
async def list_sim_jobs(iteration_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.SimJobOut]:
    """迭代下仿真作业列表（viewer+，含任务 id）。"""
    await _authorize_iteration(session, user, iteration_id, "viewer")
    jobs = await services.list_sim_jobs(session, iteration_id=iteration_id)
    displays = await services.job_display_map(session, [job.id for job in jobs])
    outs: list[schemas.SimJobOut] = []
    for job in jobs:
        out = schemas.SimJobOut.model_validate(job)
        out.task_id = await services.get_job_task_id(session, job.id)
        display = displays.get(job.id)
        if display is not None:
            out.template_name = display["template_name"]
            out.solver_type = display["solver_type"]
            out.artifact_code = display["artifact_code"]
            out.version_no = display["version_no"]
        outs.append(out)
    return outs


@router.get("/sim-jobs/{job_id}", response_model=schemas.SimJobOut)
async def get_sim_job(job_id: int, user: CurrentUser, session: SessionDep) -> schemas.SimJobOut:
    """仿真作业详情（viewer+，含任务 id）。"""
    job = await services.get_sim_job(session, job_id)
    await _authorize_iteration(session, user, job.iteration_id, "viewer")
    return await _job_out(session, job)


@router.get("/sim-jobs/{job_id}/result", response_model=schemas.SimResultOut)
async def get_sim_result(job_id: int, user: CurrentUser, session: SessionDep) -> schemas.SimResultOut:
    """仿真结果（viewer+）：指标值与逐项阈值判定，未产出时 404。"""
    job = await services.get_sim_job(session, job_id)
    await _authorize_iteration(session, user, job.iteration_id, "viewer")
    result = await services.get_result(session, job_id)
    if result is None:
        raise not_found(f"仿真结果不存在: {job_id}")
    return schemas.SimResultOut.model_validate(result)
