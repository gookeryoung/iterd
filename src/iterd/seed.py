"""演示数据 seed：三员 + 普通用户账号 + 示例项目/迭代/规则/产物.

三员模型参考 GB/T 22239 等级保护（对标 cndb seed 设计）：
- 系统管理员（admin，超级管理员）：系统配置、用户与项目管理
- 安全管理员（sec_admin）：权限策略、访问控制
- 审计管理员（audit_admin）：审计日志、合规检查
- 普通用户（demo / designer）：日常业务操作

seed 全程幂等：按用户名/既有数据查重，已存在跳过；每一步打印过程信息，
返回摘要 dict 供 CLI 输出账号清单。
"""

from __future__ import annotations

import io
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.security import hash_password
from iterd.plugins.accounts.models import UserRole
from iterd.plugins.accounts.services import create_user, get_by_username
from iterd.plugins.artifacts import services as artifact_services
from iterd.plugins.projects import services as project_services
from iterd.plugins.rules import services as rule_services

logger = logging.getLogger("iterd.seed")

# 演示账号清单：三员 + 普通用户（admin 口令来自配置，其余内置固定口令）
_DEMO_USERS: tuple[tuple[str, str, UserRole], ...] = (
    ("sec_admin", "sec1234", UserRole.SECURITY_ADMIN),
    ("audit_admin", "audit1234", UserRole.AUDIT_ADMIN),
    ("designer", "designer123", UserRole.USER),
    ("demo", "demo1234", UserRole.USER),
)


async def _ensure_user(  # noqa: PLR0913 - 幂等建号参数
    session: AsyncSession,
    username: str,
    password: str,
    *,
    role: UserRole,
    email: str = "",
    is_superuser: bool = False,
    summary: list[dict[str, Any]],
) -> Any:
    """按用户名幂等创建演示用户，过程信息写入日志与摘要."""
    existing = await get_by_username(session, username)
    if existing is not None:
        logger.info("[seed] 用户已存在，跳过: %s (角色: %s)", username, role.display_name)
        summary.append({"username": username, "password": "（沿用既有）", "role": role.display_name, "created": False})
        return existing
    user = await create_user(
        session, username=username, password=password, email=email, is_superuser=is_superuser, role=role.value
    )
    logger.info("[seed] 创建用户: %s / %s (角色: %s)", username, password, role.display_name)
    summary.append({"username": username, "password": password, "role": role.display_name, "created": True})
    return user


async def seed(session: AsyncSession, *, admin_username: str, admin_password: str) -> dict[str, Any]:
    """注入演示数据（幂等），返回摘要：用户清单与各业务对象数量."""
    summary: list[dict[str, Any]] = []
    logger.info("[seed] 开始注入演示数据 ...")

    # 用户：三员账号（系统管理员=超级管理员 + 安全管理员 + 审计管理员）+ 普通用户
    logger.info("[seed] 步骤 1/3：创建三员与普通用户账号")
    admin = await _ensure_user(
        session,
        admin_username,
        admin_password,
        role=UserRole.SYSTEM_ADMIN,
        email="admin@iterd.local",
        is_superuser=True,
        summary=summary,
    )
    for username, password, role in _DEMO_USERS:
        await _ensure_user(session, username, password, role=role, email=f"{username}@iterd.local", summary=summary)

    # 示例项目/迭代/产物
    logger.info("[seed] 步骤 2/3：创建示例项目与产物")
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
        logger.info("[seed] 创建项目: %s (%s)", project.name, project.code)
        await project_services.upsert_member(
            session, actor_id=admin.id, project_id=project.id, user_id=admin.id, role="owner"
        )
        designer = await get_by_username(session, "designer")
        if designer is not None:
            await project_services.upsert_member(
                session, actor_id=admin.id, project_id=project.id, user_id=designer.id, role="designer"
            )
            logger.info("[seed] 添加项目成员: designer → 演示项目 (designer)")
        demo = await get_by_username(session, "demo")
        if demo is not None:
            await project_services.upsert_member(
                session, actor_id=admin.id, project_id=project.id, user_id=demo.id, role="viewer"
            )
            logger.info("[seed] 添加项目成员: demo → 演示项目 (viewer)")
        iteration = await project_services.create_iteration(
            session,
            actor_id=admin.id,
            project_id=project.id,
            title="第一轮迭代",
            objective="完成概念设计并通过规则检查",
        )
        logger.info("[seed] 创建迭代: %s", iteration.title)
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
        logger.info("[seed] 创建产物: %s (%s)", artifact.name, artifact.code)
        await artifact_services.upload_version(
            session,
            actor_id=admin.id,
            artifact=artifact,
            filename="DEMO-001_rev-A.dwg",
            content_type="application/octet-stream",
            stream=io.BytesIO(b"demo dwg content"),
            metadata={"材料": "Q235", "尺寸": "100x50x10", "公差": "±0.1"},
        )
        logger.info("[seed] 上传产物版本: %s (rev A)", artifact.code)
    else:
        logger.info("[seed] 已存在项目数据，跳过项目/迭代/产物注入")

    # 演示规则
    logger.info("[seed] 步骤 3/3：创建演示规则")
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
        logger.info("[seed] 创建规则: DRAFT-001 图纸文件名规范")
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
        logger.info("[seed] 创建规则: MATERIAL-001 材料元数据必填")
    else:
        logger.info("[seed] 已存在规则数据，跳过规则注入")

    logger.info("[seed] 演示数据注入完成：共 %s 个账号（三员 + 普通用户）", len(summary))
    return {"users": summary}


async def ensure_admin(session: AsyncSession, username: str, password: str) -> None:
    """确保初始管理员存在（serve 启动时调用）：系统管理员角色."""
    admin = await get_by_username(session, username)
    if admin is None:
        await create_user(
            session, username=username, password=password, is_superuser=True, role=UserRole.SYSTEM_ADMIN.value
        )
    elif not admin.hashed_password.startswith("$2"):
        admin.hashed_password = hash_password(password)
