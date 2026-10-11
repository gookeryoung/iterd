"""实心圆轴扭转求解器."""

from __future__ import annotations

from math import pi
from typing import Any

from iterd.core.errors import IterdError
from iterd.solvers.registry import Metric, SimInput, _number, register_solver


class ShaftTorsionSolver:
    """实心圆轴扭转求解器（内置确定性示例，非有限元）.

    输入：torque(N·m) / diameter(mm) / length(mm) / shear_modulus(MPa) / allowable_shear(MPa)。
    输出：max_shear_stress(MPa) / twist_angle(°) / safety_factor(-)。
    """

    solver_type = "shaft_torsion"
    description = "实心圆轴扭转强度与刚度校核（内置确定性示例求解器）"

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格（均带默认值，作业可不传参直接运行）。"""
        return [
            {"key": "torque", "label": "传递扭矩", "unit": "N·m", "default": 500, "required": False},
            {"key": "diameter", "label": "轴径", "unit": "mm", "default": 40, "required": False},
            {"key": "length", "label": "轴长", "unit": "mm", "default": 500, "required": False},
            {"key": "shear_modulus", "label": "切变模量", "unit": "MPa", "default": 79000, "required": False},
            {"key": "allowable_shear", "label": "许用切应力", "unit": "MPa", "default": 60, "required": False},
        ]

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格。"""
        return [
            {"key": "max_shear_stress", "label": "最大切应力", "unit": "MPa"},
            {"key": "twist_angle", "label": "扭转角", "unit": "°"},
            {"key": "safety_factor", "label": "安全系数", "unit": ""},
        ]

    def run(self, sim: SimInput) -> list[Metric]:
        """按圆轴扭转公式求解（J=πd⁴/32，τ=16T/(πd³)，φ=TL/(GJ)）。"""
        values = {str(item["key"]): _number(sim.inputs, item) for item in self.input_spec()}
        for key, value in values.items():
            if value <= 0:
                raise IterdError(f"求解参数 {key} 必须为正数: {value}", code="ITERD-SOLVER_ERROR", status_code=422)

        torque = values["torque"] * 1000  # N·m → N·mm
        diameter = values["diameter"]
        length = values["length"]
        shear_modulus = values["shear_modulus"]
        allowable_shear = values["allowable_shear"]
        polar_inertia = pi * diameter**4 / 32
        max_shear_stress = 16 * torque / (pi * diameter**3)
        twist_angle = torque * length / (shear_modulus * polar_inertia) * 180 / pi
        safety_factor = allowable_shear / max_shear_stress
        return [
            Metric(key="max_shear_stress", value=round(max_shear_stress, 4), unit="MPa", label="最大切应力"),
            Metric(key="twist_angle", value=round(twist_angle, 6), unit="°", label="扭转角"),
            Metric(key="safety_factor", value=round(safety_factor, 4), unit="", label="安全系数"),
        ]


register_solver(ShaftTorsionSolver())
