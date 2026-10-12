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
    category: str = ""


@dataclass
class RuleRef:
    """检查输入：规则引用."""

    rule_id: int
    code: str
    name: str
    params: dict[str, Any]
    severity: str


@dataclass
class BomItemRef:
    """检查输入：BOM 行引用."""

    part_code: str
    part_name: str
    material: str
    spec: str
    quantity: int
    unit_weight: float | None
    note: str


@dataclass
class CheckContext:
    """跨产物检查输入：迭代产物集 + BOM + 迭代元数据."""

    project_id: int
    iteration_id: int
    iteration_no: int
    iteration_title: str
    artifacts: list[ArtifactRef]
    bom_items: list[BomItemRef]


@dataclass
class Finding:
    """检查输出（context 检查器可通过 artifact_version_id 关联具体产物版本，缺省为迭代级发现项）."""

    rule_id: int
    severity: str
    location: str
    message: str
    artifact_version_id: int | None = None


class CheckerAdapter(Protocol):
    """静态规则检查器协议：按 checker_type 注册（单产物轨道）."""

    checker_type: str

    def supported_extensions(self) -> tuple[str, ...]:
        """支持的文件扩展名（空表示全部）。"""

    def check(self, artifact: ArtifactRef, rules: list[RuleRef]) -> list[Finding]:
        """对单个产物执行一组规则，返回发现项."""


class ContextCheckerAdapter(Protocol):
    """跨产物检查器协议：按 checker_type 注册（context 轨道，每次检查运行执行一次）."""

    checker_type: str

    def check(self, context: CheckContext, rules: list[RuleRef]) -> list[Finding]:
        """对迭代产物集 + BOM 上下文执行一组规则，返回发现项."""


_registry: dict[str, CheckerAdapter] = {}
_context_registry: dict[str, ContextCheckerAdapter] = {}


def register_checker(checker: CheckerAdapter) -> None:
    """注册单产物检查器（重复注册覆盖；与 context 轨道重名视为配置错误）。"""
    if checker.checker_type in _context_registry:
        raise IterdError(
            f"检查器 {checker.checker_type} 已注册为 context 轨道，不允许双轨重名",
            code="ITERD-CHECKER_ERROR",
            status_code=422,
        )
    _registry[checker.checker_type] = checker


def register_context_checker(checker: ContextCheckerAdapter) -> None:
    """注册跨产物检查器（重复注册覆盖；与单产物轨道重名视为配置错误）。"""
    if checker.checker_type in _registry:
        raise IterdError(
            f"检查器 {checker.checker_type} 已注册为单产物轨道，不允许双轨重名",
            code="ITERD-CHECKER_ERROR",
            status_code=422,
        )
    _context_registry[checker.checker_type] = checker


def get_checker(checker_type: str) -> CheckerAdapter:
    """取单产物检查器，未注册抛 CHECKER_ERROR."""
    if checker_type not in _registry:
        raise IterdError(f"未注册的检查器: {checker_type}", code="ITERD-CHECKER_ERROR", status_code=422)
    return _registry[checker_type]


def get_context_checker(checker_type: str) -> ContextCheckerAdapter:
    """取跨产物检查器，未注册抛 CHECKER_ERROR."""
    if checker_type not in _context_registry:
        raise IterdError(f"未注册的跨产物检查器: {checker_type}", code="ITERD-CHECKER_ERROR", status_code=422)
    return _context_registry[checker_type]


def registered_checkers() -> list[str]:
    """已注册单产物检查器列表."""
    return sorted(_registry)


def registered_context_checkers() -> list[str]:
    """已注册跨产物检查器列表."""
    return sorted(_context_registry)


def checker_kind(checker_type: str) -> str:
    """检查器轨道：context（跨产物）优先判定，其余为 artifact（单产物）。"""
    return "context" if checker_type in _context_registry else "artifact"


def checker_manifest() -> list[dict[str, str]]:
    """检查器清单（供前端下拉选择）：类型 + 轨道 kind（artifact|context）+ 说明."""
    entries: dict[str, str] = {}
    for name in sorted(_registry):
        entries[name] = str(getattr(_registry[name], "description", ""))
    for name in sorted(_context_registry):
        entries[name] = str(getattr(_context_registry[name], "description", ""))
    return [
        {"checker_type": name, "kind": checker_kind(name), "description": description}
        for name, description in sorted(entries.items())
    ]
