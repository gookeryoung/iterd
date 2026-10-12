"""notify 路由：审计日志查询 + 站内信通知（列表/未读/已读）+ 通知 WebSocket 推送."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from iterd.api.deps import CurrentUser, SessionDep
from iterd.plugins.notify import notifications, service

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


# ---- 站内信通知 ----


class NotificationOut(BaseModel):
    """站内信通知对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    ntype: str
    title: str
    body: str
    project_id: int | None
    link: str
    resource_type: str
    resource_id: str
    read_at: datetime | None
    created_at: datetime


class UnreadCountOut(BaseModel):
    """未读计数。"""

    count: int


class MarkAllReadOut(BaseModel):
    """全部已读结果。"""

    marked: int


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: CurrentUser,
    session: SessionDep,
    unread_only: bool = False,
    limit: int = Query(default=50, le=200),
) -> list[NotificationOut]:
    """当前用户的通知列表（倒序，可只看未读）。"""
    items = await notifications.list_notifications(session, user_id=int(user.id), unread_only=unread_only, limit=limit)
    return [NotificationOut.model_validate(item) for item in items]


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def notifications_unread_count(user: CurrentUser, session: SessionDep) -> UnreadCountOut:
    """当前用户未读通知数。"""
    return UnreadCountOut(count=await notifications.unread_count(session, user_id=int(user.id)))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(notification_id: int, user: CurrentUser, session: SessionDep) -> NotificationOut:
    """标记单条通知已读（仅限本人）。"""
    item = await notifications.mark_read(session, user_id=int(user.id), notification_id=notification_id)
    await session.commit()
    return NotificationOut.model_validate(item)


@router.post("/notifications/read-all", response_model=MarkAllReadOut)
async def mark_all_notifications_read(user: CurrentUser, session: SessionDep) -> MarkAllReadOut:
    """全部未读通知标记已读。"""
    marked = await notifications.mark_all_read(session, user_id=int(user.id))
    await session.commit()
    return MarkAllReadOut(marked=marked)


async def _authenticate_ws_user(websocket: WebSocket) -> int | None:
    """等待并校验首帧 JWT，成功返回 user_id（失败关闭连接返回 None）。"""
    import json

    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.core.security import decode_access_token

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        token = str(json.loads(raw).get("token", ""))
        uid = decode_access_token(token, get_settings())
        settings = get_settings()
        factory = get_session_factory(get_engine(settings.database_url))
        async with factory() as session:
            from sqlalchemy import select

            from iterd.plugins.accounts.models import User

            user = (await session.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
            if user is None or not user.is_active:
                await websocket.close(code=1008)
                return None
            return int(user.id)
    except Exception:
        with contextlib.suppress(Exception):
            await websocket.close(code=1008)
        return None


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket) -> None:
    """站内信推送：首帧 JWT 鉴权后轮询未读计数，变化即推送（单机轮询模式，与任务流一致）.

    推送帧：{"unread_count": int}。
    """
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.notify import notifications as notify_service

    await websocket.accept()
    user_id = await _authenticate_ws_user(websocket)
    if user_id is None:
        return
    last_count: int | None = None
    try:
        while True:
            settings = get_settings()
            factory = get_session_factory(get_engine(settings.database_url))
            async with factory() as session:
                count = await notify_service.unread_count(session, user_id=user_id)
            if count != last_count:
                await websocket.send_json({"unread_count": count})
                last_count = count
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    with contextlib.suppress(Exception):
        await websocket.close()
