"""trace 插件：溯源 URN 注册与关联图."""

from __future__ import annotations

from .models import TraceLink, TraceNode
from .service import ensure_link, register

__all__ = ["TraceLink", "TraceNode", "ensure_link", "register"]
