"""演示数据 seed：覆盖式重建（对标 cndb seed）+ 典型案例数据集载入.

覆盖模式：每次执行先清空业务数据（项目/迭代/产物/规则/规则集/检查/仿真/任务/溯源，
保留用户与审计日志），再重建三员 + 普通用户账号、演示项目全流程内容，并载入
``examples/datasets/`` 下全部典型案例（含同步预执行审查流水线），
典型案例数据集更新后重跑 ``iterd seed`` 即可立即在界面展示。

三员模型参考 GB/T 22239 等级保护（对标 cndb seed 设计）：
- 系统管理员（admin，超级管理员）：系统配置、用户与项目管理
- 安全管理员（sec_admin）：权限策略、访问控制
- 审计管理员（audit_admin）：审计日志、合规检查
- 普通用户（demo / designer）：日常业务操作

账号按用户名查重建号（已存在沿用），口令与 seed 内置/配置口令不符时对齐并告警；
每一步打印过程信息，返回摘要 dict 供 CLI 输出账号清单与典型案例统计。
"""

from __future__ import annotations

import io
import logging
from typing import Any

from sqlalchemy import delete, select
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

# 演示规则集（项目级）：供演示审查流水线的规则检查作业使用
_DEMO_RULE_SET_NAME = "演示规则集"

# 演示仿真模板 / 审查模板编码
_DEMO_SIM_TEMPLATE_CODE = "DEMO-BEAM-CHECK"
_DEMO_WORKFLOW_CODE = "DEMO-REVIEW"

# 覆盖时保留的表：账号与审计日志（只增不改）
_KEEP_TABLES = frozenset({"users", "audit_logs"})


async def _reset_business_data(session: AsyncSession) -> int:
    """清空全部业务表（覆盖式重建前置，对标 cndb seed），返回清空表数量.

    按依赖逆序删除（子表在前）；用户与审计日志保留，保证账号体系与审计痕迹延续。
    """
    from iterd.models import Base
    from iterd.plugins.accounts import models as accounts_models  # noqa: F401
    from iterd.plugins.artifacts import models as artifacts_models  # noqa: F401
    from iterd.plugins.notify import models as notify_models  # noqa: F401
    from iterd.plugins.projects import models as projects_models  # noqa: F401
    from iterd.plugins.rules import models as rules_models  # noqa: F401
    from iterd.plugins.simulation import models as simulation_models  # noqa: F401
    from iterd.plugins.trace import models as trace_models  # noqa: F401
    from iterd.tasks import models as task_models  # noqa: F401

    tables = [t for t in reversed(Base.metadata.sorted_tables) if t.name not in _KEEP_TABLES]
    for table in tables:
        await session.execute(delete(table))
    await session.commit()
    logger.info("[seed] 覆盖模式：已清空 %s 张业务表（保留 users / audit_logs）", len(tables))
    return len(tables)


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
    """按用户名幂等创建演示用户，口令与内置不符时对齐，过程信息写入日志与摘要."""
    existing = await get_by_username(session, username)
    if existing is not None:
        mark = "（沿用既有）"
        if not verify_password(password, existing.hashed_password):
            existing.hashed_password = hash_password(password)
            mark = "（口令已对齐）"
            logger.warning("[seed] 用户 %s 已存在，口令与演示口令不符，已对齐", username)
        logger.info("[seed] 用户已存在，跳过创建: %s (角色: %s)", username, role.display_name)
        summary.append({"username": username, "password": password + mark, "role": role.display_name, "created": False})
        return existing
    user = await create_user(
        session, username=username, password=password, email=email, is_superuser=is_superuser, role=role.value
    )
    logger.info("[seed] 创建用户: %s / %s (角色: %s)", username, password, role.display_name)
    summary.append({"username": username, "password": password, "role": role.display_name, "created": True})
    return user


async def seed(session: AsyncSession, *, admin_username: str, admin_password: str) -> dict[str, Any]:
    """覆盖式注入演示数据与典型案例，返回摘要：用户清单、演示流程与案例统计."""
    summary: list[dict[str, Any]] = []
    logger.info("[seed] 开始覆盖式注入演示数据 ...")

    # 覆盖模式：清空业务数据后整体重建（对标 cndb seed；用户与审计日志保留）
    await _reset_business_data(session)

    # 用户：三员账号（系统管理员=超级管理员 + 安全管理员 + 审计管理员）+ 普通用户
    logger.info("[seed] 步骤 1/5：创建三员与普通用户账号")
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

    # 示例项目/迭代/产物（覆盖重建后业务表为空，直接创建）
    logger.info("[seed] 步骤 2/5：创建示例项目与产物")
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
        filename="DEMO-001_revA.dwg",
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

    # 演示规则
    logger.info("[seed] 步骤 3/5：创建演示规则")
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

    # 演示全流程内容：规则集 / 迭代激活 / 演示审查模板 / 预置提交与运行
    logger.info("[seed] 步骤 4/5：完善演示全流程内容")
    demo_flow = await _ensure_demo_flow(session, actor_id=admin.id)

    # 典型案例：examples/datasets 全量载入并预执行审查流水线（非源码仓库自动跳过）
    logger.info("[seed] 步骤 5/5：载入典型案例数据集")
    from iterd.example_datasets import datasets_root, load_all_cases

    if datasets_root() is None:
        cases: list[dict[str, Any]] = []
        logger.info("[seed] 非源码仓库（未找到 examples/datasets），跳过典型案例载入")
    else:
        cases = await load_all_cases(session, actor_id=admin.id)
        for case in cases:
            logger.info(
                "[seed] 典型案例 %s：项目 %s / 迭代 %s / 产物 %s / 流水线运行 %s",
                case["name"],
                case["projects"],
                case["iterations"],
                case["artifacts"],
                len(case["workflows"]),
            )

    logger.info("[seed] 演示数据注入完成：共 %s 个账号（三员 + 普通用户）", len(summary))
    return {"users": summary, "demo_flow": demo_flow, "cases": cases}


