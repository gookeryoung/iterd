"""notify 插件：审计日志 + 站内信通知（事件触达；邮件/Webhook 为渠道扩展点）。"""

from __future__ import annotations

from .models import AuditLog, Notification
from .notifications import (
    Channel,
    list_notifications,
    mark_all_read,
    mark_read,
    notify,
    register_channel,
    unread_count,
    unregister_channels_for_test,
)
from .service import audit

__all__ = [
    "AuditLog",
    "Channel",
    "Notification",
    "audit",
    "list_notifications",
    "mark_all_read",
    "mark_read",
    "notify",
    "register_channel",
    "unread_count",
    "unregister_channels_for_test",
]
