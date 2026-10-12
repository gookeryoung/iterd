"""螺栓剪切求解器."""

from __future__ import annotations

from math import pi
from typing import Any

from iterd.core.errors import IterdError
from iterd.solvers.registry import Metric, SimInput, _number, register_solver
from iterd.solvers.weld import _positive_int


class BoltShearSolver:
    """螺栓组剪切强度求解器（内置确定性示例，非有限元）.

    输入：shear_force(N) / bolt_diameter(mm) / count(4) / planes(1) / allowable_shear(MPa)。
    输出：single_shear_area(mm²) / shear_stress(MPa) / safety_factor(-)。
    """

    solver_type = "bolt_shear"
    description = "螺栓组剪切强度校核（单栓截面剪切法，内置确定性示例求解器）"

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格（均带默认值，作业可不传参直接运行）。"""
        return [
            {"key": "shear_force", "label": "剪切载荷", "unit": "N", "default": 10000, "required": False},
            {"key": "bolt_diameter", "label": "螺栓直径", "unit": "mm", "default": 10, "required": False},
            {"key": "count", "label": "螺栓个数", "unit": "", "default": 4, "required": False},
            {"key": "planes", "label": "剪切面数", "unit": "", "default": 1, "required": False},
            {"key": "allowable_shear", "label": "许用切应力", "unit": "MPa", "default": 80, "required": False},
        ]

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格。"""
        return [
            {"key": "single_shear_area", "label": "单栓截面积", "unit": "mm²"},
            {"key": "shear_stress", "label": "工作切应力", "unit": "MPa"},
            {"key": "safety_factor", "label": "安全系数", "unit": ""},
        ]

    def run(self, sim: SimInput) -> list[Metric]:
        """按螺栓截面剪切求解（A=πd²/4，τ=4F/(n·planes·π·d²)）。"""
        values = {str(item["key"]): _number(sim.inputs, item) for item in self.input_spec()}
        for key, value in values.items():
            if value <= 0:
                raise IterdError(f"求解参数 {key} 必须为正数: {value}", code="ITERD-SOLVER_ERROR", status_code=422)
        count = _positive_int(sim.inputs, {"key": "count", "default": 4})
        planes = _positive_int(sim.inputs, {"key": "planes", "default": 1})

        diameter = values["bolt_diameter"]
        single_area = pi * diameter**2 / 4
        shear_stress = 4 * values["shear_force"] / (count * planes * pi * diameter**2)
        safety_factor = values["allowable_shear"] / shear_stress
        return [
            Metric(key="single_shear_area", value=round(single_area, 4), unit="mm²", label="单栓截面积"),
            Metric(key="shear_stress", value=round(shear_stress, 4), unit="MPa", label="工作切应力"),
            Metric(key="safety_factor", value=round(safety_factor, 4), unit="", label="安全系数"),
        ]


register_solver(BoltShearSolver())
