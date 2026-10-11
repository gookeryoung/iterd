"""求解器协议、注册表与内置实现.

P1 内置：beam_static（简支梁三点弯曲近似，确定性）；新增求解器不改平台代码。
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


class BeamStaticSolver:
    """简支梁三点弯曲静力近似求解器（内置确定性示例，非有限元）。

    输入：load(N) / length(mm) / width(mm) / height(mm) / modulus(MPa) / yield_strength(MPa)。
    输出：max_stress(MPa) / deflection(mm) / safety_factor(-)。
    """

    solver_type = "beam_static"
    description = "简支梁三点弯曲静力近似（内置确定性示例求解器）"

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格（均带默认值，作业可不传参直接运行）。"""
        return [
            {"key": "load", "label": "集中载荷", "unit": "N", "default": 1000, "required": False},
            {"key": "length", "label": "跨距", "unit": "mm", "default": 500, "required": False},
            {"key": "width", "label": "截面宽", "unit": "mm", "default": 20, "required": False},
            {"key": "height", "label": "截面高", "unit": "mm", "default": 40, "required": False},
            {"key": "modulus", "label": "弹性模量", "unit": "MPa", "default": 206000, "required": False},
            {"key": "yield_strength", "label": "屈服强度", "unit": "MPa", "default": 235, "required": False},
        ]

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格。"""
        return [
            {"key": "max_stress", "label": "最大弯曲应力", "unit": "MPa"},
            {"key": "deflection", "label": "跨中挠度", "unit": "mm"},
            {"key": "safety_factor", "label": "安全系数", "unit": ""},
        ]

    def run(self, sim: SimInput) -> list[Metric]:
        """按材料力学公式求解（截面惯性矩 I=bh^3/12）。"""
        values = {str(item["key"]): _number(sim.inputs, item) for item in self.input_spec()}
        for key, value in values.items():
            if value <= 0:
                raise IterdError(f"求解参数 {key} 必须为正数: {value}", code="ITERD-SOLVER_ERROR", status_code=422)

        load = values["load"]
        length = values["length"]
        width = values["width"]
        height = values["height"]
        modulus = values["modulus"]
        yield_strength = values["yield_strength"]
        inertia = width * height**3 / 12
        max_stress = 1.5 * load * length / (width * height**2)
        deflection = load * length**3 / (48 * modulus * inertia)
        safety_factor = yield_strength / max_stress
        return [
            Metric(key="max_stress", value=round(max_stress, 4), unit="MPa", label="最大弯曲应力"),
            Metric(key="deflection", value=round(deflection, 6), unit="mm", label="跨中挠度"),
            Metric(key="safety_factor", value=round(safety_factor, 4), unit="", label="安全系数"),
        ]


def _number(inputs: dict[str, Any], spec: dict[str, Any]) -> float:
    """取数值参数（缺省回落到规格默认值，非法值抛错）。"""
    key = str(spec["key"])
    raw = inputs.get(key, spec.get("default"))
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise IterdError(f"求解参数 {key} 不是数值: {raw!r}", code="ITERD-SOLVER_ERROR", status_code=422) from exc


register_solver(BeamStaticSolver())


__all__ = [
    "BeamStaticSolver",
    "Metric",
    "SimInput",
    "SolverAdapter",
    "default_inputs",
    "get_solver",
    "register_solver",
    "registered_solvers",
    "solver_manifest",
]
