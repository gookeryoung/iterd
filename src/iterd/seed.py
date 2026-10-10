"""演示数据 seed：管理员 + 示例项目/迭代/规则/产物/规则集."""

from __future__ import annotations

import io
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.security import hash_password
from iterd.plugins.accounts.services import create_user, get_by_username
from iterd.plugins.artifacts import services as artifact_services
from iterd.plugins.projects import services as project_services
from iterd.plugins.rules import services as rule_services

logger = logging.getLogger("iterd.seed")


async def seed(session: AsyncSession, *, admin_username: str, admin_password: str) -> None:
    """注入演示数据（幂等：管理员已存在则跳过）。"""
    admin = await get_by_username(session, admin_username)
    if admin is None:
        admin = await create_user(
            session, username=admin_username, password=admin_password, email="admin@iterd.local", is_superuser=True
        )
        logger.info("已创建管理员 %s", admin_username)

    designer = await get_by_username(session, "designer")
    if designer is None:
        designer = await create_user(session, username="designer", password="designer123", email="designer@iterd.local")

    projects = await project_services.list_projects(session)
    if not projects:
        project = await project_services.create_project(
            session,
            actor_id=admin.id,
            parent_id=None,
            code="DEMO",
            name="演示项目",
            description="IterD 演示数据",
            status="active",
        )
        await project_services.upsert_member(
            session, actor_id=admin.id, project_id=project.id, user_id=admin.id, role="owner"
        )
        await project_services.upsert_member(
            session, actor_id=admin.id, project_id=project.id, user_id=designer.id, role="designer"
        )
        iteration = await project_services.create_iteration(
            session,
            actor_id=admin.id,
            project_id=project.id,
            title="第一轮迭代",
            objective="完成概念设计并通过规则检查",
        )
        artifact = await artifact_services.create_artifact(
            session,
            actor_id=admin.id,
            project_id=project.id,
            iteration_id=iteration.id,
            code="DEMO-001",
            name="示例零件图",
            category="drawing",
            description="演示产物",
        )
        await artifact_services.upload_version(
            session,
            actor_id=admin.id,
            artifact=artifact,
            filename="DEMO-001_rev-A.dwg",
            content_type="application/octet-stream",
            stream=io.BytesIO(b"demo dwg content"),
            metadata={"材料": "Q235", "尺寸": "100x50x10", "公差": "±0.1"},
        )

    rules = await rule_services.list_rules(session)
    if not rules:
        await rule_services.create_rule(
            session,
            actor_id=admin.id,
            code="DRAFT-001",
            name="图纸文件名规范",
            category="drafting",
            checker_type="filename_convention",
            params={"pattern": r"^[A-Z0-9-]+_rev[A-Z]\.\w+$"},
            severity_default="error",
        )
        await rule_services.create_rule(
            session,
            actor_id=admin.id,
            code="MATERIAL-001",
            name="材料元数据必填",
            category="material",
            checker_type="metadata_required",
            params={"required": {"材料": "str", "尺寸": "str", "公差": "str"}},
            severity_default="error",
        )


async def ensure_admin(session: AsyncSession, username: str, password: str) -> None:
    """确保初始管理员存在（serve 启动时调用）。"""
    admin = await get_by_username(session, username)
    if admin is None:
        await create_user(session, username=username, password=password, is_superuser=True)
    elif not admin.hashed_password.startswith("$2"):
        admin.hashed_password = hash_password(password)
