"""simulation 端到端测试：求解器清单 → 模板 → 作业（worker 执行）→ 结果评估 → 溯源 → 审计."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import login_as


def _wait_job(client: TestClient, job_id: int) -> dict[str, Any]:
    """轮询作业直至终态。"""
    final: dict[str, Any] = {}
    for _ in range(50):
        final = client.get(f"/api/v1/sim-jobs/{job_id}").json()
        if final["status"] in ("succeeded", "failed"):
            return final
        time.sleep(0.2)
    return final


def _scenario(client: TestClient) -> dict[str, Any]:
    """项目 + 激活迭代 + 带版本产物。"""
    project = client.post("/api/v1/projects", json={"code": "SIM", "name": "仿真项目"}).json()
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代", "status": "active"})
    artifact = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}",
        json={"code": "SIM-BEAM", "name": "梁", "category": "model"},
    ).json()
    version = client.post(
        f"/api/v1/artifacts/{artifact['id']}/versions", files={"file": ("SIM-BEAM_revA.step", b"model")}
    ).json()
    return {"project": project, "iteration": iteration, "artifact": artifact, "version": version}


def test_solvers_manifest(client: TestClient) -> None:
    solvers = client.get("/api/v1/solvers").json()
    types = {item["solver_type"] for item in solvers}
    assert "beam_static" in types
    beam = next(item for item in solvers if item["solver_type"] == "beam_static")
    assert {i["key"] for i in beam["inputs"]} >= {"load", "length", "width", "height"}
    assert {m["key"] for m in beam["metrics"]} == {"max_stress", "deflection", "safety_factor"}


def test_template_crud_and_rbac(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"code": "TPL", "name": "模板项目"}).json()

    created = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "BEAM-DEFAULT",
            "name": "梁默认模板",
            "solver_type": "beam_static",
            "project_id": project["id"],
            "thresholds": {"max_stress": {"max": 100}},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["thresholds"] == {"max_stress": {"max": 100}}

    dup = client.post(
        "/api/v1/sim-templates",
        json={"code": "BEAM-DEFAULT", "name": "重复", "solver_type": "beam_static", "project_id": project["id"]},
    )
    assert dup.status_code == 400

    unknown = client.post(
        "/api/v1/sim-templates", json={"code": "X-1", "name": "未知求解器", "solver_type": "no_such_solver"}
    )
    assert unknown.status_code == 422

    assert client.get("/api/v1/sim-templates/99999").status_code == 404
    listed = client.get("/api/v1/sim-templates", params={"project_id": project["id"]}).json()
    assert any(item["code"] == "BEAM-DEFAULT" for item in listed)

    # 非成员 designer 不能在该项目创建模板
    login_as(client, "designer", "designer123")
    denied = client.post(
        "/api/v1/sim-templates",
        json={"code": "DENY", "name": "拒绝", "solver_type": "beam_static", "project_id": project["id"]},
    )
    assert denied.status_code == 403
    # 全局模板仅超管
    global_denied = client.post(
        "/api/v1/sim-templates", json={"code": "GLOBAL", "name": "全局", "solver_type": "beam_static"}
    )
    assert global_denied.status_code == 403


def test_sim_job_flow_and_evaluation(client: TestClient) -> None:
    scene = _scenario(client)
    iteration_id = scene["iteration"]["id"]

    template = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "BEAM-CHECK",
            "name": "梁校核",
            "solver_type": "beam_static",
            "project_id": scene["project"]["id"],
            "thresholds": {"max_stress": {"max": 100}},
        },
    ).json()

    # 未产出结果时 404
    job = client.post(
        f"/api/v1/iterations/{iteration_id}/sim-jobs",
        json={"template_id": template["id"], "artifact_version_id": scene["version"]["id"]},
    )
    assert job.status_code == 202, job.text
    job_id = job.json()["id"]
    assert job.json()["task_id"] is not None
    assert job.json()["template_name"] == "梁校核"
    assert job.json()["artifact_code"] == "SIM-BEAM"
    assert client.get(f"/api/v1/sim-jobs/{job_id}/result").status_code == 404

    done = _wait_job(client, job_id)
    assert done["status"] == "succeeded", done
    assert done["summary"] == {"metrics": 3, "failures": 0, "verdict": "pass"}

    result = client.get(f"/api/v1/sim-jobs/{job_id}/result").json()
    assert result["verdict"] == "pass" and result["failures"] == 0
    assert set(result["metrics"]) == {"max_stress", "deflection", "safety_factor"}
    # 默认参数：max_stress = 1.5*1000*500/(20*40^2) = 23.4375
    assert result["metrics"]["max_stress"] == 23.4375
    assert all(item["passed"] for item in result["detail"])

    # 加大载荷至 5000N：max_stress = 117.1875 > 100 → 判定失败
    second = client.post(
        f"/api/v1/iterations/{iteration_id}/sim-jobs",
        json={
            "template_id": template["id"],
            "artifact_version_id": scene["version"]["id"],
            "inputs": {"load": 5000},
        },
    ).json()
    second_id = second["id"]
    failed_done = _wait_job(client, second_id)
    assert failed_done["status"] == "succeeded"
    assert failed_done["summary"]["verdict"] == "fail"
    failed_result = client.get(f"/api/v1/sim-jobs/{second_id}/result").json()
    assert failed_result["failures"] == 1
    assert failed_result["metrics"]["max_stress"] == 117.1875
    stress_item = next(item for item in failed_result["detail"] if item["key"] == "max_stress")
    assert stress_item["passed"] is False

    jobs = client.get(f"/api/v1/iterations/{iteration_id}/sim-jobs").json()
    assert len(jobs) == 2
    assert jobs[0]["solver_type"] == "beam_static"

    # 溯源：作业与结果节点已注册
    import asyncio

    from sqlalchemy import select

    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.trace.models import TraceNode

    async def _count() -> int:
        factory = get_session_factory(get_engine(get_settings().database_url))
        async with factory() as session:
            rows = (await session.execute(select(TraceNode.urn).where(TraceNode.ref_table == "sim_jobs"))).scalars()
            return len(list(rows))

    assert asyncio.run(_count()) == 2

    audits = client.get("/api/v1/audit-logs", params={"resource_type": "sim_job"}).json()
    assert audits and audits[0]["action"] == "sim_job.create"


def test_sim_job_invalid_inputs_failed(client: TestClient) -> None:
    scene = _scenario(client)
    template = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "BEAM-BAD",
            "name": "梁异常输入",
            "solver_type": "beam_static",
            "project_id": scene["project"]["id"],
        },
    ).json()
    job = client.post(
        f"/api/v1/iterations/{scene['iteration']['id']}/sim-jobs",
        json={"template_id": template["id"], "inputs": {"load": "not-a-number"}},
    ).json()

    done = _wait_job(client, job["id"])
    assert done["status"] == "failed"
    assert "不是数值" in (done["error"] or "")
    assert client.get(f"/api/v1/sim-jobs/{job['id']}/result").status_code == 404

    tasks = client.get("/api/v1/tasks", params={"status": "failed"}).json()
    assert tasks and tasks[0]["task_type"] == "sim_job"


def test_sim_job_edges(client: TestClient) -> None:
    scene = _scenario(client)
    iteration_id = scene["iteration"]["id"]
    template = client.post(
        "/api/v1/sim-templates",
        json={"code": "EDGE-1", "name": "边界模板", "solver_type": "beam_static", "project_id": scene["project"]["id"]},
    ).json()

    assert client.get("/api/v1/sim-jobs/99999").status_code == 404
    assert client.get("/api/v1/sim-jobs/99999/result").status_code == 404
    assert client.get("/api/v1/iterations/99999/sim-jobs").status_code == 404
    assert client.get(f"/api/v1/iterations/{iteration_id}/sim-jobs").json() == []

    bad_template = client.post(f"/api/v1/iterations/{iteration_id}/sim-jobs", json={"template_id": 99999})
    assert bad_template.status_code == 404
    bad_version = client.post(
        f"/api/v1/iterations/{iteration_id}/sim-jobs",
        json={"template_id": template["id"], "artifact_version_id": 99999},
    )
    assert bad_version.status_code == 404

    # 非成员 designer 不能发起作业
    login_as(client, "designer", "designer123")
    denied = client.post(f"/api/v1/iterations/{iteration_id}/sim-jobs", json={"template_id": template["id"]})
    assert denied.status_code == 403


def test_template_patch(client: TestClient) -> None:
    """仿真模板 PATCH：部分更新 / 求解器校验 / RBAC / 停用门禁 / 404。"""
    project = client.post("/api/v1/projects", json={"code": "PTP", "name": "PATCH 项目"}).json()
    template = client.post(
        "/api/v1/sim-templates",
        json={
            "code": "PTP-BEAM",
            "name": "梁校核",
            "solver_type": "beam_static",
            "project_id": project["id"],
            "thresholds": {"max_stress": {"max": 100}},
            "description": "原始说明",
        },
    ).json()
    template_id = template["id"]

    # 部分更新：仅改名称与阈值，其余字段不变
    patched = client.patch(f"/api/v1/sim-templates/{template_id}", json={"name": "梁校核 v2", "enabled": False})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"] == "梁校核 v2"
    assert body["enabled"] is False
    assert body["solver_type"] == "beam_static"
    assert body["thresholds"] == {"max_stress": {"max": 100}}
    assert body["description"] == "原始说明"

    # solver_type 变更：未知求解器 422，合法求解器生效
    unknown = client.patch(f"/api/v1/sim-templates/{template_id}", json={"solver_type": "no_such_solver"})
    assert unknown.status_code == 422
    switched = client.patch(
        f"/api/v1/sim-templates/{template_id}",
        json={"solver_type": "shaft_torsion", "params": {"torque": 300}, "thresholds": None},
    )
    assert switched.status_code == 200
    assert switched.json()["solver_type"] == "shaft_torsion"
    assert switched.json()["params"] == {"torque": 300}
    assert switched.json()["thresholds"] is None

    # 停用模板不可发起作业
    iteration = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"}).json()
    disabled = client.post(f"/api/v1/iterations/{iteration['id']}/sim-jobs", json={"template_id": template_id})
    assert disabled.status_code == 400
    assert "ITERD-INVALID_STATE" in disabled.text

    # 空体 PATCH：无字段变更仍成功
    noop = client.patch(f"/api/v1/sim-templates/{template_id}", json={})
    assert noop.status_code == 200

    assert client.patch("/api/v1/sim-templates/99999", json={"name": "x"}).status_code == 404

    # RBAC：非成员 designer 不能改项目模板，也不能改全局模板
    client.post("/api/v1/sim-templates", json={"code": "PTP-GLOBAL", "name": "全局", "solver_type": "beam_static"})
    login_as(client, "designer", "designer123")
    assert client.patch(f"/api/v1/sim-templates/{template_id}", json={"name": "越权"}).status_code == 403
    templates = client.get("/api/v1/sim-templates").json()
    global_id = next(t["id"] for t in templates if t["code"] == "PTP-GLOBAL")
    assert client.patch(f"/api/v1/sim-templates/{global_id}", json={"name": "越权"}).status_code == 403

    # 审计已记录 sim_template.update
    audits = client.get("/api/v1/audit-logs", params={"resource_type": "sim_template"}).json()
    actions = [a["action"] for a in audits]
    assert "sim_template.update" in actions
