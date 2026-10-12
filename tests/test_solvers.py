"""求解器单元测试：公式精确断言与参数校验."""

from __future__ import annotations

import math

import pytest

from iterd.core.errors import IterdError
from iterd.solvers import SimInput, default_inputs, get_solver, registered_solvers, solver_manifest


def _run(solver_type: str, **inputs: float) -> dict[str, float]:
    """以给定入参运行求解器，返回 {指标: 值}."""
    solver = get_solver(solver_type)
    return {m.key: m.value for m in solver.run(SimInput(job_id=1, inputs=inputs))}


def test_registry_and_manifest() -> None:
    assert set(registered_solvers()) == {
        "beam_static",
        "bolt_shear",
        "column_buckling",
        "gear_tooth_bending",
        "shaft_torsion",
        "weld_fillet_shear",
    }
    manifest = solver_manifest()
    assert {item["solver_type"] for item in manifest} == set(registered_solvers())
    for item in manifest:
        assert item["inputs"] and item["metrics"] and item["description"]


def test_default_inputs() -> None:
    assert default_inputs("shaft_torsion") == {
        "torque": 500,
        "diameter": 40,
        "length": 500,
        "shear_modulus": 79000,
        "allowable_shear": 60,
    }


def test_beam_static_regression() -> None:
    """重构回归：与示例数据集 1 文档基准一致（8000N / 2000mm / 40x80 / Q235）."""
    metrics = _run("beam_static", load=8000, length=2000, width=40, height=80, modulus=206000, yield_strength=235)
    assert metrics["max_stress"] == pytest.approx(93.75, rel=1e-6)
    assert metrics["deflection"] == pytest.approx(3.79, rel=1e-2)
    assert metrics["safety_factor"] == pytest.approx(2.51, rel=1e-2)


def test_column_buckling() -> None:
    inertia = 60 * 60**3 / 12
    expected_pcr = math.pi**2 * 206000 * inertia / 1500**2
    metrics = _run(
        "column_buckling",
        axial_load=50000,
        length=1500,
        width=60,
        height=60,
        modulus=206000,
        effective_length_factor=1.0,
    )
    assert metrics["critical_load"] == round(expected_pcr, 4)
    assert metrics["actual_stress"] == round(50000 / 3600, 4)
    assert metrics["safety_factor"] == round(expected_pcr / 50000, 4)
    # 手算基准：Q235 60x60x1500 两端铰支，Pcr ≈ 975906.48 N
    assert metrics["critical_load"] == pytest.approx(975906.48, rel=1e-6)

    # 手算基准：40x40x4000 细长杆 Pcr ≈ 27108.51 N，P=30kN 时安全系数 < 1
    slender = _run(
        "column_buckling",
        axial_load=30000,
        length=4000,
        width=40,
        height=40,
        modulus=206000,
        effective_length_factor=1.0,
    )
    assert slender["critical_load"] == pytest.approx(27108.51, rel=1e-6)
    assert slender["safety_factor"] == pytest.approx(0.9036, rel=1e-4)

    # 计算长度系数 μ=2（一端固定一端自由）：临界力折减 4 倍
    fixed_free = _run(
        "column_buckling",
        axial_load=30000,
        length=4000,
        width=40,
        height=40,
        modulus=206000,
        effective_length_factor=2.0,
    )
    assert fixed_free["critical_load"] == pytest.approx(slender["critical_load"] / 4, rel=1e-6)

    # 弱轴：矩形截面取两轴惯性矩的较小值
    rect_inertia = min(30 * 90**3, 90 * 30**3) / 12
    rect = _run(
        "column_buckling",
        axial_load=10000,
        length=2000,
        width=30,
        height=90,
        modulus=206000,
        effective_length_factor=1.0,
    )
    assert rect["critical_load"] == round(math.pi**2 * 206000 * rect_inertia / 2000**2, 4)


def test_shaft_torsion() -> None:
    polar_inertia = math.pi * 45**4 / 32
    torque = 800 * 1000  # N·m → N·mm
    expected_tau = 16 * torque / (math.pi * 45**3)
    expected_twist = torque * 500 / (79000 * polar_inertia) * 180 / math.pi
    metrics = _run("shaft_torsion", torque=800, diameter=45, length=500, shear_modulus=79000, allowable_shear=60)
    assert metrics["max_shear_stress"] == round(expected_tau, 4)
    assert metrics["twist_angle"] == round(expected_twist, 6)
    assert metrics["safety_factor"] == round(60 / expected_tau, 4)
    # 手算基准：800 N·m / Φ45 / 500mm，τ ≈ 44.71 MPa、扭转角 ≈ 0.72°
    assert metrics["max_shear_stress"] == pytest.approx(44.7118, abs=1e-3)
    assert metrics["twist_angle"] == pytest.approx(0.7206, abs=1e-3)

    # 扭矩线性放大 1.875 倍（1500 N·m）：应力与扭转角同比放大
    overload = _run("shaft_torsion", torque=1500, diameter=45, length=500, shear_modulus=79000, allowable_shear=60)
    assert overload["max_shear_stress"] == pytest.approx(metrics["max_shear_stress"] * 1.875, rel=1e-4)
    assert overload["twist_angle"] == pytest.approx(metrics["twist_angle"] * 1.875, rel=1e-4)


