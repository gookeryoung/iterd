"""rules 路由：规则库 / 规则集 / 检查运行 / 报告查询."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import permission_denied
from iterd.plugins.projects import rbac
from iterd.plugins.projects import services as project_services
from iterd.plugins.rules import schemas, services
from iterd.plugins.rules.models import CheckRun

router = APIRouter(prefix="/api/v1", tags=["rules"])


# ---- 规则库 ----


@router.get("/checkers", response_model=list[dict[str, str]])
async def list_checkers(_user: CurrentUser) -> list[dict[str, str]]:
    """已注册检查器清单（新建规则时供前端下拉选择）。"""
    from iterd.checkers import checker_manifest

    return checker_manifest()


@router.get("/rules", response_model=list[schemas.RuleItemOut])
async def list_rules(_user: CurrentUser, session: SessionDep, category: str | None = None) -> list[schemas.RuleItemOut]:
    """规则库列表（登录用户）。"""
    rules = await services.list_rules(session, category=category)
    return [schemas.RuleItemOut.model_validate(r) for r in rules]


@router.post("/rules", response_model=schemas.RuleItemOut, status_code=201)
async def create_rule(body: schemas.RuleItemIn, user: CurrentUser, session: SessionDep) -> schemas.RuleItemOut:
    """创建规则条目（登录用户均可维护规则库，项目级使用由 RBAC 约束）。"""
    rule = await services.create_rule(session, actor_id=user.id, **body.model_dump())
    await session.commit()
    return schemas.RuleItemOut.model_validate(rule)


@router.patch("/rules/{rule_id}", response_model=schemas.RuleItemOut)
async def update_rule(
    rule_id: int, body: schemas.RuleItemIn, user: CurrentUser, session: SessionDep
) -> schemas.RuleItemOut:
    """更新规则条目。"""
    rule = await services.get_rule(session, rule_id)
    updated = await services.update_rule(
        session, actor_id=user.id, rule=rule, fields=body.model_dump(exclude_unset=True)
    )
    await session.commit()
    return schemas.RuleItemOut.model_validate(updated)


# ---- 规则集 ----


@router.get("/rule-sets", response_model=list[schemas.RuleSetOut])
async def list_rule_sets(
    _user: CurrentUser, session: SessionDep, project_id: int | None = None
) -> list[schemas.RuleSetOut]:
    """规则集列表（可按项目过滤，含全局）。"""
    rule_sets = await services.list_rule_sets(session, project_id=project_id)
    return [schemas.RuleSetOut.model_validate(rs) for rs in rule_sets]


@router.post("/rule-sets", response_model=schemas.RuleSetOut, status_code=201)
async def create_rule_set(body: schemas.RuleSetIn, user: CurrentUser, session: SessionDep) -> schemas.RuleSetOut:
    """创建规则集（指定项目时需该项目 designer+）。"""
    if body.project_id is not None:
        await rbac.require_project_role(session, body.project_id, user.id, "designer", is_superuser=user.is_superuser)
    rule_set = await services.create_rule_set(
        session,
        actor_id=user.id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        rule_ids=body.rule_ids,
    )
    await session.commit()
    return schemas.RuleSetOut.model_validate(rule_set)


@router.get("/rule-sets/{rule_set_id}", response_model=schemas.RuleSetDetailOut)
async def get_rule_set(rule_set_id: int, user: CurrentUser, session: SessionDep) -> schemas.RuleSetDetailOut:
    """规则集详情（含成员规则 id）。"""
    rule_set = await services.get_rule_set(session, rule_set_id)
    if rule_set.project_id is not None:
        await rbac.require_project_role(
            session,
            rule_set.project_id,
            user.id,
            "viewer",
            is_superuser=user.is_superuser,
            include_ancestor=True,
        )
    out = schemas.RuleSetDetailOut.model_validate(rule_set)
    out.rule_ids = await services.get_rule_set_rules(session, rule_set_id)
    return out


@router.post("/rule-sets/{rule_set_id}/rules", response_model=schemas.RuleSetDetailOut, status_code=201)
async def add_rules_to_set(
    rule_set_id: int, body: schemas.RuleSetRuleIn, user: CurrentUser, session: SessionDep
) -> schemas.RuleSetDetailOut:
    """向规则集批量添加规则（designer+；全局规则集需超管）。"""
    rule_set = await services.get_rule_set(session, rule_set_id)
    if rule_set.project_id is None:
        if not user.is_superuser:
            raise permission_denied("全局规则集仅超级管理员可维护")
    else:
        await rbac.require_project_role(
            session, rule_set.project_id, user.id, "designer", is_superuser=user.is_superuser
        )
    rule_ids = await services.set_rule_set_rules(session, rule_set_id=rule_set_id, rule_ids=body.rule_ids)
    await session.commit()
    out = schemas.RuleSetDetailOut.model_validate(rule_set)
    out.rule_ids = rule_ids
    return out


# ---- 检查运行与报告 ----


@router.get("/iterations/{iteration_id}/check-runs", response_model=list[schemas.CheckRunOut])
async def list_check_runs(iteration_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.CheckRunOut]:
    """迭代下检查运行列表（viewer+），带出任务 id 便于订阅进度。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    runs = list(
        (
            await session.execute(select(CheckRun).where(CheckRun.iteration_id == iteration_id).order_by(CheckRun.id))
        ).scalars()
    )
    outs = [schemas.CheckRunOut.model_validate(r) for r in runs]
    for out in outs:
        out.task_id = await services.get_check_run_task_id(session, out.id)
    return outs


@router.get("/check-runs/{check_run_id}", response_model=schemas.CheckRunOut)
async def get_check_run(check_run_id: int, user: CurrentUser, session: SessionDep) -> schemas.CheckRunOut:
    """检查运行详情（含任务 id）。"""
    run = await session.get(CheckRun, check_run_id)
    if run is None:
        from iterd.core.errors import not_found

        raise not_found(f"检查运行不存在: {check_run_id}")
    iteration = await project_services.get_iteration(session, run.iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    out = schemas.CheckRunOut.model_validate(run)
    out.task_id = await services.get_check_run_task_id(session, run.id)
    return out


@router.get("/check-runs/{check_run_id}/findings", response_model=list[schemas.CheckFindingOut])
async def list_findings(  # noqa: PLR0913, PLR0917 - 过滤参数
    check_run_id: int,
    user: CurrentUser,
    session: SessionDep,
    severity: str | None = None,
    artifact_version_id: int | None = None,
    rule_item_id: int | None = None,
    limit: int = Query(default=500, le=2000),
) -> list[schemas.CheckFindingOut]:
    """结构化报告查询：按严重级别/产物版本/规则过滤（viewer+），含规则与产物信息。"""
    run = await session.get(CheckRun, check_run_id)
    if run is None:
        from iterd.core.errors import not_found

        raise not_found(f"检查运行不存在: {check_run_id}")
    iteration = await project_services.get_iteration(session, run.iteration_id)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    records = await services.list_findings(
        session,
        check_run_id=check_run_id,
        severity=severity,
        artifact_version_id=artifact_version_id,
        rule_item_id=rule_item_id,
        limit=limit,
    )
    outs = [schemas.CheckFindingOut.model_validate(record.finding) for record in records]
    for out, record in zip(outs, records, strict=True):
        out.rule_code = record.rule_code
        out.rule_name = record.rule_name
        out.artifact_code = record.artifact_code
        out.artifact_name = record.artifact_name
        out.version_no = record.version_no
    return outs
