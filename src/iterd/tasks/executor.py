"""任务执行器协议与注册表."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class TaskContext(Protocol):
    """执行期上下文：进度回调与日志."""

    def progress(self, stage: str, percent: int) -> None:
        """更新进度（stage 描述阶段，percent 0-100）。"""

    def log(self, level: str, message: str) -> None:
        """追加任务日志（level: info/warning/error）。"""


@dataclass
class TaskResult:
    """任务执行结果."""

    success: bool
    error: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)


ExecutorFn = Any  # async (session, payload, ctx) -> TaskResult


_registry: dict[str, ExecutorFn] = {}


def register_executor(task_type: str, fn: ExecutorFn) -> None:
    """按 task_type 注册执行器（重复注册覆盖）。"""
    _registry[task_type] = fn


def get_executor(task_type: str) -> ExecutorFn:
    """取执行器，未注册抛错."""
    if task_type not in _registry:
        raise KeyError(f"未注册的任务类型: {task_type}")
    return _registry[task_type]


def registered_types() -> list[str]:
    """已注册的任务类型列表（info 接口用）。"""
    return sorted(_registry)


async def run_executor(session: AsyncSession, task_type: str, payload: dict[str, Any], ctx: TaskContext) -> TaskResult:
    """调用执行器."""
    return await get_executor(task_type)(session, payload, ctx)
