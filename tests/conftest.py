"""共享夹具：隔离环境的 TestClient."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """隔离配置：临时 SQLite 与数据目录."""
    from iterd.core import config as cfg
    from iterd.core import database as dbmod
    from iterd.core import storage as stmod

    dbmod.reset_database()
    stmod.reset_storage()
    cfg.reset_settings(None)
    monkeypatch.setenv("ITERD_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ITERD_DATA_DIR", str(tmp_path / "data"))
    cfg.reset_settings(None)
    dbmod.reset_database()
    stmod.reset_storage()
    yield tmp_path
    cfg.reset_settings(None)
    dbmod.reset_database()
    stmod.reset_storage()


def _build_test_client() -> Generator[TestClient, None, None]:
    """创建带管理员登录态的客户端（启用进程内 worker，预置 designer 用户）。"""
    from iterd.app import create_app

    application = create_app()
    with TestClient(application) as http:
        resp = http.post("/api/v1/auth/login", json={"username": "admin", "password": "admin1234"})
        http.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
        created = http.post("/api/v1/users", json={"username": "designer", "password": "designer123"})
        if created.status_code == 201:
            pass  # 已存在则忽略
        yield http


@pytest.fixture()
def client(env: Path) -> Generator[TestClient, None, None]:
    """带管理员登录态的测试客户端（启用进程内 worker，预置 designer 用户）。"""
    yield from _build_test_client()


@pytest.fixture()
def spa_client(env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """SPA 已挂载的测试客户端：在临时目录伪造前端构建产物并重定向静态目录解析.

    用于验证已移除端点在 SPA 托管下的 404/405 行为，不依赖真实前端构建产物。
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><html><body>spa</body></html>", encoding="utf-8")
    import iterd.app as app_module

    monkeypatch.setattr(app_module, "__file__", str(tmp_path / "app.py"))
    yield from _build_test_client()


def login_as(client: TestClient, username: str, password: str) -> None:
    """切换客户端登录用户."""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
