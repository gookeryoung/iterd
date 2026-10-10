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


@pytest.fixture()
def client(env: Path) -> Generator[TestClient, None, None]:
    """带管理员登录态的测试客户端（启用进程内 worker，预置 designer 用户）。"""
    from iterd.app import create_app

    application = create_app()
    with TestClient(application) as http:
        resp = http.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        http.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
        created = http.post("/api/v1/users", json={"username": "designer", "password": "designer123"})
        if created.status_code == 201:
            pass  # 已存在则忽略
        yield http


def login_as(client: TestClient, username: str, password: str) -> None:
    """切换客户端登录用户."""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    client.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