# 演示审查模板定义：规则检查 → 梁静力仿真（needs 门禁），全绿链路演示
_DEMO_WORKFLOW_DEFINITION = """\
name: 演示审查流水线
description: 静态规则检查通过后执行梁静力校核

jobs:
  rules-check:
    name: 静态规则检查
    uses: rules/check
    with:
      rule_set: 演示规则集
  beam-check:
    name: 梁静力校核
    needs: rules-check
    uses: simulation/run
    with:
      template: DEMO-BEAM-CHECK
      artifact: DEMO-001
"""


async def _ensure_demo_flow(session: AsyncSession, *, actor_id: int) -> dict[str, Any]:
    """确保演示全流程内容齐备：规则集 / 迭代激活 / 演示审查模板 / 提交方案与运行.

    全部幂等（按名称 / 编码 / 既有提交查重）；提交产生的运行在 seed 会话内同步执行
    （与 worker 同一执行路径，调度任务执行后删除避免 worker 重复执行），
    保证打开界面即有完整的 提交 → 运行 → 步骤 → 日志 演示数据。
    """
    flow: dict[str, Any] = {
        "rule_set": False,
        "activated": False,
        "sim_template": False,
        "workflow": False,
        "submission_id": None,
        "runs": 0,
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

    # 1) 演示规则集（项目级，成员为全部既有规则），供规则检查作业引用
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

    # 2) 激活首个迭代（planned → active，走状态机；active 才可提交方案）
    if iteration.status == "planned":
        await project_services.update_iteration(
            session, actor_id=actor_id, iteration=iteration, fields={"status": "active"}
        )
        flow["activated"] = True
        logger.info("[seed] 激活迭代: %s（#%s）", iteration.title, iteration.number)

    # 3) 演示仿真模板（beam_static 梁静力校核）与审查模板（rules-check → beam-check 门禁链路）
    from iterd.plugins.simulation import services as sim_services
    from iterd.plugins.workflows import services as workflow_services

    sim_template = next(
        (
            t
            for t in await sim_services.list_templates(session, project_id=project.id)
            if t.code == _DEMO_SIM_TEMPLATE_CODE
        ),
        None,
    )
    if sim_template is None:
        await sim_services.create_template(
            session,
            actor_id=actor_id,
            code=_DEMO_SIM_TEMPLATE_CODE,
            name="梁静力校核（演示）",
            solver_type="beam_static",
            project_id=project.id,
            params={"load": 1000, "length": 500, "width": 20, "height": 40, "modulus": 206000, "yield_strength": 235},
            thresholds={"max_stress": {"max": 160}, "deflection": {"max": 2.0}, "safety_factor": {"min": 1.2}},
            description="演示仿真模板：beam_static 求解器默认工况，三项指标均在阈值内，结论 pass",
        )
        flow["sim_template"] = True
        logger.info("[seed] 创建演示仿真模板: %s", _DEMO_SIM_TEMPLATE_CODE)
    workflow = next(
        (
            t
            for t in await workflow_services.list_templates(session, project_id=project.id)
            if t.code == _DEMO_WORKFLOW_CODE
        ),
        None,
    )
    if workflow is None:
        await workflow_services.create_template(
            session,
            actor_id=actor_id,
            project_id=project.id,
            code=_DEMO_WORKFLOW_CODE,
            name="演示审查流水线",
            description="静态规则检查通过后执行梁静力校核；演示数据全绿，流水线结论 success",
            definition=_DEMO_WORKFLOW_DEFINITION,
        )
        flow["workflow"] = True
        logger.info("[seed] 创建演示审查模板: %s", _DEMO_WORKFLOW_CODE)

    # 4) 提交一次迭代方案并进程内执行（无既有提交时；运行走 worker 同一执行路径）
    from iterd.tasks.models import Task

    submissions = await workflow_services.list_submissions(session, iteration_id=iteration.id)
    if not submissions:
        submission, runs = await workflow_services.create_submission(
            session,
            actor_id=actor_id,
            iteration_id=iteration.id,
            title="首轮方案提交",
            note="seed 预置演示提交：触发项目内全部启用审查模板",
        )
        flow["submission_id"] = int(submission.id)
        for run in runs:
            run_id = int(run.id)
            summary = await workflow_services.execute_workflow_run(session, run_id=run_id)
            flow["runs"] += 1
            logger.info("[seed] 演示运行 #%s 执行完成：%s", run_id, summary.get("conclusion"))
        # 同步执行后清理遗留调度任务，避免 serve 启动 worker 后重复执行
        stale = (
            await session.execute(select(Task.id).where(Task.task_type == "workflow_run", Task.status == "pending"))
        ).scalars()
        for task_id in list(stale):
            task = await session.get(Task, int(task_id))
            if task is not None:
                await session.delete(task)
        await session.commit()
        logger.info("[seed] 预置提交方案 #%s：%s 条运行", submission.id, len(runs))
    else:
        logger.info("[seed] 迭代已有提交方案，跳过预置提交")
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
