"""accounts API 测试：登录 / 用户管理 / API Token."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login_as


def test_login_success_and_me(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["is_superuser"] is True


def test_login_failure(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "ITERD-UNAUTHORIZED"


def test_unauthorized_access(client: TestClient) -> None:
    saved = client.headers.get("Authorization")
    client.headers.pop("Authorization", None)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer junk"})
    assert bad.status_code == 401
    client.headers["Authorization"] = saved


def test_user_management_requires_superuser(client: TestClient) -> None:
    login_as(client, "designer", "designer123")
    resp = client.get("/api/v1/users")
    assert resp.status_code == 403


def test_create_and_list_users(client: TestClient) -> None:
    resp = client.post("/api/v1/users", json={"username": "reviewer1", "password": "secret1", "email": "r@x.io"})
    assert resp.status_code == 201
    duplicate = client.post("/api/v1/users", json={"username": "reviewer1", "password": "secret1"})
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "ITERD-DUPLICATE_CODE"
    listed = client.get("/api/v1/users")
    assert {u["username"] for u in listed.json()} >= {"admin", "reviewer1"}


def test_create_user_with_role(client: TestClient) -> None:
    """管理员可创建三员角色用户；非法角色返回 400."""
    resp = client.post("/api/v1/users", json={"username": "secadmin1", "password": "secret1", "role": "security_admin"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "security_admin"
    listed = {u["username"]: u["role"] for u in client.get("/api/v1/users").json()}
    assert listed["secadmin1"] == "security_admin"

    bad = client.post("/api/v1/users", json={"username": "badrole", "password": "secret1", "role": "root"})
    assert bad.status_code == 400
    assert bad.json()["code"] == "ITERD-INVALID_ROLE"


def test_api_token_flow(client: TestClient) -> None:
    created = client.post("/api/v1/api-tokens", json={"name": "ci"})
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("itk_")
    me = client.get("/api/v1/auth/me", headers={"X-API-Token": body["token"]})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    saved = client.headers.get("Authorization")
    client.headers.pop("Authorization", None)
    invalid = client.get("/api/v1/auth/me", headers={"X-API-Token": "itk_bad"})
    assert invalid.status_code == 401
    client.headers["Authorization"] = saved
