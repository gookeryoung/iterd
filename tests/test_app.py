"""iterd Web 应用路由测试."""

from __future__ import annotations

from fastapi.testclient import TestClient

from iterd.app import app


def test_root_health_check() -> None:
    """根路径应返回健康检查信息."""
    with TestClient(app) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["project"] == "iterd"
