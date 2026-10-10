"""notify 路由：审计日志查询."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from iterd.api.deps import CurrentUser, SessionDep
from iterd.plugins.notify import service

router = APIRouter(prefix="/api/v1", tags=["audit"])


class AuditLogOut(BaseModel):
    """审计日志对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    actor_name: str
    action: str
    resource_type: str
    resource_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str
    created_at: datetime


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    _user: CurrentUser,
    session: SessionDep,
    resource_type: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogOut]:
    """审计日志查询（登录用户可查）。"""
    logs = await service.list_audit_logs(session, resource_type=resource_type, limit=limit, offset=offset)
    return [AuditLogOut.model_validate(log) for log in logs]
