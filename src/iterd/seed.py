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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.security import hash_password, verify_password
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
    ("reviewer", "reviewer123", UserRole.USER),
    ("demo", "demo1234", UserRole.USER),
)

# 演示规则集（项目级）：绑定首个迭代，检查 Tab 开箱即用
_DEMO_RULE_SET_NAME = "演示规则集"

# 预置基线名称
_DEMO_BASELINE_NAME = "BL-首轮迭代"


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
        reviewer = await get_by_username(session, "reviewer")
        if reviewer is not None:
            await project_services.upsert_member(
                session, actor_id=admin.id, project_id=project.id, user_id=reviewer.id, role="reviewer"
            )
            logger.info("[seed] 添加项目成员: reviewer → 演示项目 (reviewer)")
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
        # 规划态迭代：供演示「激活」等状态流转操作
        planned = await project_services.create_iteration(
            session,
            actor_id=admin.id,
            project_id=project.id,
            title="第二轮迭代",
            objective="保持规划态，供演示「激活」等状态流转操作",
        )
        logger.info("[seed] 创建迭代: %s (planned)", planned.title)
    else:
        logger.info("[seed] 已存在项目数据，跳过项目/迭代/产物注入")

    # 演示规则
    logger.info("[seed] 步骤 3/4：创建演示规则")
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

    # 演示全流程内容：规则集 / 绑定 / 迭代激活 / 基线 / 预置检查运行
    logger.info("[seed] 步骤 4/4：完善演示全流程内容")
    demo_flow = await _ensure_demo_flow(session, actor_id=admin.id)

    logger.info("[seed] 演示数据注入完成：共 %s 个账号（三员 + 普通用户）", len(summary))
    return {"users": summary, "demo_flow": demo_flow}


async def _ensure_demo_flow(session: AsyncSession, *, actor_id: int) -> dict[str, Any]:
    """确保演示全流程内容齐备：规则集 / 绑定 / 迭代激活 / 基线 / 预置检查运行。

    全部幂等（按名称 / 既有数据查重，已存在跳过）；非演示库（无 DEMO 项目或迭代）整体跳过。
    预置检查运行在 seed 会话内直接执行（与 worker 同一执行路径），保证打开界面即有
    已完成的检查运行与发现项，全流程可演示。
    """
    from iterd.plugins.rules.models import CheckRun

    flow: dict[str, Any] = {
        "rule_set": False,
        "binding": False,
        "activated": False,
        "baseline": False,
        "check_run_id": None,
    }
    project = next((p for p in await project_services.list_projects(session) if p.code == "DEMO"), None)
    if project is None:
        logger.info("[seed] 无演示项目，跳过全流程内容注入")
        return flow
    iterations = await project_services.list_iterations(session, project.id)
    if not iterations:
        logger.info("[seed] 演示项目无迭代，跳过全流程内容注入")
        return flow
    iteration = iterations[0]

    # 1) 演示规则集（项目级，成员为全部既有规则）并绑定首个迭代
    rule_set = next(
        (
            rs
            for rs in await rule_services.list_rule_sets(session, project_id=project.id)
            if rs.name == _DEMO_RULE_SET_NAME
        ),
        None,
    )
    if rule_set is None:
        rules = await rule_services.list_rules(session)
        rule_set = await rule_services.create_rule_set(
            session,
            actor_id=actor_id,
            project_id=project.id,
            name=_DEMO_RULE_SET_NAME,
            description="演示规则集：文件名规范 + 材料元数据必填",
            rule_ids=[r.id for r in rules],
        )
        flow["rule_set"] = True
        logger.info("[seed] 创建规则集: %s（%s 条规则）", rule_set.name, len(rules))
    if await rule_services.get_binding(session, iteration.id) is None:
        await rule_services.bind_rule_set(
            session, actor_id=actor_id, rule_set_id=rule_set.id, iteration_id=iteration.id
        )
        flow["binding"] = True
        logger.info("[seed] 绑定规则集到迭代: %s（迭代 %s）", rule_set.name, iteration.number)

    # 2) 激活首个迭代（planned → active，走状态机）
    if iteration.status == "planned":
        await project_services.update_iteration(
            session, actor_id=actor_id, iteration=iteration, fields={"status": "active"}
        )
        flow["activated"] = True
        logger.info("[seed] 激活迭代: %s（#%s）", iteration.title, iteration.number)

    # 3) 基线：锁定迭代内产物当前版本
    baseline_names = {b.name for b in await project_services.list_baselines(session, iteration.id)}
    if _DEMO_BASELINE_NAME not in baseline_names:
        await project_services.create_baseline(
            session, actor_id=actor_id, iteration_id=iteration.id, name=_DEMO_BASELINE_NAME
        )
        flow["baseline"] = True
        logger.info("[seed] 创建基线: %s", _DEMO_BASELINE_NAME)

    # 4) 预置检查运行：无检查记录时执行一次，展示发现项与汇总
    runs = list((await session.execute(select(CheckRun.id).where(CheckRun.iteration_id == iteration.id))).scalars())
    if not runs:
        check_run, _task = await rule_services.create_check_run(
            session, actor_id=actor_id, iteration_id=iteration.id, rule_set_id=rule_set.id
        )
        summary = await rule_services.execute_check_run(session, check_run_id=check_run.id)
        flow["check_run_id"] = check_run.id
        logger.info("[seed] 预置检查运行 #%s 完成：%s", check_run.id, summary)
    else:
        logger.info("[seed] 迭代已有检查运行，跳过预置检查")
    return flow


async def ensure_admin(session: AsyncSession, username: str, password: str) -> None:
    """确保初始管理员存在（serve 启动时调用）：系统管理员角色.

    管理员口令以配置为准：已存在但口令与配置不符时重置为配置口令并记录告警，
    保证 ITERD_ADMIN_PASSWORD 变更（含默认口令调整）在存量库上同样生效。
    """
    admin = await get_by_username(session, username)
    if admin is None:
        await create_user(
            session, username=username, password=password, is_superuser=True, role=UserRole.SYSTEM_ADMIN.value
        )
        return
    if not admin.hashed_password.startswith("$2"):
        admin.hashed_password = hash_password(password)
        return
    if not verify_password(password, admin.hashed_password):
        admin.hashed_password = hash_password(password)
        logger.warning("[seed] 管理员 %s 已存在，口令与配置不符，已重置为配置口令", username)
