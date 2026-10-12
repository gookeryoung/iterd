"""iterd.core.backup 备份还原测试：功能 / 校验 / 边界."""

from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import sqlite3
import tarfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from iterd.core.backup import (
    BackupError,
    RestoreError,
    auto_backup_if_due,
    create_backup,
    format_backup_filename,
    inspect_backup,
    restore_backup,
    rotate_backups,
)
from iterd.core.config import Settings, get_settings, reset_settings
from iterd.core.storage import get_storage
from iterd.models import Base


def _create_tables(database_url: str) -> None:
    """建表（导入全部模型保证 metadata 完整）。"""

    async def _create() -> None:
        from iterd.core.database import get_engine
        from iterd.plugins import accounts, artifacts, notify, projects, rules, trace  # noqa: F401
        from iterd.tasks import models as task_models  # noqa: F401

        engine = get_engine(database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


@pytest.fixture()
def seeded_db(env: Path) -> Generator[Path, None, None]:
    """已建表且含一个对象文件的隔离环境，返回数据库文件路径。"""
    from iterd.core import database as dbmod
    from iterd.core import storage as stmod

    _create_tables(get_settings().database_url)
    get_storage().put("demo.bin", io.BytesIO(b"demo object content"))
    yield Path(get_settings().database_url.removeprefix("sqlite+aiosqlite:///"))
    dbmod.reset_database()
    stmod.reset_storage()
    reset_settings(None)


def _repack_with_manifest(archive: Path, manifest: dict[str, Any], output: Path) -> Path:
    """解包归档、替换 manifest 后重新打包（协议版本 / 行数校验测试用）。"""
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(archive.parent / "_repack", filter="data")
    root = archive.parent / "_repack" / "backup"
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with tarfile.open(output, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        tar.add(root, arcname="backup")
    shutil.rmtree(archive.parent / "_repack")
    return output


def test_format_backup_filename() -> None:
    """默认文件名自描述：前缀-软件版本-协议版本-UTC 时间戳."""
    assert re.fullmatch(r"iterd-backup-\d+\.\d+\.\d+-v1-\d{8}T\d{6}Z\.tar\.gz", format_backup_filename())


def test_create_backup_and_roundtrip(seeded_db: Path, env: Path) -> None:
    """备份 → 校验 → 删除数据 → 还原，行数与对象内容零丢失."""
    archive = create_backup()
    assert archive.exists() and archive.parent == get_settings().backup_dir

    manifest = inspect_backup(archive)
    assert manifest["version"] == "1"
    assert manifest["database"]["tables"]
    assert "users" in manifest["database"]["row_counts"]
    assert manifest["objects"]["included"] and manifest["objects"]["file_count"] == 1

    # 破坏现场：删除数据库与对象
    seeded_db.unlink()
    for obj in get_settings().objects_dir.rglob("*"):
        if obj.is_file():
            obj.unlink()

    restore_backup(archive)
    assert seeded_db.is_file()
    conn = sqlite3.connect(str(seeded_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == manifest["database"]["row_counts"]["users"]
    finally:
        conn.close()
    objects = [p for p in get_settings().objects_dir.rglob("*") if p.is_file()]
    assert len(objects) == 1
    assert objects[0].read_bytes() == b"demo object content"


def test_create_backup_no_objects_explicit_output(seeded_db: Path, env: Path) -> None:
    """显式输出 + 排除对象：归档内无 objects 目录，且不触发默认目录轮换."""
    archive = create_backup(env / "custom.tar.gz", include_objects=False)
    assert archive == (env / "custom.tar.gz").resolve()
    manifest = inspect_backup(archive)
    assert manifest["objects"]["included"] is False


def test_create_backup_missing_db(env: Path) -> None:
    """数据库文件不存在时报 BackupError."""
    reset_settings(Settings(data_dir=env, database_url=f"sqlite+aiosqlite:///{env}/missing.db"))
    with pytest.raises(BackupError, match="数据库文件不存在"):
        create_backup()


def test_inspect_backup_missing(tmp_path: Path) -> None:
    """归档不存在时报 RestoreError."""
    with pytest.raises(RestoreError, match="备份归档不存在"):
        inspect_backup(tmp_path / "nope.tar.gz")


def test_inspect_backup_garbage(tmp_path: Path) -> None:
    """非归档内容报 RestoreError."""
    bad = tmp_path / "bad.tar.gz"
    bad.write_bytes(b"not a tar")
    with pytest.raises(RestoreError, match="备份归档不可读"):
        inspect_backup(bad)


def test_inspect_backup_bad_version(tmp_path: Path, seeded_db: Path) -> None:
    """协议版本不兼容时拒绝还原."""
    archive = create_backup()
    manifest: dict[str, Any] = inspect_backup(archive)
    manifest["version"] = "999"
    tampered = _repack_with_manifest(archive, manifest, tmp_path / "v999.tar.gz")
    with pytest.raises(RestoreError, match="不支持的备份协议版本"):
        inspect_backup(tampered)


def test_restore_row_count_mismatch(tmp_path: Path, seeded_db: Path) -> None:
    """还原后行数校验不一致时报 RestoreError（篡改 manifest 模拟）."""
    archive = create_backup()
    manifest: dict[str, Any] = inspect_backup(archive)
    manifest["database"]["row_counts"]["users"] = 999
    tampered = _repack_with_manifest(archive, manifest, tmp_path / "tampered.tar.gz")
    with pytest.raises(RestoreError, match="行数校验不一致"):
        restore_backup(tampered)


def test_restore_target_must_be_sqlite(seeded_db: Path, env: Path) -> None:
    """还原目标仅支持 SQLite."""
    archive = create_backup()
    reset_settings(Settings(data_dir=env, database_url="postgresql://localhost/iterd"))
    with pytest.raises(RestoreError, match="仅支持 SQLite"):
        restore_backup(archive)


def test_rotate_backups(tmp_path: Path) -> None:
    """保留策略：按文件名从新到旧保留 keep 份，其余清理."""
    for i in range(5):
        (tmp_path / f"iterd-backup-0.1.0-v1-2026101{i}T000000Z.tar.gz").write_bytes(b"x")
    removed = rotate_backups(tmp_path, 3)
    assert len(removed) == 2
    assert len(list(tmp_path.glob("iterd-backup-*.tar.gz"))) == 3
    assert rotate_backups(tmp_path, -1) == []


def test_auto_backup_if_due(seeded_db: Path, env: Path) -> None:
    """自动备份：无归档时执行；刚备份过未到间隔跳过；关闭开关返回 None."""
    settings = get_settings()
    created = auto_backup_if_due()
    assert created is not None and created.exists()
    assert auto_backup_if_due() is None  # 未到间隔
    settings.backup_interval_hours = 0
    assert auto_backup_if_due() is None  # 开关关闭


def test_incremental_backup_roundtrip(seeded_db: Path, env: Path) -> None:
    """增量备份：基线对象跳过、新对象入包；基线+增量还原数据零丢失."""
    base_archive = create_backup(env / "base.tar.gz")
    assert inspect_backup(base_archive)["objects"]["base"] == ""

    # 对象零变更：增量对象段为空（仅清单）
    empty_incremental = create_backup(base=base_archive, output=env / "empty.tar.gz")
    empty_manifest = inspect_backup(empty_incremental)
    assert empty_manifest["objects"]["included"] is False and empty_manifest["objects"]["file_count"] == 0

    # 基线后新增一个对象
    get_storage().put("extra.bin", io.BytesIO(b"extra object content"))

    incremental = create_backup(env / "inc.tar.gz", base=base_archive)
    manifest = inspect_backup(incremental)
    assert manifest["objects"]["base"] == base_archive.name
    assert manifest["objects"]["file_count"] == 1  # 仅新增对象

    # 破坏现场：删除数据库与对象
    seeded_db.unlink()
    for obj in get_settings().objects_dir.rglob("*"):
        if obj.is_file():
            obj.unlink()

    restore_backup(incremental, base=base_archive)
    objects = sorted(p.read_bytes() for p in get_settings().objects_dir.rglob("*") if p.is_file())
    assert objects == [b"demo object content", b"extra object content"]


def test_incremental_backup_chain_base_rejected(seeded_db: Path, env: Path) -> None:
    """增量归档不可作为基线（链式增量会导致还原缺对象），创建与还原两端均拦截."""
    get_storage().put("extra.bin", io.BytesIO(b"extra"))
    base_archive = create_backup()
    incremental = create_backup(base=base_archive, output=env / "inc.tar.gz")

    with pytest.raises(BackupError, match="基线须为全量归档"):
        create_backup(env / "inc2.tar.gz", base=incremental)
    with pytest.raises(RestoreError, match="基线归档须为全量归档"):
        restore_backup(incremental, base=incremental)


def test_incremental_restore_requires_matching_base(seeded_db: Path, env: Path) -> None:
    """增量备份还原缺基线或基线不匹配时报 RestoreError."""
    base_archive = create_backup(env / "base.tar.gz")
    get_storage().put("extra.bin", io.BytesIO(b"extra"))
    incremental = create_backup(env / "inc.tar.gz", base=base_archive)

    with pytest.raises(RestoreError, match="增量备份还原需提供基线归档"):
        restore_backup(incremental)
    unrelated = create_backup(env / "unrelated.tar.gz")
    with pytest.raises(RestoreError, match="基线归档不匹配"):
        restore_backup(incremental, base=unrelated)


def test_incremental_backup_missing_base(seeded_db: Path, env: Path) -> None:
    """增量备份基线归档不存在时报 BackupError."""
    with pytest.raises(BackupError, match="基线归档不存在"):
        create_backup(env / "inc.tar.gz", base=env / "nope.tar.gz")
