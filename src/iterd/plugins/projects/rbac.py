"""项目级 RBAC：五角色线性权限模型（复用 cndb 校验模式）。"""

from __future__ import annotations

from enum import IntEnum
from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import not_found, permission_denied
from iterd.plugins.projects.models import Project, ProjectMember


class Role(IntEnum):
    """项目角色（数值越大权限越高）。"""

    viewer = 1
    designer = 2
    reviewer = 3
    admin = 4
    owner = 5

    @classmethod
    @override
    def _missing_(cls, value: object) -> Role | None:
        """允许按名称构造（Role("designer")）。"""
        if isinstance(value, str) and value in cls.__members__:
            return cls[value]
        return None


def role_at_least(actual: str | Role, required: str | Role) -> bool:
    """角色权限比较."""
    return Role(actual) >= Role(required)


async def get_project_role(
    session: AsyncSession, project_id: int, user_id: int, is_superuser: bool = False
) -> Role | None:
    """查询用户在项目内的角色；超级管理员视为 owner。"""
    if is_superuser:
        return Role.owner
    row = await session.execute(
        select(ProjectMember.role).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    role = row.scalar_one_or_none()
    return Role(role) if role is not None else None


async def require_project_role(  # noqa: PLR0913 - 鉴权参数
    session: AsyncSession,
    project_id: int,
    user_id: int,
    required: str | Role,
    *,
    is_superuser: bool = False,
    include_ancestor: bool = False,
) -> Role:
    """校验项目角色，不足抛 403；项目不存在抛 404。

    include_ancestor=True 时沿项目树向上继承父项目角色。
    """
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found(f"项目不存在: {project_id}")
    role = await get_project_role(session, project_id, user_id, is_superuser)
    if role is None and include_ancestor and project.parent_id is not None:
        return await require_project_role(session, project.parent_id, user_id, required, is_superuser=is_superuser)
    if role is None or not role_at_least(role, required):
        raise permission_denied()
    return role
