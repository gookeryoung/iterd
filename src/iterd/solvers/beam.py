"""简支梁三点弯曲静力求解器."""

from __future__ import annotations

from typing import Any

from iterd.core.errors import IterdError
from iterd.solvers.registry import Metric, SimInput, _number, register_solver


class BeamStaticSolver:
    """简支梁三点弯曲静力近似求解器（内置确定性示例，非有限元）.

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


register_solver(BeamStaticSolver())
