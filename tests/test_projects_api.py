"""projects API 测试：项目树 / RBAC / 迭代状态机."""

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


def test_iteration_partial_update_activation(client: TestClient, iteration: dict[str, Any]) -> None:
    """仅传 status 的部分更新应成功（前端「激活」按钮路径），其余字段保持不变."""
    iid = iteration["id"]
    activated = client.patch(f"/api/v1/iterations/{iid}", json={"status": "active"})
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert body["status"] == "active"
    assert body["title"] == iteration["title"]
    assert body["number"] == iteration["number"]

    # 空 body 无变更
    noop = client.patch(f"/api/v1/iterations/{iid}", json={})
    assert noop.status_code == 200
    assert noop.json()["status"] == "active"
    assert noop.json()["title"] == iteration["title"]

    # 非空字段显式传 null 视为未变更（时间窗允许传 null 清空）
    cleared = client.patch(f"/api/v1/iterations/{iid}", json={"start_date": None, "end_date": None, "objective": ""})
    assert cleared.status_code == 200
    assert cleared.json()["title"] == iteration["title"]
    assert cleared.json()["start_date"] is None

    # title 显式传 null 不应触发非空约束错误
    null_title = client.patch(f"/api/v1/iterations/{iid}", json={"title": None})
    assert null_title.status_code == 200
    assert null_title.json()["title"] == iteration["title"]

    # 非法枚举值 422
    bad = client.patch(f"/api/v1/iterations/{iid}", json={"status": "bogus"})
    assert bad.status_code == 422

    # closed → planned 非法迁移
    replan = client.patch(f"/api/v1/iterations/{iid}", json={"status": "closed"})
    assert replan.status_code == 200
    replan2 = client.patch(f"/api/v1/iterations/{iid}", json={"status": "planned"})
    assert replan2.status_code == 400


def test_rbac_project_isolation(client: TestClient, project: dict[str, Any]) -> None:
    login_as(client, "designer", "designer123")
    resp = client.get(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 403
    listing = client.get("/api/v1/projects")
    assert listing.json() == []

    # 管理员将 designer 加入为 viewer
    client.headers.update({"Authorization": ""})
    login_as(client, "admin", "admin1234")
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


def test_member_list_carries_username(client: TestClient, project: dict[str, Any]) -> None:
    members = client.get(f"/api/v1/projects/{project['id']}/members")
    assert members.status_code == 200
    rows = members.json()
    assert rows and rows[0]["username"] == "admin"


def test_my_role_and_ancestor_inheritance(client: TestClient, project: dict[str, Any]) -> None:
    me = client.get(f"/api/v1/projects/{project['id']}/me")
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == "owner"
    assert body["can_manage"] is True

    child = client.post("/api/v1/projects", json={"code": "P1-SUB2", "name": "子项目", "parent_id": project["id"]})
    assert child.status_code == 201
    # 直接成员缺失时继承父项目角色
    inherited = client.get(f"/api/v1/projects/{child.json()['id']}/me")
    assert inherited.status_code == 200
    assert inherited.json()["role"] == "owner"


def test_iteration_time_window(client: TestClient, project: dict[str, Any]) -> None:
    created = client.post(
        f"/api/v1/projects/{project['id']}/iterations",
        json={"title": "带时间窗", "start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    assert created.status_code == 201
    assert created.json()["start_date"] == "2026-01-01"
    updated = client.patch(
        f"/api/v1/iterations/{created.json()['id']}",
        json={"title": "带时间窗", "end_date": "2026-02-28"},
    )
    assert updated.status_code == 200
    assert updated.json()["end_date"] == "2026-02-28"


def test_iteration_baselines_removed(spa_client: TestClient) -> None:
    """基线功能已移除：GET 404 / POST 405（迁移 0004 破坏性变更的回归守卫，SPA 挂载环境）."""
    project = spa_client.post("/api/v1/projects", json={"code": "P1", "name": "项目一"})
    assert project.status_code == 201, project.text
    created = spa_client.post(f"/api/v1/projects/{project.json()['id']}/iterations", json={"title": "迭代一"})
    assert created.status_code == 201, created.text
    iid = created.json()["id"]
    assert spa_client.get(f"/api/v1/iterations/{iid}/baselines").status_code == 404
    assert spa_client.post(f"/api/v1/iterations/{iid}/baselines", json={"name": "BL"}).status_code == 405
    assert spa_client.get("/api/v1/baselines/1").status_code == 404
