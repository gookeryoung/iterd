"""审计服务：写操作统一入口，与业务同事务提交."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.plugins.notify.models import AuditLog


async def audit(  # noqa: PLR0913 - 审计字段
    session: AsyncSession,
    *,
    actor_id: int | None,
    actor_name: str,
    action: str,
    resource_type: str,
    resource_id: int | str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str = "",
) -> None:
    """写一条审计记录（不 commit，随业务事务提交）."""
    session.add(
        AuditLog(
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before=before,
            after=after,
            ip=ip,
        )
    )


async def list_audit_logs(
    session: AsyncSession, *, resource_type: str | None = None, limit: int = 100, offset: int = 0
) -> list[AuditLog]:
    """审计日志查询（倒序）。"""
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    return list((await session.execute(stmt)).scalars())
