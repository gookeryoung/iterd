"""检查器协议与注册表.

检查器按 checker_type 注册，规则编排侧（rules 插件）只依赖本模块的协议与注册表函数；
实现模块从本模块导入协议类型并在模块底部自注册。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from iterd.core.errors import IterdError


@dataclass
class ArtifactRef:
    """检查输入：产物版本引用."""

    artifact_id: int
    artifact_code: str
    artifact_name: str
    version_id: int
    version_no: int
    filename: str
    metadata: dict[str, Any]


@dataclass
class RuleRef:
    """检查输入：规则引用."""

    rule_id: int
    code: str
    name: str
    params: dict[str, Any]
    severity: str


@dataclass
class Finding:
    """检查输出."""

    rule_id: int
    severity: str
    location: str
    message: str


class CheckerAdapter(Protocol):
    """静态规则检查器协议：按 checker_type 注册."""

    checker_type: str

    def supported_extensions(self) -> tuple[str, ...]:
        """支持的文件扩展名（空表示全部）。"""

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        """对单个产物执行一组规则，返回发现项."""


_registry: dict[str, CheckerAdapter] = {}


def register_checker(checker: CheckerAdapter) -> None:
    """注册检查器（重复注册覆盖）。"""
    _registry[checker.checker_type] = checker


def get_checker(checker_type: str) -> CheckerAdapter:
    """取检查器，未注册抛 CHECKER_ERROR."""
    if checker_type not in _registry:
        raise IterdError(f"未注册的检查器: {checker_type}", code="ITERD-CHECKER_ERROR", status_code=422)
    return _registry[checker_type]


def registered_checkers() -> list[str]:
    """已注册检查器列表."""
    return sorted(_registry)


def checker_manifest() -> list[dict[str, str]]:
    """检查器清单（供前端下拉选择）：类型 + 说明。"""
    return [
        {"checker_type": name, "description": str(getattr(_registry[name], "description", ""))}
        for name in sorted(_registry)
    ]
