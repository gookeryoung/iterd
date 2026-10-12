"""补充覆盖测试：RBAC 边界 / 迭代端点 / 规则与报告 / 溯源图 / 任务与 seed 边缘路径."""

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

    login_as(client, "admin", "admin1234")
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


def test_iteration_endpoints(client: TestClient, project: dict[str, Any], iteration: dict[str, Any]) -> None:
    pid, iid = project["id"], iteration["id"]
    assert client.get(f"/api/v1/projects/{pid}/iterations").status_code == 200
    got = client.get(f"/api/v1/iterations/{iid}")
    assert got.status_code == 200 and got.json()["status"] == "active"
    assert client.get("/api/v1/iterations/99999").status_code == 404
    # 更新不带 number（pop 分支）
    renamed = client.patch(f"/api/v1/iterations/{iid}", json={"title": "迭代改", "objective": "目标"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "迭代改"

    # 基线端点已移除（404 守卫）
    assert client.get(f"/api/v1/iterations/{iid}/baselines").status_code == 404
    assert client.get("/api/v1/baselines/99999").status_code == 404


def test_rules_crud_and_rule_sets(spa_client: TestClient) -> None:
    """规则与规则集 CRUD，含已移除端点守卫（SPA 挂载下 POST 落到 StaticFiles 返回 405）."""
    project = spa_client.post("/api/v1/projects", json={"code": "CV", "name": "覆盖项目"})
    assert project.status_code == 201, project.text
    created = spa_client.post(f"/api/v1/projects/{project.json()['id']}/iterations", json={"title": "迭代"})
    assert created.status_code == 201, created.text
    iid = created.json()["id"]

    rule = spa_client.post(
        "/api/v1/rules",
        json={"code": "R-1", "name": "规则一", "category": "drafting", "checker_type": "filename_convention"},
    )
    assert rule.status_code == 201, rule.text
    dup = spa_client.post(
        "/api/v1/rules",
        json={"code": "R-1", "name": "重复", "category": "drafting", "checker_type": "filename_convention"},
    )
    assert dup.status_code == 400
    patched = spa_client.patch(
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
        spa_client.patch(
            "/api/v1/rules/99999",
            json={"code": "X", "name": "X", "category": "drafting", "checker_type": "filename_convention"},
        ).status_code
        == 404
    )
    assert spa_client.get("/api/v1/rules", params={"category": "drafting"}).status_code == 200

    assert spa_client.post("/api/v1/rule-sets", json={"name": "全局集"}).status_code == 201
    rs = spa_client.post(
        "/api/v1/rule-sets",
        json={"name": "项目集", "project_id": project.json()["id"], "rule_ids": [rule.json()["id"]]},
    )
    assert rs.status_code == 201, rs.text
    assert len(spa_client.get("/api/v1/rule-sets", params={"project_id": project.json()["id"]}).json()) == 2

    # 绑定与独立触发端点已移除（SPA 挂载下 GET→404 / POST→405 守卫）
    assert spa_client.post(f"/api/v1/rule-sets/{rs.json()['id']}/bind", json={"iteration_id": iid}).status_code == 405
    assert (
        spa_client.post(f"/api/v1/iterations/{iid}/check-runs", json={"rule_set_id": rs.json()["id"]}).status_code
        == 405
    )


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
    client.post("/api/v1/rule-sets", json={"name": "过滤集", "rule_ids": [rule["id"]]})
    art = client.post(
        f"/api/v1/artifacts?iteration_id={iid}", json={"code": "FF-A", "name": "件", "category": "drawing"}
    ).json()
    client.post(f"/api/v1/artifacts/{art['id']}/versions", files={"file": ("bad.dwg", b"x")})

    # 规则检查运行经审查流水线触发（唯一入口）
    workflow = client.post(
        "/api/v1/workflows",
        json={
            "code": "FF-REVIEW",
            "name": "过滤审查",
            "project_id": project["id"],
            "definition": "name: 过滤审查\njobs:\n  check:\n    uses: rules/check\n    with: {rule_set: 过滤集}\n",
        },
    ).json()
    run = client.post(f"/api/v1/iterations/{iid}/workflow-runs", json={"workflow_id": workflow["id"]})
    assert run.status_code == 202, run.text
    run_id = run.json()["id"]
    for _ in range(50):
        state = client.get(f"/api/v1/workflow-runs/{run_id}").json()
        if state["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.2)
    assert state["status"] == "failed", state
    check_run_id = next(j["check_run_id"] for j in state["jobs"] if j["job_type"] == "rules")
    assert client.get(f"/api/v1/check-runs/{check_run_id}").json()["summary"]["error"] == 1

    findings = client.get(f"/api/v1/check-runs/{check_run_id}/findings").json()
    assert len(findings) >= 1
    version_id = findings[0]["artifact_version_id"]
    rule_item_id = findings[0]["rule_item_id"]
    assert (
        client.get(f"/api/v1/check-runs/{check_run_id}/findings", params={"rule_item_id": rule_item_id}).status_code
        == 200
    )
    by_version = client.get(f"/api/v1/check-runs/{check_run_id}/findings", params={"artifact_version_id": version_id})
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
    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin1234"}).json()[
        "access_token"
    ]
    with client.websocket_connect("/api/v1/ws/tasks/99999") as ws:
        ws.send_json({"token": token})
        message = ws.receive_json()
        assert message["error"] == "task not found"


def test_seed_ensure_admin(env: Path) -> None:
    from iterd.core.config import get_settings
    from iterd.core.database import get_engine, get_session_factory
    from iterd.models import Base
    from iterd.plugins.accounts import models as accounts_models  # noqa: F401
    from iterd.plugins.accounts.models import User, UserRole
    from iterd.plugins.artifacts import models as artifacts_models  # noqa: F401
    from iterd.plugins.notify import models as notify_models  # noqa: F401
    from iterd.plugins.projects import models as projects_models  # noqa: F401
    from iterd.plugins.rules import models as rules_models  # noqa: F401
    from iterd.plugins.simulation import models as simulation_models  # noqa: F401
    from iterd.plugins.trace import models as trace_models  # noqa: F401
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
            summary = await seed(session, admin_username="root", admin_password="root123")
            await session.commit()
            # 三员 + 普通用户账号齐全
            roles = {u["username"]: u["role"] for u in summary["users"]}
            assert roles == {
                "root": "系统管理员",
                "sec_admin": "安全管理员",
                "audit_admin": "审计管理员",
                "designer": "普通用户",
                "reviewer": "普通用户",
                "demo": "普通用户",
            }
            # 幂等：重复 seed 跳过（账号清单不变，全部标记"沿用既有"）
            summary2 = await seed(session, admin_username="root", admin_password="root123")
            await session.commit()
            assert {u["username"]: u["role"] for u in summary2["users"]} == roles
            assert all(not u["created"] for u in summary2["users"])
            # 数据库角色值校验
            rows = (await session.execute(select(User.username, User.role))).all()
            role_map = {r.username: r.role for r in rows}
            assert role_map["root"] == UserRole.SYSTEM_ADMIN.value
            assert role_map["sec_admin"] == UserRole.SECURITY_ADMIN.value
            assert role_map["audit_admin"] == UserRole.AUDIT_ADMIN.value
            assert role_map["demo"] == UserRole.USER.value
            # 非 bcrypt 口令哈希时重置
            session.add(User(username="legacy", hashed_password="plain", is_active=True))
            await session.commit()
            await ensure_admin(session, "legacy", "newpass")
            await session.commit()
            # 已存在管理员口令与配置不符时同步为配置口令；一致时不改动哈希
            from iterd.core.security import hash_password, verify_password

            session.add(User(username="stale", hashed_password=hash_password("oldpass"), is_active=True))
            session.add(User(username="fresh", hashed_password=hash_password("samepass"), is_active=True))
            await session.commit()
            await ensure_admin(session, "stale", "newpass2")
            await ensure_admin(session, "fresh", "samepass")
            await session.commit()
            stale = (await session.execute(select(User).where(User.username == "stale"))).scalar_one()
            fresh = (await session.execute(select(User).where(User.username == "fresh"))).scalar_one()
            assert verify_password("newpass2", stale.hashed_password)
            assert not verify_password("oldpass", stale.hashed_password)
            assert verify_password("samepass", fresh.hashed_password)

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
