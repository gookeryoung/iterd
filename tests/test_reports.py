"""reports 端到端测试：迭代对比 diff → 审查报告生成 → 归档为 result 产物.

覆盖 AC-1（结构化差异三段齐全）/ AC-2（报告四段 + 归档进文档库）/
AC-3（无基线明确语义 + 显式/非法基线）/ 权限边界。
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

_RULES_DEF = """\
name: 基线检查
jobs:
  check:
    uses: rules/check
    with: {{rule_set: {rule_set}}}
"""

_FULL_DEF = """\
name: 会签与仿真审查
jobs:
  check:
    uses: rules/check
    with: {{rule_set: {rule_set}}}
  sign-off:
    needs: check
    uses: approval/request
    with:
      approvers: [admin]
      min_count: 1
  sim:
    needs: sign-off
    uses: simulation/run
    with:
      template: {template}
      artifact: FRM-2
"""


def _make_artifact(  # noqa: PLR0913, PLR0917 - 造数参数
    client: TestClient, it_id: int, code: str, category: str, metadata: str, name: str | None = None
) -> Any:
    resp = client.post(
        f"/api/v1/artifacts?iteration_id={it_id}",
        json={"code": code, "name": name or code, "category": category},
    )
    assert resp.status_code == 201, resp.text
    art = resp.json()
    uploaded = client.post(
        f"/api/v1/artifacts/{art['id']}/versions",
        files={"file": (f"{code}_revA.dxf", b"x")},
        data={"metadata": metadata},
    )
    assert uploaded.status_code == 201, uploaded.text
    return art


def _wait_run(client: TestClient, run_id: int) -> dict[str, Any]:
    run: dict[str, Any] = {}
    for _ in range(50):
        run = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed"):
            return run
        time.sleep(0.2)
    return run


@pytest.fixture()
def prepared(client: TestClient) -> dict[str, Any]:
    """项目 + 两轮迭代（基线已关闭含 1 个 error）+ 规则库/规则集/仿真模板."""
    project = client.post("/api/v1/projects", json={"code": "REP", "name": "报告项目"}).json()
    rule = client.post(
        "/api/v1/rules",
        json={
            "code": "REP-MD",
            "name": "材料必填",
            "category": "material",
            "checker_type": "metadata_required",
            "params": {"required": {"材料": "str"}},
            "severity_default": "error",
        },
    ).json()
    rule_set = client.post(
        "/api/v1/rule-sets", json={"name": "报告集", "project_id": project["id"], "rule_ids": [rule["id"]]}
    ).json()
    client.post(
        "/api/v1/sim-templates",
        json={
            "code": "REP-BEAM",
            "name": "横梁静强度",
            "solver_type": "beam_static",
            "project_id": project["id"],
            "thresholds": {"max_stress": {"max": 100}},
        },
    )

    # 迭代 1（基线）：A-1 合规、B-1 缺材料（error 1）
    it1 = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "方案评审"}).json()
    client.patch(f"/api/v1/iterations/{it1['id']}", json={"title": "方案评审", "status": "active"})
    _make_artifact(client, it1["id"], "A-1", "drawing", '{"材料": "Q235"}', name="件A")
    _make_artifact(client, it1["id"], "B-1", "drawing", "{}", name="件B")
    client.post(
        "/api/v1/bom/import",
        params={"project_id": project["id"], "iteration_id": it1["id"]},
        files={"file": ("bom1.csv", "零件编码,零件名称,单件重量kg\nPT-01,纵梁,10\n".encode(), "text/csv")},
    )
    wf1 = client.post(
        "/api/v1/workflows",
        json={
            "code": "REP-BASE",
            "name": "基线检查",
            "project_id": project["id"],
            "definition": _RULES_DEF.format(rule_set=rule_set["id"]),
        },
    ).json()
    run1 = client.post(f"/api/v1/iterations/{it1['id']}/workflow-runs", json={"workflow_id": wf1["id"]}).json()
    assert _wait_run(client, run1["id"])["status"] == "failed"  # 含 error 发现项
    client.patch(f"/api/v1/iterations/{it1['id']}", json={"title": "方案评审", "status": "closed"})

    # 迭代 2（当前）：全新编码产物集（平台产物编码项目内唯一，跨迭代体现为增删）；BOM 数量变更+新增
    it2 = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "详细设计"}).json()
    client.patch(f"/api/v1/iterations/{it2['id']}", json={"title": "详细设计", "status": "active"})
    _make_artifact(client, it2["id"], "A-2", "drawing", '{"材料": "Q345"}', name="件A二代")
    _make_artifact(client, it2["id"], "C-2", "drawing", '{"材料": "Q235"}', name="件C")
    _make_artifact(client, it2["id"], "FRM-2", "model", '{"材料": "Q235"}', name="横梁模型")
    client.post(
        "/api/v1/bom/import",
        params={"project_id": project["id"], "iteration_id": it2["id"]},
        files={
            "file": ("bom2.csv", "零件编码,零件名称,单件重量kg\nPT-01,纵梁,12\nPT-02,横梁,18\n".encode(), "text/csv")
        },
    )
    wf2 = client.post(
        "/api/v1/workflows",
        json={
            "code": "REP-FULL",
            "name": "会签与仿真审查",
            "project_id": project["id"],
            "definition": _FULL_DEF.format(rule_set=rule_set["id"], template="REP-BEAM"),
        },
    ).json()
    run2 = client.post(f"/api/v1/iterations/{it2['id']}/workflow-runs", json={"workflow_id": wf2["id"]}).json()
    waiting = _wait_run(client, run2["id"])
    if waiting["status"] == "waiting":
        sign = next(j for j in waiting["jobs"] if j["job_key"] == "sign-off")
        signed = client.post(
            f"/api/v1/workflow-jobs/{sign['id']}/approvals", json={"decision": "approved", "comment": "同意放行"}
        )
        assert signed.status_code == 201, signed.text
    final = _wait_run(client, run2["id"])
    assert final["status"] == "succeeded", final
    return {"project": project, "it1": it1, "it2": it2}


def test_diff_structure_and_semantics(client: TestClient, prepared: dict[str, Any]) -> None:
    """AC-1：产物增删/字段级变更、BOM 差异、结论计数、仿真与审批摘要齐全."""
    diff = client.get(f"/api/v1/iterations/{prepared['it2']['id']}/diff").json()
    assert diff["baseline"]["id"] == prepared["it1"]["id"]  # 自动基线：前序 closed 迭代
    arts = diff["artifacts"]
    assert {a["code"] for a in arts["added"]} == {"A-2", "C-2", "FRM-2"}
    assert {a["code"] for a in arts["removed"]} == {"A-1", "B-1"}
    assert arts["changed"] == []  # 产物编码项目内唯一，跨迭代不会出现同码字段变更

    bom = diff["bom"]
    assert [b["part_code"] for b in bom["added"]] == ["PT-02"]
    weight = next(c for c in bom["changed"] if c["part_code"] == "PT-01")
    assert weight["field"] == "unit_weight" and weight["base"] == 10 and weight["current"] == 12

    assert diff["findings"]["baseline"] == {"error": 1, "warning": 0, "info": 0}
    assert diff["findings"]["current"] == {"error": 0, "warning": 0, "info": 0}
    assert diff["sims"]["baseline"] is None
    assert diff["sims"]["current"] == {"verdict": "pass", "failures": 0}
    assert diff["approvals"]["baseline"] is None  # 基线运行含 error 无审批作业
    assert diff["approvals"]["current"] == {"approved": 1, "rejected": 0, "pending_jobs": 0}


def test_diff_explicit_baseline_and_validation(client: TestClient, prepared: dict[str, Any]) -> None:
    """AC-3：显式基线生效；自引用与跨项目基线 422."""
    it1, it2 = prepared["it1"]["id"], prepared["it2"]["id"]
    explicit = client.get(f"/api/v1/iterations/{it2}/diff", params={"baseline": it1})
    assert explicit.status_code == 200
    assert explicit.json()["baseline"]["id"] == it1

    self_ref = client.get(f"/api/v1/iterations/{it2}/diff", params={"baseline": it2})
    assert self_ref.status_code == 422 and self_ref.json()["code"] == "ITERD-BASELINE_INVALID"

    other = client.post("/api/v1/projects", json={"code": "REP2", "name": "另一项目"}).json()
    other_it = client.post(f"/api/v1/projects/{other['id']}/iterations", json={"title": "外部"}).json()
    cross = client.get(f"/api/v1/iterations/{it2}/diff", params={"baseline": other_it["id"]})
    assert cross.status_code == 422 and cross.json()["code"] == "ITERD-BASELINE_INVALID"


def test_diff_without_baseline_semantics(client: TestClient) -> None:
    """AC-3：无前序 closed 迭代时 baseline 为 null 且带明确提示."""
    project = client.post("/api/v1/projects", json={"code": "NB", "name": "无基线项目"}).json()
    it = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "首轮"}).json()
    _make_artifact(client, it["id"], "X-1", "drawing", '{"材料": "Q235"}')
    diff = client.get(f"/api/v1/iterations/{it['id']}/diff").json()
    assert diff["baseline"] is None and "无可用基线" in diff["note"]
    assert diff["findings"]["current"] is None and diff["sims"]["current"] is None
    assert diff["approvals"]["current"] is None
    assert len(diff["artifacts"]["added"]) == 1


def test_report_markdown_sections(client: TestClient, prepared: dict[str, Any]) -> None:
    """AC-2：报告含四段内容与关键明细行."""
    report = client.get(f"/api/v1/iterations/{prepared['it2']['id']}/report").json()
    md = report["markdown"]
    for heading in ("## 一、检查汇总", "## 二、发现明细", "## 三、仿真指标判定", "## 四、审批记录"):
        assert heading in md
    assert "最大弯曲应力" in md and "MPa" in md  # 仿真判定表
    assert "admin | 通过 | 同意放行" in md  # 审批记录
    assert "（无发现项）" in md  # 迭代 2 检查全合规

    baseline_report = client.get(f"/api/v1/iterations/{prepared['it1']['id']}/report").json()
    base_md = baseline_report["markdown"]
    assert "REP-MD 材料必填" in base_md  # 发现明细行（B-1 缺材料 error）
    assert "无审批记录" in base_md
    assert "（无仿真作业）" in base_md


def test_report_archive_into_doc_library(client: TestClient, prepared: dict[str, Any]) -> None:
    """AC-2：归档为 result 产物进文档库；重复归档追加新版本."""
    it2 = prepared["it2"]["id"]
    first = client.post(f"/api/v1/iterations/{it2}/report/archive")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["artifact_code"] == "RPT-IT2" and body["version_no"] == 1

    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert detail["category"] == "result" and detail["iteration_id"] == it2

    again = client.post(f"/api/v1/iterations/{it2}/report/archive")
    assert again.status_code == 201 and again.json()["version_no"] == 2

    # 文档库可检索（项目产物列表含报告）
    listing = client.get("/api/v1/artifacts", params={"project_id": prepared["project"]["id"]}).json()
    assert any(a["code"] == "RPT-IT2" for a in listing)


def test_reports_permissions(client: TestClient, prepared: dict[str, Any]) -> None:
    """权限边界：viewer 可读 diff/报告但不可归档；无角色 outsider 全被拒."""
    from tests.conftest import login_as as switch

    client.post("/api/v1/users", json={"username": "viewer", "password": "viewer1234"})
    project_id = prepared["project"]["id"]
    joined = client.put(
        f"/api/v1/projects/{project_id}/members", json={"user_id": _user_id(client, "viewer"), "role": "viewer"}
    )
    assert joined.status_code == 201, joined.text
    it2 = prepared["it2"]["id"]

    switch(client, "viewer", "viewer1234")
    assert client.get(f"/api/v1/iterations/{it2}/diff").status_code == 200
    assert client.get(f"/api/v1/iterations/{it2}/report").status_code == 200
    assert client.post(f"/api/v1/iterations/{it2}/report/archive").status_code == 403

    switch(client, "admin", "admin1234")
    client.post("/api/v1/users", json={"username": "outsider", "password": "outsider123"})
    switch(client, "outsider", "outsider123")
    assert client.get(f"/api/v1/iterations/{it2}/diff").status_code == 403
    assert client.get(f"/api/v1/iterations/{it2}/report").status_code == 403
    assert client.post(f"/api/v1/iterations/{it2}/report/archive").status_code == 403


def _user_id(client: TestClient, username: str) -> int:
    return int(next(u for u in client.get("/api/v1/users").json() if u["username"] == username)["id"])
