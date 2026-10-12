"""reports 路由：迭代对比 diff / 审查报告生成 / 报告归档."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query

from iterd.api.deps import CurrentUser, SessionDep
from iterd.plugins.projects import rbac
from iterd.plugins.reports import schemas, services

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/iterations/{iteration_id}/diff", response_model=schemas.IterationDiffOut)
async def iteration_diff(
    iteration_id: int,
    user: CurrentUser,
    session: SessionDep,
    baseline: int | None = Query(default=None, description="基线迭代 id，缺省自动选前序 closed 迭代"),
) -> schemas.IterationDiffOut:
    """迭代对比：产物 / BOM / 检查结论 / 仿真 / 审批五段结构化差异（viewer+）."""
    iteration, baseline_iteration = await services.get_checked_iteration(session, iteration_id, baseline)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return schemas.IterationDiffOut.model_validate(
        await services.iteration_diff(session, iteration=iteration, baseline=baseline_iteration)
    )


@router.get("/iterations/{iteration_id}/report", response_model=schemas.ReportOut)
async def build_report(iteration_id: int, user: CurrentUser, session: SessionDep) -> schemas.ReportOut:
    """生成交付审查报告 Markdown（四段聚合，viewer+，不落库）."""
    iteration, _ = await services.get_checked_iteration(session, iteration_id, None)
    await rbac.require_project_role(
        session, iteration.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    markdown = await services.build_report_markdown(session, iteration)
    return schemas.ReportOut(
        iteration_id=iteration.id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        markdown=markdown,
    )


@router.post("/iterations/{iteration_id}/report/archive", response_model=schemas.ArchiveReportOut, status_code=201)
async def archive_report(iteration_id: int, user: CurrentUser, session: SessionDep) -> schemas.ArchiveReportOut:
    """报告归档：生成 Markdown 并以 result 产物上传进文档库（designer+，可重复归档为新版本）."""
    iteration, _ = await services.get_checked_iteration(session, iteration_id, None)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    markdown = await services.build_report_markdown(session, iteration)
    result = await services.archive_report(session, actor_id=user.id, iteration=iteration, markdown=markdown)
    await session.commit()
    return schemas.ArchiveReportOut(**result)


__all__ = ["router"]
