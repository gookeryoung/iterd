"""Euler 压杆稳定性求解器."""

from __future__ import annotations

from math import pi
from typing import Any

from iterd.core.errors import IterdError
from iterd.solvers.registry import Metric, SimInput, _number, register_solver


class ColumnBucklingSolver:
    """Euler 压杆稳定性求解器（内置确定性示例，非有限元）.

    输入：axial_load(N) / length(mm) / width(mm) / height(mm) / modulus(MPa) /
    effective_length_factor(-，1.0 两端铰支、2.0 一端固定一端自由)。
    输出：critical_load(N) / actual_stress(MPa) / safety_factor(-)。
    """

    solver_type = "column_buckling"
    description = "Euler 压杆稳定性近似（弱轴临界力，内置确定性示例求解器）"

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格（均带默认值，作业可不传参直接运行）。"""
        return [
            {"key": "axial_load", "label": "轴向压力", "unit": "N", "default": 10000, "required": False},
            {"key": "length", "label": "杆长", "unit": "mm", "default": 1500, "required": False},
            {"key": "width", "label": "截面宽", "unit": "mm", "default": 60, "required": False},
            {"key": "height", "label": "截面高", "unit": "mm", "default": 60, "required": False},
            {"key": "modulus", "label": "弹性模量", "unit": "MPa", "default": 206000, "required": False},
            {"key": "effective_length_factor", "label": "计算长度系数", "unit": "", "default": 1.0, "required": False},
        ]

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格。"""
        return [
            {"key": "critical_load", "label": "临界压力", "unit": "N"},
            {"key": "actual_stress", "label": "实际压应力", "unit": "MPa"},
            {"key": "safety_factor", "label": "稳定安全系数", "unit": ""},
        ]

    def run(self, sim: SimInput) -> list[Metric]:
        """按 Euler 公式求解（弱轴惯性矩 I=min(b·h³, h·b³)/12，Pcr=π²EI/(μL)²）。"""
        values = {str(item["key"]): _number(sim.inputs, item) for item in self.input_spec()}
        for key, value in values.items():
            if value <= 0:
                raise IterdError(f"求解参数 {key} 必须为正数: {value}", code="ITERD-SOLVER_ERROR", status_code=422)

        axial_load = values["axial_load"]
        length = values["length"]
        width = values["width"]
        height = values["height"]
        modulus = values["modulus"]
        factor = values["effective_length_factor"]
        inertia = min(width * height**3, height * width**3) / 12
        critical_load = pi**2 * modulus * inertia / (factor * length) ** 2
        actual_stress = axial_load / (width * height)
        safety_factor = critical_load / axial_load
        return [
            Metric(key="critical_load", value=round(critical_load, 4), unit="N", label="临界压力"),
            Metric(key="actual_stress", value=round(actual_stress, 4), unit="MPa", label="实际压应力"),
            Metric(key="safety_factor", value=round(safety_factor, 4), unit="", label="稳定安全系数"),
        ]


register_solver(ColumnBucklingSolver())
