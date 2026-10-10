"""存储与配置单元测试."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from iterd.core.config import Settings, get_settings, reset_settings
from iterd.core.storage import LocalStorage, get_storage, reset_storage


def test_local_storage_content_addressed(tmp_path: Path) -> None:
    store = LocalStorage(tmp_path)
    a = store.put("x.bin", io.BytesIO(b"hello"))
    b = store.put("y.bin", io.BytesIO(b"hello"))
    assert a.sha256 == b.sha256
    assert store.exists(a.sha256)
    assert store.open(a.sha256).read() == b"hello"
    assert store.local_path(a.sha256).exists()
    store.delete(a.sha256)
    assert not store.exists(a.sha256)
    store.delete("nonexistent")  # 静默


def test_settings_roundtrip() -> None:
    reset_settings(Settings(database_url="sqlite+aiosqlite:///x.db"))
    assert get_settings().database_url == "sqlite+aiosqlite:///x.db"
    reset_settings(None)
    assert get_settings() is get_settings()
    reset_settings(None)


def test_get_storage_singleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ITERD_DATA_DIR", str(tmp_path))
    reset_storage()
    reset_settings(None)
    s1 = get_storage()
    assert get_storage() is s1
    reset_storage()
    reset_settings(None)
