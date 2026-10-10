"""projects 服务层：项目树 / 迭代状态机 / 成员 / 基线."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError, not_found
from iterd.plugins.notify import audit
from iterd.plugins.projects.models import (
    Baseline,
    BaselineItem,
    Iteration,
    Project,
    ProjectMember,
)
from iterd.plugins.trace import ensure_link, register

# 迭代状态机：单向 planned → active → closed
ITERATION_TRANSITIONS = {("planned", "active"), ("active", "closed")}
ITERATION_STATUSES = ("planned", "active", "closed")


async def get_project(session: AsyncSession, project_id: int) -> Project:
    """按 id 取项目，不存在抛 404."""
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found(f"项目不存在: {project_id}")
    return project


async def list_projects(session: AsyncSession, *, parent_id: int | None = None) -> list[Project]:
    """项目列表；parent_id 给定时按层级过滤。"""
    stmt = select(Project).order_by(Project.id)
    if parent_id is not None:
        stmt = stmt.where(Project.parent_id == parent_id)
    return list((await session.execute(stmt)).scalars())


async def create_project(session: AsyncSession, *, actor_id: int, **fields: object) -> Project:
    """创建项目（code 全局唯一），注册溯源节点并审计."""
    code = str(fields["code"])
    dup = (await session.execute(select(Project.id).where(Project.code == code))).scalar_one_or_none()
    if dup is not None:
        raise IterdError(f"项目编码已存在: {code}", code="ITERD-DUPLICATE_CODE")
    project = Project(**fields)  # type: ignore[arg-type]
    session.add(project)
    await session.flush()
    urn = await register(
        session, node_type="project", ref_table="projects", ref_id=project.id, display_name=project.name
    )
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        after={"code": code, "urn": urn},
    )
    return project


async def update_project(
    session: AsyncSession, *, actor_id: int, project: Project, fields: dict[str, object]
) -> Project:
    """更新项目并审计."""
    before = {"name": project.name, "status": project.status, "description": project.description}
    for key, value in fields.items():
        setattr(project, key, value)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="project.update",
        resource_type="project",
        resource_id=project.id,
        before=before,
        after=dict(fields),
    )
    return project


async def list_members(session: AsyncSession, project_id: int) -> list[ProjectMember]:
    """项目成员列表."""
    return list(
        (
            await session.execute(
                select(ProjectMember).where(ProjectMember.project_id == project_id).order_by(ProjectMember.id)
            )
        ).scalars()
    )


async def upsert_member(
    session: AsyncSession, *, actor_id: int, project_id: int, user_id: int, role: str
) -> ProjectMember:
    """添加或更新项目成员角色."""
    existing = (
        await session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.role = role
        member = existing
    else:
        member = ProjectMember(project_id=project_id, user_id=user_id, role=role)
        session.add(member)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="project.member_set",
        resource_type="project",
        resource_id=project_id,
        after={"user_id": user_id, "role": role},
    )
    return member


async def next_iteration_number(session: AsyncSession, project_id: int) -> int:
    """项目内迭代编号自增."""
    current = (
        await session.execute(select(func.max(Iteration.number)).where(Iteration.project_id == project_id))
    ).scalar_one()
    return (current or 0) + 1


async def get_iteration(session: AsyncSession, iteration_id: int) -> Iteration:
    """按 id 取迭代，不存在抛 404."""
    iteration = await session.get(Iteration, iteration_id)
    if iteration is None:
        raise not_found(f"迭代不存在: {iteration_id}")
    return iteration


async def create_iteration(session: AsyncSession, *, actor_id: int, project_id: int, **fields: object) -> Iteration:
    """创建迭代（number 缺省自动自增），注册溯源节点并审计."""
    number = fields.get("number")
    if number is None:
        fields["number"] = await next_iteration_number(session, project_id)
    iteration = Iteration(project_id=project_id, **fields)  # type: ignore[arg-type]
    session.add(iteration)
    await session.flush()
    urn = await register(
        session, node_type="iteration", ref_table="iterations", ref_id=iteration.id, display_name=iteration.title
    )
    await ensure_link(session, src=(await _project_urn(session, project_id)), dst=urn, link_type="contains")
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="iteration.create",
        resource_type="iteration",
        resource_id=iteration.id,
        after={"number": iteration.number, "urn": urn},
    )
    return iteration


async def _project_urn(session: AsyncSession, project_id: int) -> str:
    from iterd.plugins.trace.models import TraceNode

    row = await session.execute(
        select(TraceNode.urn).where(TraceNode.ref_table == "projects", TraceNode.ref_id == str(project_id))
    )
    urn = row.scalar_one_or_none()
    if urn is None:
        raise not_found(f"项目溯源节点不存在: {project_id}")
    return urn


async def update_iteration(
    session: AsyncSession, *, actor_id: int, iteration: Iteration, fields: dict[str, object]
) -> Iteration:
    """更新迭代；status 变更走状态机校验并审计."""
    new_status = fields.get("status")
    if (
        new_status is not None
        and new_status != iteration.status
        and (iteration.status, str(new_status)) not in ITERATION_TRANSITIONS
    ):
        raise IterdError(
            f"迭代状态不允许从 {iteration.status} 变更为 {new_status}",
            code="ITERD-INVALID_STATE",
        )
    before = {"status": iteration.status, "title": iteration.title}
    for key, value in fields.items():
        setattr(iteration, key, value)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="iteration.update",
        resource_type="iteration",
        resource_id=iteration.id,
        before=before,
        after={k: str(v) for k, v in fields.items()},
    )
    return iteration


async def list_iterations(session: AsyncSession, project_id: int) -> list[Iteration]:
    """项目下迭代列表（按编号排序）。"""
    return list(
        (
            await session.execute(
                select(Iteration).where(Iteration.project_id == project_id).order_by(Iteration.number)
            )
        ).scalars()
    )


async def create_baseline(session: AsyncSession, *, actor_id: int, iteration_id: int, name: str) -> Baseline:
    """建立基线：锁定迭代内全部产物的当前版本快照，建立后不受新上传影响."""
    from iterd.plugins.artifacts.models import Artifact

    iteration = await get_iteration(session, iteration_id)
    if iteration.status == "planned":
        raise IterdError("规划中的迭代不允许建立基线", code="ITERD-INVALID_STATE")
    baseline = Baseline(iteration_id=iteration_id, name=name, created_by=actor_id)
    session.add(baseline)
    await session.flush()
    artifacts = list(
        (
            await session.execute(select(Artifact).where(Artifact.iteration_id == iteration_id).order_by(Artifact.id))
        ).scalars()
    )
    for artifact in artifacts:
        if artifact.current_version_id is None:
            continue
        session.add(
            BaselineItem(
                baseline_id=baseline.id, artifact_id=artifact.id, artifact_version_id=artifact.current_version_id
            )
        )
    urn = await register(
        session, node_type="baseline", ref_table="baselines", ref_id=baseline.id, display_name=baseline.name
    )
    iteration_urn = await _iteration_urn(session, iteration_id)
    await ensure_link(session, src=iteration_urn, dst=urn, link_type="contains")
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="baseline.create",
        resource_type="baseline",
        resource_id=baseline.id,
        after={"name": name, "iteration_id": iteration_id, "urn": urn},
    )
    return baseline


async def _iteration_urn(session: AsyncSession, iteration_id: int) -> str:
    from iterd.plugins.trace.models import TraceNode

    row = await session.execute(
        select(TraceNode.urn).where(TraceNode.ref_table == "iterations", TraceNode.ref_id == str(iteration_id))
    )
    urn = row.scalar_one_or_none()
    if urn is None:
        raise not_found(f"迭代溯源节点不存在: {iteration_id}")
    return urn


async def list_baselines(session: AsyncSession, iteration_id: int) -> list[Baseline]:
    """迭代下基线列表."""
    return list(
        (
            await session.execute(select(Baseline).where(Baseline.iteration_id == iteration_id).order_by(Baseline.id))
        ).scalars()
    )


async def get_baseline_items(session: AsyncSession, baseline_id: int) -> list[BaselineItem]:
    """基线快照条目."""
    return list((await session.execute(select(BaselineItem).where(BaselineItem.baseline_id == baseline_id))).scalars())
