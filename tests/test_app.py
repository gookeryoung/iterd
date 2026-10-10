"""iterd Web 应用路由测试."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from iterd.app import create_app


def test_root_health_check(env: Path) -> None:
    """根路径应返回健康检查信息（lifespan 启动建表与管理员）。"""
    with TestClient(create_app()) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["project"] == "iterd"


def test_openapi_available(env: Path) -> None:
    """OpenAPI 文档可访问。"""
    with TestClient(create_app()) as client:
        resp = client.get("/docs")
    assert resp.status_code == 200


def test_spa_history_fallback(env: Path) -> None:
    """构建产物存在时，未知前端路由回退 index.html，未匹配 API 路径仍 404。"""
    static_index = Path(__file__).parents[1] / "src" / "iterd" / "static" / "index.html"
    if not static_index.exists():
        import pytest

        pytest.skip("前端构建产物不存在")
    with TestClient(create_app()) as client:
        page = client.get("/projects/1")
        api_miss = client.get("/api/v1/not-exist")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert api_miss.status_code == 404
