"""站内信通知服务：通知写入 / 查询 / 已读管理 / 渠道扩展点."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import not_found
from iterd.plugins.notify.models import Notification

# ---- 渠道扩展点（站内信为默认渠道：DB 记录本身；邮件/Webhook 经此协议后续接入）----


class Channel(Protocol):
    """外部投递渠道协议：实现 deliver 并调用 register_channel 即接入."""

    name: str

    async def deliver(self, notification: Notification) -> None:
        """把一条已落库的通知投递到外部渠道."""
        ...


_CHANNELS: dict[str, Channel] = {}


def register_channel(channel: Channel) -> None:
    """注册外部投递渠道（同名覆盖）。"""
    _CHANNELS[channel.name] = channel


def unregister_channels_for_test() -> None:
    """清空全部已注册渠道（仅测试隔离用）。"""
    _CHANNELS.clear()


async def notify(  # noqa: PLR0913 - 通知字段参数
    session: AsyncSession,
    *,
    user_id: int,
    ntype: str,
    title: str,
    body: str = "",
    project_id: int | None = None,
    link: str = "",
    resource_type: str = "",
    resource_id: int | str = "",
) -> Notification:
    """写一条站内信通知（不 commit，随业务事务提交）；已注册的外部渠道同步投递."""
    notification = Notification(
        user_id=user_id,
        ntype=ntype,
        title=title[:200],
        body=body[:1024],
        project_id=project_id,
        link=link[:200],
        resource_type=resource_type,
        resource_id=str(resource_id),
    )
    session.add(notification)
    await session.flush()
    for channel in _CHANNELS.values():
        await channel.deliver(notification)
    return notification


async def list_notifications(
    session: AsyncSession, *, user_id: int, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    """当前用户的通知列表（倒序，可只看未读）。"""
    stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.id.desc()).limit(limit)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list((await session.execute(stmt)).scalars())


async def unread_count(session: AsyncSession, *, user_id: int) -> int:
    """当前用户未读通知数。"""
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return int((await session.execute(stmt)).scalar_one())


async def mark_read(session: AsyncSession, *, user_id: int, notification_id: int) -> Notification:
    """标记单条通知已读（仅限本人，重复已读幂等）。"""
    notification = await session.get(Notification, notification_id)
    if notification is None or int(notification.user_id) != user_id:
        raise not_found(f"通知不存在: {notification_id}")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.flush()
    return notification


async def mark_all_read(session: AsyncSession, *, user_id: int) -> int:
    """全部未读标记已读，返回受影响条数（幂等）。"""
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)
