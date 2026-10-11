"""workflows 路由：审查模板 / 审查运行 / 编排详情."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import permission_denied
from iterd.plugins.projects import rbac
from iterd.plugins.projects import services as project_services
from iterd.plugins.workflows import schemas, services
from iterd.plugins.workflows.definition import WorkflowDefinitionError, parse_definition
from iterd.plugins.workflows.models import IterationSubmission

router = APIRouter(prefix="/api/v1", tags=["workflows"])


def _job_defs_out(definition_text: str) -> list[schemas.WorkflowJobDefOut]:
    """模板定义文本 → 解析后作业结构（发起/展示前已校验，此处仅转换）."""
    definition = parse_definition(definition_text)
    return [
        schemas.WorkflowJobDefOut(key=job.key, name=job.name, uses=job.uses, needs=job.needs, with_=job.with_)
        for job in definition.jobs
    ]


async def _fill_run_out(session: SessionDep, run: schemas.WorkflowRunOut, run_id: int) -> schemas.WorkflowRunOut:
    """填充任务 id、作业概要（含绑定展示字段）与步骤、提交标题。"""
    run.task_id = await services.get_run_task_id(session, run_id)
    jobs = await services.list_jobs(session, run_id=run_id)
    displays = await services.job_display_map(session, jobs)
    steps_map = await services.job_steps(session, job_ids=[int(job.id) for job in jobs])
    if run.submission_id is not None:
        submission = await session.get(IterationSubmission, run.submission_id)
        run.submission_title = submission.title if submission is not None else ""
    outs = [schemas.WorkflowJobOut.model_validate(j) for j in jobs]
    for out in outs:
        display = displays.get(out.id, {})
        for key, value in display.items():
            setattr(out, key, value)
        out.steps = [schemas.WorkflowJobStepOut.model_validate(step) for step in steps_map.get(out.id, [])]
    run.jobs = outs
    return run


async def _fill_submission_out(
    session: SessionDep, submission: schemas.SubmissionOut, *, submission_id: int
) -> schemas.SubmissionOut:
    """填充提交方案触发产生的运行概要。"""
    runs = [
        run
        for run in await services.list_runs(session, iteration_id=submission.iteration_id)
        if run.submission_id == submission_id
    ]
    submission.runs = [
        await _fill_run_out(session, schemas.WorkflowRunOut.model_validate(run), int(run.id)) for run in runs
    ]
    return submission


# ---- 审查模板 ----


@router.get("/workflows", response_model=list[schemas.WorkflowOut])
async def list_workflows(
    _user: CurrentUser, session: SessionDep, project_id: int | None = None
) -> list[schemas.WorkflowOut]:
    """模板列表（可按项目过滤，含全局）。"""
    templates = await services.list_templates(session, project_id=project_id)
    outs = []
    for template in templates:
        out = schemas.WorkflowOut.model_validate(template)
        try:
            out.jobs = _job_defs_out(template.definition)
        except WorkflowDefinitionError:
            out.jobs = []
        outs.append(out)
    return outs


@router.post("/workflows", response_model=schemas.WorkflowOut, status_code=201)
async def create_workflow(body: schemas.WorkflowIn, user: CurrentUser, session: SessionDep) -> schemas.WorkflowOut:
    """创建审查模板（YAML 校验；指定项目需该项目 designer+，全局需超管）。"""
    if body.project_id is not None:
        await rbac.require_project_role(session, body.project_id, user.id, "designer", is_superuser=user.is_superuser)
    elif not user.is_superuser:
        raise permission_denied("全局审查模板仅超级管理员可创建")
    template = await services.create_template(session, actor_id=user.id, **body.model_dump())
    await session.commit()
    out = schemas.WorkflowOut.model_validate(template)
    out.jobs = _job_defs_out(template.definition)
    return out


async def _authorize_template_edit(session: SessionDep, template: Any, user: CurrentUser) -> None:
    """模板编辑权限：项目级 designer+，全局超管。"""
    if template.project_id is None:
        if not user.is_superuser:
            raise permission_denied("全局审查模板仅超级管理员可维护")
    else:
        await rbac.require_project_role(
            session, template.project_id, user.id, "designer", is_superuser=user.is_superuser
        )


@router.get("/workflows/{workflow_id}", response_model=schemas.WorkflowOut)
async def get_workflow(workflow_id: int, user: CurrentUser, session: SessionDep) -> schemas.WorkflowOut:
    """模板详情（含解析后 jobs 结构；项目级 viewer+）。"""
    template = await services.get_template(session, workflow_id)
    if template.project_id is not None:
        await rbac.require_project_role(
            session,
            template.project_id,
            user.id,
            "viewer",
            is_superuser=user.is_superuser,
            include_ancestor=True,
        )
    out = schemas.WorkflowOut.model_validate(template)
    out.jobs = _job_defs_out(template.definition)
    return out


@router.patch("/workflows/{workflow_id}", response_model=schemas.WorkflowOut)
async def update_workflow(
    workflow_id: int, body: schemas.WorkflowUpdateIn, user: CurrentUser, session: SessionDep
) -> schemas.WorkflowOut:
    """更新审查模板（definition 变更时重新校验 YAML）。"""
    template = await services.get_template(session, workflow_id)
    await _authorize_template_edit(session, template, user)
    fields = body.model_dump(exclude_unset=True)
    if "definition" in fields:
        # 定义变更时同步刷新名称与描述（与 YAML 头保持一致）
        try:
            definition = parse_definition(str(fields["definition"]))
        except WorkflowDefinitionError as exc:
            from iterd.core.errors import IterdError

            raise IterdError(str(exc), code="ITERD-INVALID_DEFINITION", status_code=422) from exc
        fields.setdefault("name", definition.name)
        fields.setdefault("description", definition.description)
    updated = await services.update_template(session, actor_id=user.id, template=template, fields=fields)
    await session.commit()
    out = schemas.WorkflowOut.model_validate(updated)
    out.jobs = _job_defs_out(updated.definition)
    return out


# ---- 审查运行 ----


@router.post("/iterations/{iteration_id}/workflow-runs", response_model=schemas.WorkflowRunOut, status_code=202)
async def create_workflow_run(
    iteration_id: int, body: schemas.WorkflowRunIn, user: CurrentUser, session: SessionDep
) -> schemas.WorkflowRunOut:
    """发起审查运行（designer+）：快照固化 + 引用解析 + Task 创建，worker 执行。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    run, _task = await services.create_workflow_run(
        session, actor_id=user.id, iteration_id=iteration_id, template_id=body.workflow_id
    )
    await session.commit()
    return await _fill_run_out(session, schemas.WorkflowRunOut.model_validate(run), int(run.id))


