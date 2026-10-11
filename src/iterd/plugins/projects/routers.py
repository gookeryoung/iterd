"""projects 路由：项目树 / 成员 / 迭代."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from iterd.api.deps import CurrentUser, SessionDep
from iterd.plugins.projects import rbac, schemas, services

router = APIRouter(prefix="/api/v1", tags=["projects"])


class IdOut(BaseModel):
    """简单 id 响应."""

    id: int


# ---- 项目 ----


@router.get("/projects", response_model=list[schemas.ProjectOut])
async def list_projects(
    user: CurrentUser, session: SessionDep, parent_id: int | None = None
) -> list[schemas.ProjectOut]:
    """项目列表（parent_id 过滤层级；列表仅含用户可见项目，超管全量）。"""
    projects = await services.list_projects(session, parent_id=parent_id)
    if not user.is_superuser:
        projects = [p for p in projects if await rbac.get_project_role(session, p.id, user.id) is not None]
    return [schemas.ProjectOut.model_validate(p) for p in projects]


@router.post("/projects", response_model=schemas.ProjectOut, status_code=201)
async def create_project(body: schemas.ProjectIn, user: CurrentUser, session: SessionDep) -> schemas.ProjectOut:
    """创建项目；子项目需父项目 admin+ 权限。"""
    if body.parent_id is not None:
        await rbac.require_project_role(session, body.parent_id, user.id, "admin", is_superuser=user.is_superuser)
    project = await services.create_project(session, actor_id=user.id, **body.model_dump())
    # 创建者自动成为 owner
    await services.upsert_member(session, actor_id=user.id, project_id=project.id, user_id=user.id, role="owner")
    await session.commit()
    return schemas.ProjectOut.model_validate(project)


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
async def get_project(project_id: int, user: CurrentUser, session: SessionDep) -> schemas.ProjectOut:
    """项目详情（成员可见）。"""
    await rbac.require_project_role(
        session, project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return schemas.ProjectOut.model_validate(await services.get_project(session, project_id))


@router.patch("/projects/{project_id}", response_model=schemas.ProjectOut)
async def update_project(
    project_id: int, body: schemas.ProjectIn, user: CurrentUser, session: SessionDep
) -> schemas.ProjectOut:
    """更新项目（admin+）。"""
    await rbac.require_project_role(session, project_id, user.id, "admin", is_superuser=user.is_superuser)
    project = await services.get_project(session, project_id)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("parent_id", None)
    updated = await services.update_project(session, actor_id=user.id, project=project, fields=fields)
    await session.commit()
    return schemas.ProjectOut.model_validate(updated)


# ---- 成员 ----


@router.get("/projects/{project_id}/members", response_model=list[schemas.MemberOut])
async def list_members(project_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.MemberOut]:
    """项目成员列表（viewer+），联表带出用户名。"""
    await rbac.require_project_role(
        session, project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    members = await services.list_members(session, project_id)
    name_map = await services.get_user_names(session, [m.user_id for m in members])
    outs = [schemas.MemberOut.model_validate(m) for m in members]
    for out in outs:
        out.username = name_map.get(out.user_id, "")
    return outs


@router.get("/projects/{project_id}/me", response_model=schemas.MyRoleOut)
async def my_role(project_id: int, user: CurrentUser, session: SessionDep) -> schemas.MyRoleOut:
    """当前用户在项目内的角色与能力位（含超管与父项目继承）。"""
    role = await rbac.get_project_role(
        session, project_id, user.id, is_superuser=user.is_superuser, include_ancestor=True
    )
    role_name = role.name if role is not None else None
    return schemas.MyRoleOut(
        project_id=project_id,
        user_id=user.id,
        role=role_name,
        is_superuser=user.is_superuser,
        can_manage=role is not None and role >= rbac.Role.admin,
        can_design=role is not None and role >= rbac.Role.designer,
        can_review=role is not None and role >= rbac.Role.reviewer,
    )


@router.put("/projects/{project_id}/members", response_model=schemas.MemberOut, status_code=201)
async def upsert_member(
    project_id: int, body: schemas.MemberIn, user: CurrentUser, session: SessionDep
) -> schemas.MemberOut:
    """添加/更新成员（admin+；仅 owner 可授予 owner）。"""
    actor_role = await rbac.require_project_role(session, project_id, user.id, "admin", is_superuser=user.is_superuser)
    if body.role == "owner" and actor_role < rbac.Role.owner:
        from iterd.core.errors import permission_denied

        raise permission_denied("仅 owner 可授予 owner 角色")
    member = await services.upsert_member(
        session, actor_id=user.id, project_id=project_id, user_id=body.user_id, role=body.role
    )
    await session.commit()
    return schemas.MemberOut.model_validate(member)


# ---- 迭代 ----


@router.get("/projects/{project_id}/iterations", response_model=list[schemas.IterationOut])
async def list_iterations(project_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.IterationOut]:
    """项目下迭代列表（viewer+）。"""
    await rbac.require_project_role(
        session, project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    iterations = await services.list_iterations(session, project_id)
    return [schemas.IterationOut.model_validate(i) for i in iterations]


@router.post("/projects/{project_id}/iterations", response_model=schemas.IterationOut, status_code=201)
async def create_iteration(
    project_id: int, body: schemas.IterationIn, user: CurrentUser, session: SessionDep
) -> schemas.IterationOut:
    """创建迭代（designer+，number 缺省自动自增）。"""
    await rbac.require_project_role(session, project_id, user.id, "designer", is_superuser=user.is_superuser)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("status", None)  # 新建一律 planned
    iteration = await services.create_iteration(session, actor_id=user.id, project_id=project_id, **fields)
    await session.commit()
    return schemas.IterationOut.model_validate(iteration)


@router.get("/iterations/{iteration_id}", response_model=schemas.IterationOut)
async def get_iteration(iteration_id: int, user: CurrentUser, session: SessionDep) -> schemas.IterationOut:
    """迭代详情（viewer+）。"""
    iteration = await services.get_iteration(session, iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return schemas.IterationOut.model_validate(iteration)


@router.patch("/iterations/{iteration_id}", response_model=schemas.IterationOut)
async def update_iteration(
    iteration_id: int, body: schemas.IterationPatch, user: CurrentUser, session: SessionDep
) -> schemas.IterationOut:
    """更新迭代（designer+；支持仅传 status 的部分更新，状态迁移走状态机）。"""
    iteration = await services.get_iteration(session, iteration_id)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    fields = body.model_dump(exclude_unset=True)
    # 非空约束字段显式传 null 视为未变更；时间窗字段允许传 null 清空
    for key in ("number", "title", "objective", "status"):
        if fields.get(key) is None:
            fields.pop(key, None)
    updated = await services.update_iteration(session, actor_id=user.id, iteration=iteration, fields=fields)
    await session.commit()
    return schemas.IterationOut.model_validate(updated)
