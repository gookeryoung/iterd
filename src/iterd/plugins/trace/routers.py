"""trace 路由：溯源图查询."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from iterd.api.deps import CurrentUser, SessionDep
from iterd.plugins.trace import service

router = APIRouter(prefix="/api/v1", tags=["trace"])


@router.get("/trace/graph")
async def trace_graph(
    _user: CurrentUser,
    session: SessionDep,
    urn: str,
    direction: str = Query(default="both", pattern="^(up|down|both)$"),
    depth: int = Query(default=5, ge=1, le=10),
) -> dict[str, Any]:
    """追溯查询：给定节点向上/向下/双向展开全链路，返回节点与边。"""
    return await service.trace_graph(session, urn=urn, direction=direction, depth=depth)
