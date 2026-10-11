"""artifacts 项目级文档库聚合服务：审查状态汇总 / part_of 关联边.

只读派生视图：不落新表、不改写路径。
审查状态口径（版本感知）：取产物所属迭代最近一次 CheckRun——
pending/running → running；已结束且当前版本晚于检查开始时间 → stale；
有 findings（任一历史版本）→ failed；否则 passed；无任何 CheckRun → unreviewed。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.plugins.artifacts.models import Artifact, ArtifactLink, ArtifactVersion
from iterd.plugins.artifacts.services import list_artifacts
from iterd.plugins.rules.models import CheckFinding, CheckRun, RuleItem

# 已结束的检查运行状态（可判定通过/未通过/过期）
_FINISHED_CHECK_STATUSES = ("succeeded", "failed")


def _naive(dt: datetime | None) -> datetime | None:
    """归一化为 naive datetime（SQLite 读取路径统一），避免 aware/naive 比较异常."""
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _trunc_second(dt: datetime | None) -> datetime | None:
    """截断到秒：created_at 由数据库端 current_timestamp 生成（秒级精度），须与 started_at 同分辨率比较."""
    dt = _naive(dt)
    if dt is not None:
        return dt.replace(microsecond=0)
    return dt


async def project_review_status(session: AsyncSession, *, project_id: int) -> list[dict[str, Any]]:
    """项目级产物审查状态聚合（排除软删），按产物 id 升序."""
    artifacts = await list_artifacts(session, project_id=project_id)
    if not artifacts:
        return []
    artifact_ids = [a.id for a in artifacts]
    iteration_ids = {a.iteration_id for a in artifacts}

    # 每个迭代最近一次 CheckRun（id 升序遍历，末次赋值即最新）
    runs = list(
        (
            await session.execute(
                select(CheckRun).where(CheckRun.iteration_id.in_(iteration_ids)).order_by(CheckRun.id)
            )
        ).scalars()
    )
    latest_by_iteration: dict[int, CheckRun] = {run.iteration_id: run for run in runs}

    # 当前版本创建时间（stale 推导）
    current_version_ids = [a.current_version_id for a in artifacts if a.current_version_id is not None]
    version_by_id: dict[int, ArtifactVersion] = {}
    if current_version_ids:
        version_by_id = {
            v.id: v
            for v in (
                await session.execute(select(ArtifactVersion).where(ArtifactVersion.id.in_(current_version_ids)))
            ).scalars()
        }

    # 全部版本归属（findings 按 artifact 归集）
    version_owner: dict[int, int] = {
        int(vid): int(aid)
        for vid, aid in (
            await session.execute(
                select(ArtifactVersion.id, ArtifactVersion.artifact_id).where(
                    ArtifactVersion.artifact_id.in_(artifact_ids)
                )
            )
        ).all()
    }

    # 最近一次已结束 CheckRun 中属于本项目产物的 findings（联表规则与版本号）
    latest_finished_ids = [run.id for run in latest_by_iteration.values() if run.status in _FINISHED_CHECK_STATUSES]
    findings_by_artifact: dict[int, list[dict[str, Any]]] = {}
    if latest_finished_ids:
        rows = (
            await session.execute(
                select(CheckFinding, RuleItem.code, RuleItem.name, ArtifactVersion.version_no)
                .join(RuleItem, CheckFinding.rule_item_id == RuleItem.id)
                .join(ArtifactVersion, CheckFinding.artifact_version_id == ArtifactVersion.id)
                .where(
                    CheckFinding.check_run_id.in_(latest_finished_ids),
                    ArtifactVersion.artifact_id.in_(artifact_ids),
                )
                .order_by(CheckFinding.id)
            )
        ).all()
        for finding, rule_code, rule_name, version_no in rows:
            artifact_id = version_owner.get(finding.artifact_version_id)
            if artifact_id is None:
                continue
            findings_by_artifact.setdefault(artifact_id, []).append(
                {
                    "id": finding.id,
                    "check_run_id": finding.check_run_id,
                    "artifact_version_id": finding.artifact_version_id,
                    "version_no": version_no,
                    "rule_id": finding.rule_item_id,
                    "rule_code": rule_code,
                    "rule_name": rule_name,
                    "severity": finding.severity,
                    "location": finding.location,
                    "message": finding.message,
                }
            )

    results: list[dict[str, Any]] = []
    for artifact in artifacts:
        run = latest_by_iteration.get(artifact.iteration_id)
        status = "unreviewed"
        check_run_id: int | None = None
        check_run_status: str | None = None
        last_checked_at: datetime | None = None
        last_check_started_at: datetime | None = None
        if run is not None:
            check_run_id = run.id
            check_run_status = run.status
            if run.status not in _FINISHED_CHECK_STATUSES:
                status = "running"
            else:
                last_checked_at = run.finished_at
                last_check_started_at = run.started_at
                current_version = (
                    version_by_id.get(artifact.current_version_id) if artifact.current_version_id else None
                )
                started = _trunc_second(run.started_at)
                created = _trunc_second(current_version.created_at if current_version else None)
                if created is not None and started is not None and created > started:
                    status = "stale"
                elif findings_by_artifact.get(artifact.id):
                    status = "failed"
                else:
                    status = "passed"
        results.append(
            {
                "artifact_id": artifact.id,
                "code": artifact.code,
                "name": artifact.name,
                "category": artifact.category,
                "iteration_id": artifact.iteration_id,
                "current_version_id": artifact.current_version_id,
                "status": status,
                "check_run_id": check_run_id,
                "check_run_status": check_run_status,
                "last_checked_at": last_checked_at,
                "last_check_started_at": last_check_started_at,
                "findings": findings_by_artifact.get(artifact.id, []),
            }
        )
    return results


async def project_part_of_links(session: AsyncSession, *, project_id: int) -> list[ArtifactLink]:
    """项目级 part_of 关联边（两端点均在本项目内且未软删），按 id 升序."""
    project_artifact_ids = select(Artifact.id).where(Artifact.project_id == project_id, Artifact.deleted_at.is_(None))
    stmt = (
        select(ArtifactLink)
        .where(
            ArtifactLink.link_type == "part_of",
            ArtifactLink.src_artifact_id.in_(project_artifact_ids),
            ArtifactLink.dst_artifact_id.in_(project_artifact_ids),
        )
        .order_by(ArtifactLink.id)
    )
    return list((await session.execute(stmt)).scalars())
