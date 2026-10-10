"""任务执行框架：任务表 + worker + 执行器注册表（规则检查与仿真共用）。"""

from __future__ import annotations

from .executor import TaskContext, TaskResult, get_executor, register_executor
from .models import Task

__all__ = ["Task", "TaskContext", "TaskResult", "get_executor", "register_executor"]
