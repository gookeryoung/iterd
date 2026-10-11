"""iterd Web 应用路由测试."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from iterd.app import create_app


def test_root_serves_spa_or_health(env: Path) -> None:
    """根路径：有前端构建产物时由 SPA 托管返回首页；无产物时返回健康检查 JSON."""
    static_index = Path(__file__).parents[1] / "src" / "iterd" / "static" / "index.html"
    with TestClient(create_app()) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    if static_index.exists():
        assert "text/html" in resp.headers["content-type"]
    else:
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
