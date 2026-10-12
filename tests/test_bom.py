"""BOM 与跨产物检查端到端测试：CSV 导入（幂等/权限/校验）→ context 检查器 → 流水线分流 → 报告."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

BOM_CSV = (
    "序号,零件编码,零件名称,材料,规格,数量,单件重量kg,备注\n"
    "1,PT-01,纵梁,Q235B,120x120x6,4,10.0,一致\n"
    "2,PT-02,横梁,Q235B,80x40x5,12,18.0,重量冲突\n"
    "3,PT-09,螺栓,8.8级,M16,96,1.0,缺件\n"
    "4,PT-03,支腿,Q235B,100x100x5,6,5.0,一致\n"
).encode()


@pytest.fixture()
def scenario(client: TestClient) -> dict[str, Any]:
    """项目 + 激活迭代 + 四个产物（覆盖 / 冲突 / 缺件 / 未覆盖四类边界）."""
    project = client.post("/api/v1/projects", json={"code": "BOMPR", "name": "BOM 项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    arts: dict[str, Any] = {}
    specs = {
        "DRW-A": ("drawing", '{"part_code": "PT-01", "重量kg": 10.0}'),
        "MOD-A": ("model", '{"part_code": "PT-02", "重量kg": 20.0}'),
        "CAL-A": ("result", '{"covers": "DRW-A,MOD-A"}'),
        "DRW-B": ("drawing", '{"part_code": "PT-03", "重量kg": 5.0}'),
    }
    for code, (category, metadata) in specs.items():
        art = client.post(
            f"/api/v1/artifacts?iteration_id={iteration['id']}",
            json={"code": code, "name": code, "category": category},
        ).json()
        client.post(
            f"/api/v1/artifacts/{art['id']}/versions",
            files={"file": (f"{code}_revA.dxf", b"x")},
            data={"metadata": metadata},
        )
        arts[code] = art
    return {"project": project, "iteration": iteration, "arts": arts}


def _import_bom(client: TestClient, scenario: dict[str, Any], content: bytes = BOM_CSV) -> Any:
    return client.post(
        "/api/v1/bom/import",
        params={"project_id": scenario["project"]["id"], "iteration_id": scenario["iteration"]["id"]},
        files={"file": ("bom.csv", content, "text/csv")},
    )


def test_bom_import_idempotent_and_list(client: TestClient, scenario: dict[str, Any]) -> None:
    """CSV 导入：created/updated 计数正确；重复导入按零件编码 upsert 不产生重复行."""
    it_id = scenario["iteration"]["id"]
    first = _import_bom(client, scenario)
    assert first.status_code == 201, first.text
    assert first.json() == {"created": 4, "updated": 0, "total": 4}

    second = _import_bom(client, scenario)
    assert second.status_code == 201
    assert second.json() == {"created": 0, "updated": 4, "total": 4}

    rows = client.get("/api/v1/bom", params={"iteration_id": it_id}).json()
    assert len(rows) == 4
    by_code = {r["part_code"]: r for r in rows}
    assert by_code["PT-01"]["part_name"] == "纵梁"
    assert by_code["PT-02"]["unit_weight"] == 18.0
    assert by_code["PT-09"]["quantity"] == 96
    assert by_code["PT-01"]["project_id"] == scenario["project"]["id"]

    # 数量缺省 1、重量缺省 None
    minimal = client.post(
        "/api/v1/bom/import",
        params={"project_id": scenario["project"]["id"], "iteration_id": it_id},
        files={"file": ("mini.csv", "零件编码,零件名称\nPT-X,垫片\n".encode(), "text/csv")},
    )
    assert minimal.status_code == 201
    rows = client.get("/api/v1/bom", params={"iteration_id": it_id}).json()
    extra = next(r for r in rows if r["part_code"] == "PT-X")
    assert extra["quantity"] == 1 and extra["unit_weight"] is None


def test_bom_import_validation(client: TestClient, scenario: dict[str, Any]) -> None:
    """CSV 校验：缺必需列 / 数量非法 / 迭代与项目不匹配均被 4xx 拦截."""
    base = {"project_id": scenario["project"]["id"], "iteration_id": scenario["iteration"]["id"]}
    missing_col = client.post(
        "/api/v1/bom/import",
        params=base,
        files={"file": ("bad.csv", "零件编码,材料\nPT-1,Q235\n".encode(), "text/csv")},
    )
    assert missing_col.status_code == 422
    bad_qty = client.post(
        "/api/v1/bom/import",
        params=base,
        files={"file": ("bad.csv", "零件编码,零件名称,数量\nPT-1,垫片,零\n".encode(), "text/csv")},
    )
    assert bad_qty.status_code == 422
    empty = client.post("/api/v1/bom/import", params=base, files={"file": ("empty.csv", b"", "text/csv")})
    assert empty.status_code == 422
    mismatch = client.post(
        "/api/v1/bom/import",
        params={"project_id": 99999, "iteration_id": scenario["iteration"]["id"]},
        files={"file": ("bom.csv", BOM_CSV, "text/csv")},
    )
    assert mismatch.status_code == 404


def test_bom_import_permission(client: TestClient, scenario: dict[str, Any]) -> None:
    """权限：项目外用户导入被拒；读取端点须带定位参数."""
    from tests.conftest import login_as

    client.post("/api/v1/users", json={"username": "outsider", "password": "outsider123"})
    login_as(client, "outsider", "outsider123")
    resp = _import_bom(client, scenario)
    assert resp.status_code == 403
    assert client.get("/api/v1/bom").status_code == 403
    login_as(client, "admin", "admin1234")
    assert client.get("/api/v1/bom", params={"project_id": scenario["project"]["id"]}).status_code == 200


def test_context_checkers_dispatch_and_findings(client: TestClient, scenario: dict[str, Any]) -> None:
    """context 检查器经流水线 rules/check 分流：整迭代执行一次，迭代级发现项无产物关联."""
    _import_bom(client, scenario)
    bom_rule = client.post(
        "/api/v1/rules",
        json={
            "code": "BOM-T",
            "name": "BOM 一致性",
            "category": "material",
            "checker_type": "bom_consistency",
            "params": {"weight_tolerance_pct": 5},
            "severity_default": "error",
        },
    ).json()
    cmp_rule = client.post(
        "/api/v1/rules",
        json={
            "code": "CMP-T",
            "name": "计算书覆盖度",
            "category": "process",
            "checker_type": "iteration_completeness",
            "params": {"calc_category": "result", "covered_categories": ["drawing", "model"]},
            "severity_default": "warning",
        },
    ).json()
    rule_set = client.post(
        "/api/v1/rule-sets",
        json={
            "name": "BOM 集",
            "project_id": scenario["project"]["id"],
            "rule_ids": [bom_rule["id"], cmp_rule["id"]],
        },
    ).json()

    workflow = client.post(
        "/api/v1/workflows",
        json={
            "code": "BOMPR-REVIEW",
            "name": "BOM 审查",
            "project_id": scenario["project"]["id"],
            "definition": f"name: BOM 审查\njobs:\n  check:\n    uses: rules/check\n    with: {{rule_set: {rule_set['id']}}}\n",
        },
    ).json()
    created = client.post(
        f"/api/v1/iterations/{scenario['iteration']['id']}/workflow-runs", json={"workflow_id": workflow["id"]}
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    final: dict[str, Any] = {}
    for _ in range(50):
        final = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if final["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)
    assert final["status"] == "failed", final  # error 级发现项 2 条 → 流水线失败

    check_run_id = next(j["check_run_id"] for j in final["jobs"] if j["job_type"] == "rules")
    state = client.get(f"/api/v1/check-runs/{check_run_id}").json()
    assert state["status"] == "succeeded"
    assert state["summary"] == {"error": 2, "warning": 1, "info": 0, "artifacts": 4, "rules": 2}

    findings = client.get(f"/api/v1/check-runs/{check_run_id}/findings").json()
    by_key = {(f["rule_code"], f["location"]): f for f in findings}
    conflict = by_key[("BOM-T", "bom:PT-02")]
    assert conflict["severity"] == "error"
    assert conflict["artifact_code"] == "MOD-A"
    assert "偏差 10.0% 超过容忍 5%" in conflict["message"]
    missing = by_key[("BOM-T", "bom:PT-09")]
    assert missing["artifact_code"] is None  # 迭代级发现项：缺件无产物版本关联
    assert "无对应产物" in missing["message"]
    uncovered = by_key[("CMP-T", "DRW-B")]
    assert uncovered["severity"] == "warning"
    assert uncovered["artifact_code"] == "DRW-B"
    assert "无 result 类计算书覆盖" in uncovered["message"]
    # 一致零件（PT-01 / PT-03）与被覆盖产物（DRW-A / MOD-A）不产生发现项
    assert len(findings) == 3


def test_bom_consistency_checker_units() -> None:
    """bom_consistency 单元边界：空 BOM 不报、covers 列表形态、元数据缺重量跳过比对."""
    from iterd.checkers import BomConsistencyChecker, BomItemRef, CheckContext, RuleRef

    def _art(code: str, metadata: dict[str, Any]) -> Any:
        from iterd.checkers import ArtifactRef

        return ArtifactRef(
            artifact_id=1,
            artifact_code=code,
            artifact_name=code,
            version_id=10,
            version_no=1,
            filename=f"{code}.dxf",
            metadata=metadata,
            category="drawing",
        )

    rule = RuleRef(rule_id=1, code="BOM", name="BOM", params={"weight_tolerance_pct": 5}, severity="error")
    checker = BomConsistencyChecker()

    empty = CheckContext(project_id=1, iteration_id=1, iteration_no=1, iteration_title="t", artifacts=[], bom_items=[])
    assert checker.check(empty, [rule]) == []

    artifacts = [
        _art("DRW-A", {"part_code": "PT-01", "重量kg": 10.0}),
        _art("DRW-N", {"part_code": "PT-02"}),  # 无重量元数据 → 跳过比对
    ]
    bom_items = [
        BomItemRef(part_code="PT-01", part_name="纵梁", material="", spec="", quantity=1, unit_weight=10.0, note=""),
        BomItemRef(part_code="PT-02", part_name="横梁", material="", spec="", quantity=1, unit_weight=9.0, note=""),
    ]
    context = CheckContext(
        project_id=1, iteration_id=1, iteration_no=1, iteration_title="t", artifacts=artifacts, bom_items=bom_items
    )
    assert checker.check(context, [rule]) == []


def test_iteration_completeness_checker_units() -> None:
    """iteration_completeness 单元边界：covers 列表 / 字符串两种形态与空产物集."""
    from iterd.checkers import ArtifactRef, CheckContext, IterationCompletenessChecker, RuleRef

    rule = RuleRef(rule_id=1, code="CMP", name="CMP", params={}, severity="warning")
    checker = IterationCompletenessChecker()

    def _ctx(covers: Any) -> CheckContext:
        return CheckContext(
            project_id=1,
            iteration_id=1,
            iteration_no=1,
            iteration_title="t",
            artifacts=[
                ArtifactRef(
                    artifact_id=1,
                    artifact_code="CAL-A",
                    artifact_name="CAL-A",
                    version_id=10,
                    version_no=1,
                    filename="CAL-A.csv",
                    metadata={"covers": covers},
                    category="result",
                ),
                ArtifactRef(
                    artifact_id=2,
                    artifact_code="DRW-A",
                    artifact_name="DRW-A",
                    version_id=11,
                    version_no=1,
                    filename="DRW-A.dxf",
                    metadata={},
                    category="drawing",
                ),
            ],
            bom_items=[],
        )

    assert checker.check(_ctx(["DRW-A"]), [rule]) == []
    assert checker.check(_ctx("DRW-A"), [rule]) == []
    uncovered = checker.check(_ctx(None), [rule])
    assert len(uncovered) == 1
    assert uncovered[0].location == "DRW-A"
    assert uncovered[0].artifact_version_id == 11
    # 空产物集不产生发现项
    assert (
        checker.check(
            CheckContext(project_id=1, iteration_id=1, iteration_no=1, iteration_title="t", artifacts=[], bom_items=[]),
            [rule],
        )
        == []
    )