def test_weld_fillet_shear() -> None:
    metrics = _run(
        "weld_fillet_shear",
        shear_force=10000,
        weld_leg=6,
        weld_length=200,
        sides=1,
        allowable_shear=80,
    )
    # throat=0.7h=4.2mm，A=4.2*200=840mm²，τ=10000/840≈11.9048MPa
    assert metrics["throat_size"] == pytest.approx(4.2, rel=1e-6)
    assert metrics["shear_stress"] == pytest.approx(11.9048, rel=1e-4)
    assert metrics["safety_factor"] == pytest.approx(80 / 11.9048, rel=1e-4)

    # 双侧角焊缝：承载面积翻倍，应力减半
    double = _run("weld_fillet_shear", shear_force=10000, weld_leg=6, weld_length=200, sides=2, allowable_shear=80)
    assert double["shear_stress"] == pytest.approx(metrics["shear_stress"] / 2, rel=1e-6)
    assert double["safety_factor"] == pytest.approx(metrics["safety_factor"] * 2, rel=1e-6)


def test_bolt_shear() -> None:
    metrics = _run("bolt_shear", shear_force=10000, bolt_diameter=10, count=4, planes=1, allowable_shear=80)
    # τ=4F/(n·planes·π·d²)=40000/(400π)≈31.8310MPa
    assert metrics["single_shear_area"] == pytest.approx(25 * math.pi, rel=1e-6)
    assert metrics["shear_stress"] == pytest.approx(31.8310, rel=1e-4)
    assert metrics["safety_factor"] == pytest.approx(80 / 31.8310, rel=1e-4)

    # 双剪切面：应力减半；螺栓数加倍：应力减半
    two_planes = _run("bolt_shear", shear_force=10000, bolt_diameter=10, count=4, planes=2, allowable_shear=80)
    assert two_planes["shear_stress"] == pytest.approx(metrics["shear_stress"] / 2, rel=1e-6)
    eight_bolts = _run("bolt_shear", shear_force=10000, bolt_diameter=10, count=8, planes=1, allowable_shear=80)
    assert eight_bolts["shear_stress"] == pytest.approx(metrics["shear_stress"] / 2, rel=1e-6)


def test_gear_tooth_bending() -> None:
    metrics = _run(
        "gear_tooth_bending",
        tangential_force=2000,
        module=3,
        teeth=24,
        face_width=30,
        allowable_bending=200,
    )
    # Y=0.154−0.912/24=0.116，σ=2000/(30*3*0.116)≈191.5709MPa
    assert metrics["form_factor"] == pytest.approx(0.116, rel=1e-6)
    assert metrics["bending_stress"] == pytest.approx(191.5709, rel=1e-4)
    assert metrics["safety_factor"] == pytest.approx(200 / 191.5709, rel=1e-4)

    # 齿数减小：Y 减小，应力升高
    fewer = _run("gear_tooth_bending", tangential_force=2000, module=3, teeth=12, face_width=30, allowable_bending=200)
    assert fewer["form_factor"] == pytest.approx(0.154 - 0.912 / 12, rel=1e-6)
    assert fewer["bending_stress"] == pytest.approx(2000 / (30 * 3 * (0.154 - 0.912 / 12)), rel=1e-6)


def test_weld_bolt_gear_param_validation() -> None:
    # 角焊缝：侧数非正整数抛错（0 由正数校验拦截，1.5 由整数校验拦截）
    weld = get_solver("weld_fillet_shear")
    for bad_sides in (0, 1.5, "two"):
        with pytest.raises(IterdError) as exc:
            weld.run(SimInput(job_id=1, inputs={"sides": bad_sides}))
        assert exc.value.code == "ITERD-SOLVER_ERROR"

    # 螺栓：个数 / 剪切面数须为不小于 1 的整数
    bolt = get_solver("bolt_shear")
    for key in ("count", "planes"):
        with pytest.raises(IterdError) as exc:
            bolt.run(SimInput(job_id=1, inputs={key: 2.5}))
        assert exc.value.code == "ITERD-SOLVER_ERROR"

    # 齿轮：齿数过小导致齿形系数非正（Y=0.154−0.912/z，z<6 时 Y<0）
    gear = get_solver("gear_tooth_bending")
    with pytest.raises(IterdError) as exc:
        gear.run(SimInput(job_id=1, inputs={"teeth": 4}))
    assert exc.value.code == "ITERD-SOLVER_ERROR"


@pytest.mark.parametrize("solver_type", ["weld_fillet_shear", "bolt_shear", "gear_tooth_bending"])
def test_new_solver_zero_and_text_validation(solver_type: str) -> None:
    spec = get_solver(solver_type).input_spec()[0]
    key = str(spec["key"])
    with pytest.raises(IterdError) as zero:
        get_solver(solver_type).run(SimInput(job_id=1, inputs={key: 0}))
    assert zero.value.code == "ITERD-SOLVER_ERROR"
    with pytest.raises(IterdError) as text:
        get_solver(solver_type).run(SimInput(job_id=1, inputs={key: "abc"}))
    assert text.value.code == "ITERD-SOLVER_ERROR"


@pytest.mark.parametrize("solver_type", ["beam_static", "column_buckling", "shaft_torsion"])
def test_solver_param_validation(solver_type: str) -> None:
    solver = get_solver(solver_type)
    key = str(solver.input_spec()[0]["key"])
    with pytest.raises(IterdError) as zero:
        solver.run(SimInput(job_id=1, inputs={key: 0}))
    assert zero.value.code == "ITERD-SOLVER_ERROR"
    with pytest.raises(IterdError) as text:
        solver.run(SimInput(job_id=1, inputs={key: "abc"}))
    assert text.value.code == "ITERD-SOLVER_ERROR"


def test_get_unknown_solver() -> None:
    with pytest.raises(IterdError) as exc:
        get_solver("no_such_solver")
    assert exc.value.code == "ITERD-SOLVER_ERROR"
