"""rules 端到端测试：规则库 → 规则集 → 流水线规则检查作业 → 报告 → 溯源 → 审计.

规则检查的唯一触发入口是审查流水线（rules/check 作业），本文件经
workflow-run 触达检查执行链路；findings / check-runs 读端点直接断言。
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def scenario(client: TestClient) -> dict[str, object]:
    """项目 + 激活迭代 + 两个产物（一个合规、一个违规）。"""
    project = client.post("/api/v1/projects", json={"code": "PR", "name": "规则项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    ok_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "OK-1", "name": "合规件", "category": "drawing"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{ok_art['id']}/versions",
        files={"file": ("OK-1_revA.dwg", b"ok")},
        data={"metadata": '{"材料": "Q235", "尺寸": "10", "公差": "±0.1"}'},
    )
    bad_art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "BAD-1", "name": "违规件", "category": "drawing"},
    ).json()
    client.post(
        f"/api/v1/artifacts/{bad_art['id']}/versions", files={"file": ("badname.dwg", b"bad")}, data={"metadata": "{}"}
    )
    return {"project": project, "iteration": iteration, "ok": ok_art, "bad": bad_art}


def _prepare_rules(client: TestClient, scenario: dict[str, Any]) -> int:
    r1 = client.post(
        "/api/v1/rules",
        json={
            "code": "FN-1",
            "name": "文件名规范",
            "category": "drafting",
            "checker_type": "filename_convention",
            "params": {"pattern": r"^[A-Z0-9-]+_rev[A-Z]\."},
            "severity_default": "error",
        },
    ).json()
    r2 = client.post(
        "/api/v1/rules",
        json={
            "code": "MD-1",
            "name": "材料必填",
            "category": "material",
            "checker_type": "metadata_required",
            "params": {"required": {"材料": "str", "尺寸": "str", "公差": "str"}},
            "severity_default": "error",
        },
    ).json()
    rule_set = client.post(
        "/api/v1/rule-sets",
        json={"name": "默认集", "project_id": scenario["project"]["id"], "rule_ids": [r1["id"], r2["id"]]},
    ).json()
    return rule_set["id"]


def _run_check_workflow(client: TestClient, scenario: dict[str, Any], rule_set_id: int) -> dict[str, Any]:
    """创建单 rules 作业审查模板并发起运行，轮询至终态返回运行详情。"""
    workflow = client.post(
        "/api/v1/workflows",
        json={
            "code": "PR-REVIEW",
            "name": "规则审查",
            "project_id": scenario["project"]["id"],
            "definition": f"name: 规则审查\njobs:\n  check:\n    uses: rules/check\n    with: {{rule_set: {rule_set_id}}}\n",
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
            return final
        time.sleep(0.2)
    return final


def test_full_check_flow(client: TestClient, scenario: dict[str, Any]) -> None:
    rule_set_id = _prepare_rules(client, scenario)
    it_id = scenario["iteration"]["id"]

    final = _run_check_workflow(client, scenario, rule_set_id)
    assert final["status"] == "failed", final  # 违规件 error>0 → 流水线失败
    assert final["summary"]["findings"]["error"] == 2
    check_run_id = next(j["check_run_id"] for j in final["jobs"] if j["job_type"] == "rules")

    state = client.get(f"/api/v1/check-runs/{check_run_id}").json()
    assert state["status"] == "succeeded"
    assert state["summary"]["error"] == 2  # 违规件：文件名 + 材料必填
    assert state["summary"]["artifacts"] == 2

    findings = client.get(f"/api/v1/check-runs/{check_run_id}/findings").json()
    assert len(findings) == 2
    by_severity = client.get(f"/api/v1/check-runs/{check_run_id}/findings", params={"severity": "error"}).json()
    assert len(by_severity) == 2
    none = client.get(f"/api/v1/check-runs/{check_run_id}/findings", params={"severity": "info"}).json()
    assert none == []

    runs = client.get(f"/api/v1/iterations/{it_id}/check-runs").json()
    assert len(runs) == 1

    # 任务记录可查（流水线运行任务）
    task_id = final["task_id"]
    task_detail = client.get(f"/api/v1/tasks/{task_id}")
    assert task_detail.status_code == 200
    assert task_detail.json()["status"] == "succeeded"
    missing_task = client.get("/api/v1/tasks/99999")
    assert missing_task.status_code == 404

    # WebSocket 推送终态：连接后先发送 JWT 首帧鉴权（任务已完成时首条即终态）
    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin1234"}).json()[
        "access_token"
    ]
    with client.websocket_connect(f"/api/v1/ws/tasks/{task_id}") as ws:
        ws.send_json({"token": token})
        message = ws.receive_json()
        assert message["status"] in ("running", "succeeded")

    # 未鉴权连接被拒（1008）
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/api/v1/ws/tasks/{task_id}") as unauth:
        unauth.receive_json()

    # 溯源图：产物版本向下可查到 check_finding 节点
    version_id = client.get(f"/api/v1/artifacts/{scenario['bad']['id']}/versions").json()[0]["id"]
    import asyncio

    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.trace.models import TraceNode

    async def _get_urn() -> str | None:
        factory = get_session_factory(get_engine(get_settings().database_url))
        async with factory() as session:
            row = await session.execute(
                TraceNode.__table__.select().where(
                    TraceNode.ref_table == "artifact_versions", TraceNode.ref_id == str(version_id)
                )
            )
            return (row.first() is not None and "found") or None

    assert asyncio.run(_get_urn()) is not None

    # 审计可查：模板/运行/规则/规则集各动作均有记录
    audits = client.get("/api/v1/audit-logs").json()
    actions = {a["action"] for a in audits}
    assert {"workflow.create", "workflow_run.create", "rule.create", "rule_set.create"} <= actions
    assert "artifact.upload" in actions
    filtered = client.get("/api/v1/audit-logs", params={"resource_type": "workflow_run"}).json()
    assert all(a["resource_type"] == "workflow_run" for a in filtered)


def test_check_run_not_found(client: TestClient, scenario: dict[str, Any]) -> None:
    assert client.get("/api/v1/check-runs/99999").status_code == 404
    assert client.get("/api/v1/check-runs/99999/findings").status_code == 404


def test_checkers_manifest(client: TestClient) -> None:
    checkers = client.get("/api/v1/checkers").json()
    types = {item["checker_type"] for item in checkers}
    assert {"filename_convention", "metadata_required"} <= types


def test_rule_set_detail_and_members(client: TestClient, scenario: dict[str, Any]) -> None:
    rule_set_id = _prepare_rules(client, scenario)

    detail = client.get(f"/api/v1/rule-sets/{rule_set_id}").json()
    assert len(detail["rule_ids"]) == 2

    extra = client.post(
        "/api/v1/rules",
        json={"code": "EX-1", "name": "附加规则", "category": "process", "checker_type": "metadata_required"},
    ).json()
    added = client.post(f"/api/v1/rule-sets/{rule_set_id}/rules", json={"rule_ids": [extra["id"]]}).json()
    assert len(added["rule_ids"]) == 3

    # 绑定端点已移除（404 守卫）
    assert client.get(f"/api/v1/iterations/{scenario['iteration']['id']}/rule-set-binding").status_code == 404


def test_findings_enriched(client: TestClient, scenario: dict[str, Any]) -> None:
    rule_set_id = _prepare_rules(client, scenario)
    final = _run_check_workflow(client, scenario, rule_set_id)
    assert final["task_id"] is not None
    check_run_id = next(j["check_run_id"] for j in final["jobs"] if j["job_type"] == "rules")

    findings = client.get(f"/api/v1/check-runs/{check_run_id}/findings").json()
    assert findings
    first = findings[0]
    assert first["rule_code"] and first["artifact_code"] and first["version_no"] == 1
    assert first["artifact_name"]
