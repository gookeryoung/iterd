"""求解器协议、注册表与共享工具.

求解器按 solver_type 注册，仿真编排侧（simulation 插件）只依赖本模块的协议与注册表函数；
实现模块从本模块导入协议类型与取参工具，在模块底部自注册。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from iterd.core.errors import IterdError


@dataclass
class SimInput:
    """求解输入：作业参数（模板默认值与作业入参合并后）与产物上下文."""

    job_id: int
    artifact_code: str = ""
    artifact_name: str = ""
    version_no: int = 0
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metric:
    """求解输出指标."""

    key: str
    value: float
    unit: str = ""
    label: str = ""


class SolverAdapter(Protocol):
    """数值求解器协议：按 solver_type 注册."""

    solver_type: str

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格：[{key, label, unit, default, required}]."""

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格：[{key, label, unit}]."""

    def run(self, sim: SimInput) -> list[Metric]:
        """执行一次求解，返回指标列表（参数非法时抛 IterdError）。"""


_registry: dict[str, SolverAdapter] = {}


def register_solver(solver: SolverAdapter) -> None:
    """注册求解器（重复注册覆盖）。"""
    _registry[solver.solver_type] = solver


def get_solver(solver_type: str) -> SolverAdapter:
    """取求解器，未注册抛 SOLVER_ERROR."""
    if solver_type not in _registry:
        raise IterdError(f"未注册的求解器: {solver_type}", code="ITERD-SOLVER_ERROR", status_code=422)
    return _registry[solver_type]


def registered_solvers() -> list[str]:
    """已注册求解器类型列表。"""
    return sorted(_registry)


def solver_manifest() -> list[dict[str, Any]]:
    """求解器清单（供前端下拉与动态参数表单）。"""
    return [
        {
            "solver_type": name,
            "description": str(getattr(_registry[name], "description", "")),
            "inputs": _registry[name].input_spec(),
            "metrics": _registry[name].metric_spec(),
        }
        for name in sorted(_registry)
    ]


def default_inputs(solver_type: str) -> dict[str, Any]:
    """求解器默认输入参数（模板未指定时使用）。"""
    return {
        str(item["key"]): item.get("default")
        for item in get_solver(solver_type).input_spec()
        if item.get("default") is not None
    }


def _number(inputs: dict[str, Any], spec: dict[str, Any]) -> float:
    """取数值参数（缺省回落到规格默认值，非法值抛错）。"""
    key = str(spec["key"])
    raw = inputs.get(key, spec.get("default"))
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise IterdError(f"求解参数 {key} 不是数值: {raw!r}", code="ITERD-SOLVER_ERROR", status_code=422) from exc
