"""rules 端到端测试：规则库 → 规则集 → 批量检查（worker 执行）→ 报告 → 溯源 → 审计."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def scenario(client: TestClient) -> dict[str, object]:
    """激活迭代 + 两个产物（一个合规、一个违规）。"""
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
    return {"iteration": iteration, "ok": ok_art, "bad": bad_art}


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
    rule_set = client.post("/api/v1/rule-sets", json={"name": "默认集", "rule_ids": [r1["id"], r2["id"]]}).json()
    bound = client.post(f"/api/v1/rule-sets/{rule_set['id']}/bind", json={"iteration_id": scenario["iteration"]["id"]})
    assert bound.status_code == 201
    return rule_set["id"]


def test_full_check_flow(client: TestClient, scenario: dict[str, Any]) -> None:
    rule_set_id = _prepare_rules(client, scenario)
    it_id = scenario["iteration"]["id"]

    created = client.post(f"/api/v1/iterations/{it_id}/check-runs", json={"rule_set_id": rule_set_id})
    assert created.status_code == 202
    run_id = created.json()["id"]

    # 进程内 worker 异步执行：轮询直至 succeeded
    final = None
    for _ in range(50):
        state = client.get(f"/api/v1/check-runs/{run_id}").json()
        if state["status"] in ("succeeded", "failed"):
            final = state
            break
        import time

        time.sleep(0.2)
    assert final is not None and final["status"] == "succeeded", final
    assert final["summary"]["error"] == 2  # 违规件：文件名 + 材料必填
    assert final["summary"]["artifacts"] == 2

    findings = client.get(f"/api/v1/check-runs/{run_id}/findings").json()
    assert len(findings) == 2
    by_severity = client.get(f"/api/v1/check-runs/{run_id}/findings", params={"severity": "error"}).json()
    assert len(by_severity) == 2
    none = client.get(f"/api/v1/check-runs/{run_id}/findings", params={"severity": "info"}).json()
    assert none == []

    runs = client.get(f"/api/v1/iterations/{it_id}/check-runs").json()
    assert len(runs) == 1

    # 任务记录可查
    tasks = client.get("/api/v1/tasks").json()
    assert tasks[0]["status"] == "succeeded"
    task_detail = client.get(f"/api/v1/tasks/{tasks[0]['id']}")
    assert task_detail.status_code == 200
    missing_task = client.get("/api/v1/tasks/99999")
    assert missing_task.status_code == 404

    # WebSocket 推送终态（任务已完成时首条即终态，随后服务端关闭连接）
    with client.websocket_connect(f"/api/v1/ws/tasks/{tasks[0]['id']}") as ws:
        message = ws.receive_json()
        assert message["status"] in ("running", "succeeded")

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

    # 审计可查
    audits = client.get("/api/v1/audit-logs").json()
    actions = {a["action"] for a in audits}
    assert "check_run.create" in actions
    assert "artifact.upload" in actions
    filtered = client.get("/api/v1/audit-logs", params={"resource_type": "check_run"}).json()
    assert all(a["resource_type"] == "check_run" for a in filtered)


def test_check_run_not_found(client: TestClient, scenario: dict[str, Any]) -> None:
    assert client.get("/api/v1/check-runs/99999").status_code == 404
    assert client.get("/api/v1/check-runs/99999/findings").status_code == 404