@router.get("/iterations/{iteration_id}/workflow-runs", response_model=list[schemas.WorkflowRunOut])
async def list_workflow_runs(iteration_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.WorkflowRunOut]:
    """迭代下运行列表（viewer+，含作业概要与任务 id）。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    outs = []
    for run in await services.list_runs(session, iteration_id=iteration_id):
        outs.append(await _fill_run_out(session, schemas.WorkflowRunOut.model_validate(run), int(run.id)))
    return outs


@router.get("/workflow-runs/{run_id}", response_model=schemas.WorkflowRunOut)
async def get_workflow_run(run_id: int, user: CurrentUser, session: SessionDep) -> schemas.WorkflowRunOut:
    """运行详情（含全部作业、日志与绑定信息；viewer+）。"""
    run = await services.get_run(session, run_id)
    iteration = await project_services.get_iteration(session, run.iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return await _fill_run_out(session, schemas.WorkflowRunOut.model_validate(run), run_id)


@router.post("/workflow-runs/{run_id}/rerun", response_model=schemas.WorkflowRunOut, status_code=202)
async def rerun_workflow_run(run_id: int, user: CurrentUser, session: SessionDep) -> schemas.WorkflowRunOut:
    """以运行快照重新执行（designer+，生成新 run）。"""
    run = await services.get_run(session, run_id)
    iteration = await project_services.get_iteration(session, run.iteration_id)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    new_run, _task = await services.rerun_workflow_run(session, actor_id=user.id, run=run)
    await session.commit()
    return await _fill_run_out(session, schemas.WorkflowRunOut.model_validate(new_run), int(new_run.id))


# ---- 提交方案 ----


@router.post("/iterations/{iteration_id}/submissions", response_model=schemas.SubmissionOut, status_code=202)
async def create_submission(
    iteration_id: int, body: schemas.SubmissionIn, user: CurrentUser, session: SessionDep
) -> schemas.SubmissionOut:
    """提交迭代方案（designer+）：为每个启用模板各产生一条运行，worker 执行。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    submission, _runs = await services.create_submission(
        session, actor_id=user.id, iteration_id=iteration_id, title=body.title, note=body.note
    )
    await session.commit()
    return await _fill_submission_out(
        session, schemas.SubmissionOut.model_validate(submission), submission_id=int(submission.id)
    )


@router.get("/iterations/{iteration_id}/submissions", response_model=list[schemas.SubmissionOut])
async def list_submissions(iteration_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.SubmissionOut]:
    """迭代下提交方案列表（viewer+，含各自触发的运行）。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    outs = []
    for submission in await services.list_submissions(session, iteration_id=iteration_id):
        outs.append(
            await _fill_submission_out(
                session, schemas.SubmissionOut.model_validate(submission), submission_id=int(submission.id)
            )
        )
    return outs


@router.get("/submissions/{submission_id}", response_model=schemas.SubmissionOut)
async def get_submission(submission_id: int, user: CurrentUser, session: SessionDep) -> schemas.SubmissionOut:
    """提交方案详情（viewer+，含触发的运行）。"""
    submission = await services.get_submission(session, submission_id)
    iteration = await project_services.get_iteration(session, submission.iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return await _fill_submission_out(
        session, schemas.SubmissionOut.model_validate(submission), submission_id=submission_id
    )
