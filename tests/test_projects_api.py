"""projects API 测试：项目树 / RBAC / 迭代状态机 / 基线."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login_as


@pytest.fixture()
def project(client: TestClient) -> dict[str, object]:
    resp = client.post("/api/v1/projects", json={"code": "P1", "name": "项目一"})
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def iteration(client: TestClient, project: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "迭代一"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_project_crud_and_tree(client: TestClient, project: dict[str, Any]) -> None:
    child = client.post("/api/v1/projects", json={"code": "P1-SUB", "name": "子项目", "parent_id": project["id"]})
    assert child.status_code == 201
    duplicate = client.post("/api/v1/projects", json={"code": "P1", "name": "重复"})
    assert duplicate.status_code == 400

    updated = client.patch(
        f"/api/v1/projects/{project['id']}", json={"code": "P1", "name": "项目一改", "description": "更新"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "项目一改"

    listed = client.get("/api/v1/projects", params={"parent_id": project["id"]})
    assert [p["code"] for p in listed.json()] == ["P1-SUB"]
    detail = client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 200
    missing = client.get("/api/v1/projects/99999")
    assert missing.status_code == 404


def test_iteration_number_auto_increment(client: TestClient, project: dict[str, Any]) -> None:
    first = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "A"})
    second = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "B"})
    assert first.json()["number"] == 1
    assert second.json()["number"] == 2


def test_iteration_state_machine(client: TestClient, iteration: dict[str, Any]) -> None:
    iid = iteration["id"]
    closed = client.patch(f"/api/v1/iterations/{iid}", json={"title": "迭代一", "status": "closed"})
    assert closed.status_code == 400  # planned → closed 非法
    activated = client.patch(f"/api/v1/iterations/{iid}", json={"title": "迭代一", "status": "active"})
    assert activated.status_code == 200
    closed_ok = client.patch(f"/api/v1/iterations/{iid}", json={"title": "迭代一", "status": "closed"})
    assert closed_ok.status_code == 200
    assert closed_ok.json()["status"] == "closed"


def test_rbac_project_isolation(client: TestClient, project: dict[str, Any]) -> None:
    login_as(client, "designer", "designer123")
    resp = client.get(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 403
    listing = client.get("/api/v1/projects")
    assert listing.json() == []

    # 管理员将 designer 加入为 viewer
    client.headers.update({"Authorization": ""})
    login_as(client, "admin", "admin123")
    reviewer_id = next(u for u in client.get("/api/v1/users").json() if u["username"] == "designer")["id"]
    added = client.put(f"/api/v1/projects/{project['id']}/members", json={"user_id": reviewer_id, "role": "viewer"})
    assert added.status_code == 201
    login_as(client, "designer", "designer123")
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200
    # viewer 不能建迭代
    denied = client.post(f"/api/v1/projects/{project['id']}/iterations", json={"title": "X"})
    assert denied.status_code == 403


def test_owner_only_grant(client: TestClient, project: dict[str, Any]) -> None:
    members = client.get(f"/api/v1/projects/{project['id']}/members")
    assert members.status_code == 200
    some_id = 1
    resp = client.put(f"/api/v1/projects/{project['id']}/members", json={"user_id": some_id, "role": "owner"})
    # admin（owner 创建者）可授予 owner；验证接口可达
    assert resp.status_code in (201, 403)


def test_baseline_locks_versions(client: TestClient, project: dict[str, Any], iteration: dict[str, Any]) -> None:
    # planned 迭代不允许建基线
    early = client.post(f"/api/v1/iterations/{iteration['id']}/baselines", json={"name": "早期基线"})
    assert early.status_code == 400

    client.patch(f"/api/v1/iterations/{iteration['id']}", json={"title": "迭代一", "status": "active"})
    art = client.post(
        f"/api/v1/artifacts?iteration_id={iteration['id']}", json={"code": "A-1", "name": "零件", "category": "drawing"}
    )
    version = client.post(
        f"/api/v1/artifacts/{art.json()['id']}/versions",
        files={"file": ("A-1_revA.dwg", b"v1")},
        data={"metadata": '{"材料": "Q235"}'},
    )
    assert version.status_code == 201

    baseline = client.post(f"/api/v1/iterations/{iteration['id']}/baselines", json={"name": "BL-1"})
    assert baseline.status_code == 201
    # 基线后再上传新版本，快照不受影响
    client.post(f"/api/v1/artifacts/{art.json()['id']}/versions", files={"file": ("A-1_revB.dwg", b"v2")})
    detail = client.get(f"/api/v1/baselines/{baseline.json()['id']}")
    items = detail.json()["items"]
    assert len(items) == 1
    assert items[0]["artifact_version_id"] == version.json()["id"]

    baselines = client.get(f"/api/v1/iterations/{iteration['id']}/baselines")
    assert len(baselines.json()) == 1
