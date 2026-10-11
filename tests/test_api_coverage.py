"""补充覆盖测试：RBAC 边界 / 迭代与基线端点 / 规则与报告 / 溯源图 / 任务与 seed 边缘路径."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import login_as


@pytest.fixture()
def project(client: TestClient) -> dict[str, Any]:
    """预置项目."""
    resp = client.post("/api/v1/projects", json={"code": "CV", "name": "覆盖项目"})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def iteration(client: TestClient, project: dict[str, Any]) -> dict[str, Any]:
    """预置激活迭代."""
    resp = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代"})
    assert resp.status_code == 201, resp.text
    it = resp.json()
    client.patch(f"/api/v1/iterations/{it['id']}", json={"title": "迭代", "status": "active"})
    return it


def _user_id(client: TestClient, username: str) -> int:
    return next(u for u in client.get("/api/v1/users").json() if u["username"] == username)["id"]


def test_designer_project_visibility_and_member_ops(client: TestClient, project: dict[str, Any]) -> None:
    pid = project["id"]
    login_as(client, "designer", "designer123")
    assert client.get("/api/v1/projects").json() == []
    assert client.get(f"/api/v1/projects/{pid}").status_code == 403

    login_as(client, "admin", "admin123")
    designer_id = _user_id(client, "designer")
    client.post("/api/v1/users", json={"username": "mgr", "password": "mgr12345"})
    mgr_id = _user_id(client, "mgr")
    assert (
        client.put(f"/api/v1/projects/{pid}/members", json={"user_id": designer_id, "role": "admin"}).status_code == 201
    )
    # 更新既有成员角色（upsert 更新分支，保持 admin 以便创建子项目）
    updated = client.put(f"/api/v1/projects/{pid}/members", json={"user_id": designer_id, "role": "admin"})
    assert updated.status_code == 201
    assert client.put(f"/api/v1/projects/{pid}/members", json={"user_id": mgr_id, "role": "admin"}).status_code == 201

    # designer（父项目 admin）可创建子项目并自动成为 owner，也可更新父项目
    login_as(client, "designer", "designer123")
    assert client.patch(f"/api/v1/projects/{pid}", json={"code": "CV", "name": "X"}).status_code == 200

    # 非 owner 的 admin 不能授予 owner
    login_as(client, "mgr", "mgr12345")
    assert client.get(f"/api/v1/projects/{pid}/members").status_code == 200
    denied = client.put(f"/api/v1/projects/{pid}/members", json={"user_id": mgr_id, "role": "owner"})
    assert denied.status_code == 403


def test_iteration_and_baseline_endpoints(
    client: TestClient, project: dict[str, Any], iteration: dict[str, Any]
) -> None:
    pid, iid = project["id"], iteration["id"]
    assert client.get(f"/api/v1/projects/{pid}/iterations").status_code == 200
    got = client.get(f"/api/v1/iterations/{iid}")
    assert got.status_code == 200 and got.json()["status"] == "active"
    assert client.get("/api/v1/iterations/99999").status_code == 404
    # 更新不带 number（pop 分支）
    renamed = client.patch(f"/api/v1/iterations/{iid}", json={"title": "迭代改", "objective": "目标"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "迭代改"

    assert client.get(f"/api/v1/iterations/{iid}/baselines").json() == []
    # 产物带版本后建基线
    art = client.post(
        f"/api/v1/artifacts?iteration_id={iid}", json={"code": "CV-1", "name": "件", "category": "drawing"}
    ).json()
    version = client.post(f"/api/v1/artifacts/{art['id']}/versions", files={"file": ("CV-1_revA.dwg", b"v")}).json()
    baseline = client.post(f"/api/v1/iterations/{iid}/baselines", json={"name": "BL-CV"})
    assert baseline.status_code == 201, baseline.text
    detail = client.get(f"/api/v1/baselines/{baseline.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["artifact_version_id"] == version["id"]
    assert client.get("/api/v1/baselines/99999").status_code == 404
    assert len(client.get(f"/api/v1/iterations/{iid}/baselines").json()) == 1


def test_rules_crud_and_rule_sets(client: TestClient, project: dict[str, Any], iteration: dict[str, Any]) -> None:
    rule = client.post(
        "/api/v1/rules",
        json={"code": "R-1", "name": "规则一", "category": "drafting", "checker_type": "filename_convention"},
    )
    assert rule.status_code == 201, rule.text
    dup = client.post(
        "/api/v1/rules",
        json={"code": "R-1", "name": "重复", "category": "drafting", "checker_type": "filename_convention"},
    )
    assert dup.status_code == 400
    patched = client.patch(
        f"/api/v1/rules/{rule.json()['id']}",
        json={
            "code": "R-1",
            "name": "规则一改",
            "category": "drafting",
            "checker_type": "filename_convention",
            "enabled": False,
        },
    )
    assert patched.status_code == 200 and patched.json()["name"] == "规则一改"
    assert (
        client.patch(
            "/api/v1/rules/99999",
            json={"code": "X", "name": "X", "category": "drafting", "checker_type": "filename_convention"},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/rules", params={"category": "drafting"}).status_code == 200

    assert client.post("/api/v1/rule-sets", json={"name": "全局集"}).status_code == 201
    rs = client.post(
        "/api/v1/rule-sets", json={"name": "项目集", "project_id": project["id"], "rule_ids": [rule.json()["id"]]}
    )
    assert rs.status_code == 201, rs.text
    assert len(client.get("/api/v1/rule-sets", params={"project_id": project["id"]}).json()) == 2
    assert client.post("/api/v1/rule-sets/99999/bind", json={"iteration_id": iteration["id"]}).status_code == 404
    assert client.post(f"/api/v1/rule-sets/{rs.json()['id']}/bind", json={"iteration_id": 99999}).status_code == 404
    bound = client.post(f"/api/v1/rule-sets/{rs.json()['id']}/bind", json={"iteration_id": iteration["id"]})
    assert bound.status_code == 201
    # 重复绑定覆盖
    assert (
        client.post(f"/api/v1/rule-sets/{rs.json()['id']}/bind", json={"iteration_id": iteration["id"]}).status_code
        == 201
    )

    # 检查运行 404 分支
    assert (
        client.post(f"/api/v1/iterations/{iteration['id']}/check-runs", json={"rule_set_id": 99999}).status_code == 404
    )
    assert client.post("/api/v1/iterations/99999/check-runs", json={"rule_set_id": rs.json()["id"]}).status_code == 404


def test_findings_filters_and_trace_graph(
    client: TestClient, project: dict[str, Any], iteration: dict[str, Any]
) -> None:
    iid = iteration["id"]
    rule = client.post(
        "/api/v1/rules",
        json={
            "code": "FF-1",
            "name": "文件名",
            "category": "drafting",
            "checker_type": "filename_convention",
            "params": {"pattern": r"^[A-Z0-9-]+_rev[A-Z]\."},
            "severity_default": "error",
        },
    ).json()
    rs = client.post("/api/v1/rule-sets", json={"name": "过滤集", "rule_ids": [rule["id"]]}).json()
    art = client.post(
        f"/api/v1/artifacts?iteration_id={iid}", json={"code": "FF-A", "name": "件", "category": "drawing"}
    ).json()
    client.post(f"/api/v1/artifacts/{art['id']}/versions", files={"file": ("bad.dwg", b"x")})
    run = client.post(f"/api/v1/iterations/{iid}/check-runs", json={"rule_set_id": rs["id"]})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    for _ in range(50):
        state = client.get(f"/api/v1/check-runs/{run_id}").json()
        if state["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)
    assert state["status"] == "succeeded", state

    findings = client.get(f"/api/v1/check-runs/{run_id}/findings").json()
    assert len(findings) >= 1
    version_id = findings[0]["artifact_version_id"]
    rule_item_id = findings[0]["rule_item_id"]
    assert client.get(f"/api/v1/check-runs/{run_id}/findings", params={"rule_item_id": rule_item_id}).status_code == 200
    by_version = client.get(f"/api/v1/check-runs/{run_id}/findings", params={"artifact_version_id": version_id})
    assert by_version.status_code == 200 and len(by_version.json()) >= 1

    # 溯源图：project -contains-> iteration -contains-> version
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.plugins.trace.models import TraceNode

    def _urn(ref_table: str, ref_id: int) -> str:
        async def _q() -> str:
            factory = get_session_factory(get_engine(get_settings().database_url))
            async with factory() as session:
                row = await session.execute(
                    select(TraceNode.urn).where(TraceNode.ref_table == ref_table, TraceNode.ref_id == str(ref_id))
                )
                return row.scalar_one()

        return asyncio.run(_q())

    project_urn = _urn("projects", project["id"])
    version_urn = _urn("artifact_versions", version_id)
    down = client.get("/api/v1/trace/graph", params={"urn": project_urn, "direction": "down"}).json()
    assert {n["urn"] for n in down["nodes"]} >= {version_urn}
    up = client.get("/api/v1/trace/graph", params={"urn": version_urn, "direction": "up"}).json()
    assert {n["urn"] for n in up["nodes"]} >= {project_urn}
    both = client.get("/api/v1/trace/graph", params={"urn": project_urn, "direction": "both"}).json()
    assert both["edges"]
    assert client.get("/api/v1/trace/graph", params={"urn": "urn:iterd:x:none"}).status_code == 200


def test_artifact_endpoint_edges(client: TestClient, project: dict[str, Any], iteration: dict[str, Any]) -> None:
    iid, pid = iteration["id"], project["id"]
    assert client.get("/api/v1/artifacts").status_code == 404
    assert client.get("/api/v1/artifacts", params={"project_id": pid}).status_code == 200
    assert client.get("/api/v1/artifacts/99999").status_code == 404
    assert client.get("/api/v1/versions/99999").status_code == 404
    assert client.get("/api/v1/versions/99999/download").status_code == 404
    assert client.post("/api/v1/artifacts/99999/versions", files={"file": ("x", b"x")}).status_code == 404

    # 无版本的产物间建关联（溯源边跳过分支）
    a = client.post(
        f"/api/v1/artifacts?iteration_id={iid}", json={"code": "EA-1", "name": "A", "category": "drawing"}
    ).json()
    b = client.post(
        f"/api/v1/artifacts?iteration_id={iid}", json={"code": "EA-2", "name": "B", "category": "drawing"}
    ).json()
    linked = client.post(
        f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": b["id"], "link_type": "refers_to"}
    )
    assert linked.status_code == 201, linked.text
    bad_type = client.post(f"/api/v1/artifacts/{a['id']}/links", json={"dst_artifact_id": b["id"], "link_type": "nope"})
    assert bad_type.status_code == 422
    # 名称更新（metadata 为 None 分支）
    renamed = client.patch(f"/api/v1/artifacts/{a['id']}", json={"name": "A 改"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "A 改"


def test_task_list_filter_and_ws_missing(client: TestClient) -> None:
    assert client.get("/api/v1/tasks", params={"status": "succeeded", "limit": 5}).status_code == 200
    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    with client.websocket_connect("/api/v1/ws/tasks/99999") as ws:
        ws.send_json({"token": token})
        message = ws.receive_json()
        assert message["error"] == "task not found"


def test_seed_ensure_admin(env: Path) -> None:
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.models import Base
    from iterd.plugins import accounts, artifacts, projects, rules, trace  # noqa: F401
    from iterd.plugins.accounts.models import User
    from iterd.seed import ensure_admin, seed
    from iterd.tasks import models as task_models  # noqa: F401

    async def _create() -> None:
        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    factory = get_session_factory(get_engine(get_settings().database_url))

    async def _run() -> None:
        async with factory() as session:
            await seed(session, admin_username="root", admin_password="root123")
            await session.commit()
            # 幂等：重复 seed 跳过
            await seed(session, admin_username="root", admin_password="root123")
            await session.commit()
            # 非 bcrypt 口令哈希时重置
            session.add(User(username="legacy", hashed_password="plain", is_active=True))
            await session.commit()
            await ensure_admin(session, "legacy", "newpass")
            await session.commit()

    asyncio.run(_run())


def test_run_one_shot_unknown_executor(env: Path) -> None:
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.models import Base
    from iterd.plugins import accounts  # noqa: F401
    from iterd.tasks import models as task_models  # noqa: F401
    from iterd.tasks import runner
    from iterd.tasks.models import Task

    async def _create() -> None:
        engine = get_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    factory = get_session_factory(get_engine(get_settings().database_url))

    async def main() -> None:
        async with factory() as session:
            task = Task(task_type="no_such_executor", payload={}, status="pending", attempts=1, max_attempts=1)
            session.add(task)
            await session.commit()
            task_id = task.id
            await runner.run_one_shot(session, task, "w1")
        async with factory() as session:
            final = await session.get(Task, task_id)
            assert final is not None and final.status == "failed"

    asyncio.run(main())
