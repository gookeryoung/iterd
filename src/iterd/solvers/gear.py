"""齿轮齿根弯曲求解器."""

from __future__ import annotations

from typing import Any

from iterd.core.errors import IterdError
from iterd.solvers.registry import Metric, SimInput, _number, register_solver
from iterd.solvers.weld import _positive_int


class GearToothBendingSolver:
    """直齿轮齿根弯曲强度求解器（内置确定性示例，非有限元）.

    输入：tangential_force(N) / module(mm) / teeth(24) / face_width(mm) / allowable_bending(MPa)。
    输出：form_factor(-) / bending_stress(MPa) / safety_factor(-)。
    """

    solver_type = "gear_tooth_bending"
    description = "直齿轮齿根弯曲强度校核（Lewis 公式，内置确定性示例求解器）"

    def input_spec(self) -> list[dict[str, Any]]:
        """输入参数规格（均带默认值，作业可不传参直接运行）。"""
        return [
            {"key": "tangential_force", "label": "切向力", "unit": "N", "default": 2000, "required": False},
            {"key": "module", "label": "模数", "unit": "mm", "default": 3, "required": False},
            {"key": "teeth", "label": "齿数", "unit": "", "default": 24, "required": False},
            {"key": "face_width", "label": "齿宽", "unit": "mm", "default": 30, "required": False},
            {"key": "allowable_bending", "label": "许用弯曲应力", "unit": "MPa", "default": 200, "required": False},
        ]

    def metric_spec(self) -> list[dict[str, str]]:
        """输出指标规格。"""
        return [
            {"key": "form_factor", "label": "齿形系数", "unit": ""},
            {"key": "bending_stress", "label": "齿根弯曲应力", "unit": "MPa"},
            {"key": "safety_factor", "label": "安全系数", "unit": ""},
        ]

    def run(self, sim: SimInput) -> list[Metric]:
        """按 Lewis 公式求解（Y=0.154−0.912/z，σ=F/(b·m·Y)）。"""
        values = {str(item["key"]): _number(sim.inputs, item) for item in self.input_spec()}
        for key, value in values.items():
            if value <= 0:
                raise IterdError(f"求解参数 {key} 必须为正数: {value}", code="ITERD-SOLVER_ERROR", status_code=422)
        teeth = _positive_int(sim.inputs, {"key": "teeth", "default": 24})

        form_factor = 0.154 - 0.912 / teeth
        if form_factor <= 0:
            raise IterdError(
                f"齿数过小导致齿形系数非正（z={teeth}），须 z ≥ 6",
                code="ITERD-SOLVER_ERROR",
                status_code=422,
            )
        bending_stress = values["tangential_force"] / (values["face_width"] * values["module"] * form_factor)
        safety_factor = values["allowable_bending"] / bending_stress
        return [
            Metric(key="form_factor", value=round(form_factor, 4), unit="", label="齿形系数"),
            Metric(key="bending_stress", value=round(bending_stress, 4), unit="MPa", label="齿根弯曲应力"),
            Metric(key="safety_factor", value=round(safety_factor, 4), unit="", label="安全系数"),
        ]


register_solver(GearToothBendingSolver())
