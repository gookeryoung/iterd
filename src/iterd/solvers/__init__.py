"""求解器包：协议、注册表与内置实现.

内置：beam_static（简支梁弯曲）/ column_buckling（Euler 压杆稳定）/ shaft_torsion（圆轴扭转），
均为确定性解析示例；新增求解器实现子模块并在底部注册即可，平台代码零改动。
"""

from __future__ import annotations

from iterd.solvers.beam import BeamStaticSolver
from iterd.solvers.column import ColumnBucklingSolver
from iterd.solvers.registry import (
    Metric,
    SimInput,
    SolverAdapter,
    default_inputs,
    get_solver,
    register_solver,
    registered_solvers,
    solver_manifest,
)
from iterd.solvers.shaft import ShaftTorsionSolver

__all__ = [
    "BeamStaticSolver",
    "ColumnBucklingSolver",
    "Metric",
    "ShaftTorsionSolver",
    "SimInput",
    "SolverAdapter",
    "default_inputs",
    "get_solver",
    "register_solver",
    "registered_solvers",
    "solver_manifest",
]
