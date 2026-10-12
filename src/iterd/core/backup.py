"""数据备份与还原：SQLite 热备份 + 内容寻址对象存储归档.

覆盖内容：
1. SQLite 数据库（``sqlite3.Connection.backup`` 页级热备份，无需停服）
2. objects 内容寻址对象存储（产物文件，版本不可变）

输出为 ``.tar.gz`` 归档，内含 ``manifest.json`` 元信息供还原端校验。
对象存储内容寻址且不可变，跨归档天然去重；多次归档叠加还原等价于最新全量。

增量备份：``create_backup(base=<全量基线归档>)`` —— 基线中已包含的对象跳过不重复打包
（对象零变更时对象段为空），数据库始终为全量快照；还原时通过 ``restore_backup(base=…)``
先还原基线对象再叠加增量对象，数据一致性语义与全量还原相同。基线必须为全量归档
（增量归档不含被跳过的对象，链式增量会导致还原缺对象，创建与还原两端均拦截）。

归档结构::

    iterd-backup-<软件版本>-v<manifest版本>-<UTC时间戳>.tar.gz
    ├── manifest.json          # 备份元信息（版本、时间、表清单与行数、对象统计）
    ├── data/
    │   └── iterd.db           # native 模式下的数据库一致性快照
    └── objects/               # 内容寻址对象（{sha256[:2]}/{sha256}）
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import shutil
import sqlite3
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "MANIFEST_VERSION",
    "SUPPORTED_MANIFEST_VERSIONS",
    "BackupError",
    "BackupManifest",
    "RestoreError",
    "auto_backup_if_due",
    "create_backup",
    "format_backup_filename",
    "inspect_backup",
    "restore_backup",
    "rotate_backups",
]

logger = logging.getLogger("iterd.backup")

MANIFEST_VERSION = "1"  # 当前 manifest 协议版本，restore 端检查此值做兼容性判断
SUPPORTED_MANIFEST_VERSIONS = {"1"}  # restore 端支持的 manifest 协议版本集合

_DB_BACKUP_NAME = "iterd.db"
_OBJECTS_DIR_NAME = "objects"
_BACKUP_PREFIX = "iterd-backup"


class BackupError(RuntimeError):
    """备份过程中的业务错误."""


class RestoreError(RuntimeError):
    """还原过程中的业务错误（归档缺失、协议不兼容、校验不一致等）."""


@dataclass
class ObjectsInfo:
    """对象存储备份统计."""

    included: bool = False
    file_count: int = 0
    total_size: int = 0
    base: str = ""  # 增量备份的基线归档文件名（全量备份为空串）


@dataclass
class DatabaseInfo:
    """数据库备份统计."""

    path: str = ""
    db_type: str = "sqlite"
    backup_mode: str = "native"
    tables: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class BackupManifest:
    """备份元信息（序列化写入 manifest.json）."""

    version: str = MANIFEST_VERSION
    app_version: str = ""
    created_at: str = ""
    database: DatabaseInfo = field(default_factory=DatabaseInfo)
    objects: ObjectsInfo = field(default_factory=ObjectsInfo)


def format_backup_filename(ext: str = ".tar.gz") -> str:
    """生成带版本标注的默认备份文件名.

    格式：``iterd-backup-<软件版本>-v<manifest版本>-<UTC时间戳><ext>``，
    示例：``iterd-backup-0.1.0-v1-20261010T121530Z.tar.gz``。
    文件名自描述且按时间可排序，是"指定时间点还原"选择归档的依据。

    Args:
        ext: 文件名后缀（归档 ``.tar.gz``）.

    Returns:
        带软件版本与 manifest 协议版本的文件名.
    """
    import iterd

    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{_BACKUP_PREFIX}-{iterd.__version__}-v{MANIFEST_VERSION}-{ts}{ext}"


def _resolve_sqlite_path(database_url: str) -> Path:
    """从 SQLite DATABASE_URL 解析出实际数据库文件路径."""
    path_str = urlparse(database_url).path
    if path_str.startswith("/"):
        path_str = path_str[1:]
    return Path(path_str).resolve()


def _row_counts_of(conn: sqlite3.Connection) -> dict[str, int]:
    """枚举用户表并统计行数（排除 sqlite_ 内部表），用于备份统计与还原校验."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    return {table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) for table in tables}  # nosec B608 - 表名来自 sqlite_master 枚举


def _backup_sqlite_native(db_path: Path, target_dir: Path) -> dict[str, int]:
    """使用 sqlite3 的 backup() API 热备份数据库文件到 target_dir/iterd.db."""
    dest = target_dir / _DB_BACKUP_NAME
    src_conn = sqlite3.connect(str(db_path))
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()
    conn = sqlite3.connect(str(dest))
    try:
        return _row_counts_of(conn)
    finally:
        conn.close()


def _collect_objects(objects_dir: Path, target_dir: Path, skip: set[str] | None = None) -> ObjectsInfo:
    """收集内容寻址对象目录并复制到归档临时目录，保留 {sha256[:2]}/ 结构.

    Args:
        objects_dir: 对象存储源目录.
        target_dir: 归档临时目录.
        skip: 相对路径集合（来自基线归档），命中的对象跳过（增量备份去重）.
    """
    info = ObjectsInfo(included=False)
    if not objects_dir.is_dir():
        return info
    target_objects = target_dir / _OBJECTS_DIR_NAME
    excluded = skip or set()
    for src_file in sorted(objects_dir.rglob("*")):
        if not src_file.is_file() or src_file.name.startswith("."):
            continue
        rel = src_file.relative_to(objects_dir).as_posix()
        if rel in excluded:
            continue
        dst_file = target_objects / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        info.file_count += 1
        info.total_size += src_file.stat().st_size
    info.included = info.file_count > 0
    return info


def _object_relpaths_in_archive(archive: Path) -> set[str]:
    """枚举归档内对象成员的相对路径（backup/objects/ 下），供增量备份跳过未变对象."""
    with tarfile.open(archive, "r:gz") as tar:
        prefix = f"backup/{_OBJECTS_DIR_NAME}/"
        return {m.name.removeprefix(prefix) for m in tar.getmembers() if m.isfile() and m.name.startswith(prefix)}


def _make_tar_archive(source_dir: Path, output_path: Path) -> None:
    """将 source_dir 打包为 output_path（.tar.gz，GNU 长文件格式支持 Windows 长路径）."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        tar.add(source_dir, arcname="backup")


def _ensure_tmp_dir(settings: Any) -> Path:
    """确保临时拼装目录存在（data_dir 整体覆盖后派生目录可能尚未创建）."""
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    return settings.tmp_dir


def _ensure_backup_dir(target: Path) -> Path:
    """确保默认备份目录存在；不可用时降级到系统临时目录并告警."""
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError as exc:
        fallback = Path(tempfile.gettempdir()) / "iterd-backups"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError as fallback_exc:
            raise BackupError(
                f"默认备份目录不可创建: {target}（{exc}）；备用目录也不可用: {fallback}（{fallback_exc}）"
            ) from exc
        logger.warning("默认备份目录不可用（%s），改用备用目录: %s", exc, fallback)
        return fallback


def create_backup(  # noqa: PLR0913 - 备份参数
    output: Path | None = None,
    *,
    include_objects: bool = True,
    keep: int | None = None,
    database_url: str | None = None,
    objects_dir: Path | None = None,
    base: Path | None = None,
) -> Path:
    """创建数据备份（base 指定基线归档时为增量备份）.

    Args:
        output: 归档输出路径；默认落到配置的 backup_dir，按 ``format_backup_filename``
            生成自描述文件名。目录不可用时降级到系统临时目录并告警。
        include_objects: 是否包含 objects 内容寻址对象目录.
        keep: 备份后保留策略 —— 默认输出目录中最多保留的归档数（按文件名时间戳排序），
            超出从旧到新清理；仅对默认输出路径生效，显式指定 output 时不轮换。
        database_url: 覆盖配置中的数据库连接串（测试用）.
        objects_dir: 覆盖配置中的对象存储目录（测试用）.
        base: 增量备份的基线归档（必须为全量备份）—— 基线中已包含的对象跳过
            不重复打包（对象内容寻址不可变，跳过即去重）；数据库始终为全量快照.
            还原该归档时必须同时提供同一基线。

    Returns:
        备份归档的绝对路径.

    Raises:
        BackupError: 数据库文件不存在、基线归档不可用或备份过程中发生业务错误.
    """
    from iterd.core.config import get_settings

    settings = get_settings()
    db_url = database_url or settings.database_url
    obj_dir = objects_dir or settings.objects_dir

    if output is None:
        default_dir = _ensure_backup_dir(settings.backup_dir)
        output = (default_dir / format_backup_filename()).resolve()
        logger.info("未指定输出路径，默认备份到: %s", output)
    else:
        output = Path(output).resolve()

    temp_root = Path(tempfile.mkdtemp(prefix="iterd-backup-", dir=_ensure_tmp_dir(settings)))
    try:
        db_dir = temp_root / "data"
        db_dir.mkdir()
        manifest = BackupManifest(
            app_version=_app_version(),
            created_at=dt.datetime.now(dt.UTC).isoformat(),
            database=DatabaseInfo(backup_mode="native"),
        )

        db_path = _resolve_sqlite_path(db_url)
        if not db_path.is_file():
            raise BackupError(f"SQLite 数据库文件不存在: {db_path}")
        manifest.database.path = _DB_BACKUP_NAME
        manifest.database.row_counts = _backup_sqlite_native(db_path, db_dir)
        manifest.database.tables = sorted(manifest.database.row_counts)
        logger.info(
            "数据库备份完成: %d 张表, 共 %d 行",
            len(manifest.database.row_counts),
            sum(manifest.database.row_counts.values()),
        )

        if include_objects:
            skip: set[str] | None = None
            if base is not None:
                if not base.is_file():
                    raise BackupError(f"增量备份基线归档不存在: {base}")
                base_manifest = inspect_backup(base)
                if str(base_manifest["objects"].get("base", "")):
                    raise BackupError(
                        f"增量备份基线须为全量归档（增量归档不含被跳过的对象，链式基线会导致还原缺对象）: {base}"
                    )
                skip = _object_relpaths_in_archive(base)
            manifest.objects = _collect_objects(obj_dir, temp_root, skip=skip)
            if base is not None:
                manifest.objects.base = base.name
            logger.info("对象备份: %d 个文件, %.1f KB", manifest.objects.file_count, manifest.objects.total_size / 1024)

        manifest_path = temp_root / "manifest.json"
        manifest_path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2), encoding="utf-8")

        _make_tar_archive(temp_root, output)
        logger.info("备份完成: %s（%.2f MB）", output, output.stat().st_size / 1024 / 1024)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    if keep is None:
        keep = settings.backup_keep
    rotate_backups(output.parent, keep)
    return output


def rotate_backups(backup_dir: Path, keep: int) -> list[Path]:
    """保留策略轮换：目录内归档按文件名（含 UTC 时间戳，可排序）从新到旧保留 ``keep`` 份.

    Args:
        backup_dir: 备份归档目录.
        keep: 最大保留数量；小于 0 表示不清理.

    Returns:
        本次删除的归档路径列表.
    """
    if keep < 0:
        return []
    archives = sorted(backup_dir.glob(f"{_BACKUP_PREFIX}-*.tar.gz"), reverse=True)
    removed: list[Path] = []
    for stale in archives[keep:]:
        stale.unlink()
        removed.append(stale)
        logger.info("保留策略清理过期归档: %s", stale)
    return removed


def _app_version() -> str:
    """读取 iterd 软件版本（独立函数便于测试替换）."""
    import iterd

    return iterd.__version__


def _read_manifest(archive: Path) -> tuple[tarfile.TarFile, dict[str, Any]]:
    """打开归档并读取 manifest.json（供 inspect 与 restore 共用）.

    Raises:
        RestoreError: 归档不可读、manifest 缺失、协议版本不兼容或数据库文件缺失.
    """
    if not archive.is_file():
        raise RestoreError(f"备份归档不存在: {archive}")
    try:
        tar = tarfile.open(archive, "r:gz")  # noqa: SIM115 - tar 句柄跨函数返回给调用方使用，由调用方负责关闭
    except (tarfile.TarError, OSError) as exc:
        raise RestoreError(f"备份归档不可读: {archive}（{exc}）") from exc
    try:
        try:
            member = tar.getmember("backup/manifest.json")
        except KeyError:
            raise RestoreError(f"归档缺少 manifest.json: {archive}") from None
        extracted = tar.extractfile(member)
        if extracted is None:
            raise RestoreError(f"归档内 manifest.json 不可读: {archive}")
        manifest = json.loads(extracted.read().decode("utf-8"))
        version = str(manifest.get("version", ""))
        if version not in SUPPORTED_MANIFEST_VERSIONS:
            raise RestoreError(f"不支持的备份协议版本: v{version}（支持: {sorted(SUPPORTED_MANIFEST_VERSIONS)}）")
        try:
            tar.getmember(f"backup/data/{_DB_BACKUP_NAME}")
        except KeyError:
            raise RestoreError(f"归档缺少数据库文件 data/{_DB_BACKUP_NAME}: {archive}") from None
        return tar, manifest
    except BaseException:
        tar.close()  # 异常路径释放句柄；成功路径由调用方在使用完毕后关闭
        raise


def inspect_backup(archive: Path) -> dict[str, Any]:
    """校验备份归档并返回 manifest 元信息（不执行还原）.

    Args:
        archive: ``.tar.gz`` 备份归档路径.

    Returns:
        manifest 字典（version / app_version / created_at / database / objects）.

    Raises:
        RestoreError: 归档不可读、manifest 缺失、协议版本不兼容或数据库文件缺失.
    """
    tar, manifest = _read_manifest(archive)
    tar.close()
    return manifest


def _restore_sqlite(extracted_dir: Path, target_db_path: Path) -> None:
    """用 SQLite backup API 把备份库页级覆盖到目标（目标被占用时依然成功）."""
    source = extracted_dir / "data" / _DB_BACKUP_NAME
    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(source))
    try:
        dest_conn = sqlite3.connect(str(target_db_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def _validate_incremental_base(manifest: dict[str, Any], base: Path | None) -> None:
    """增量归档还原前校验基线：必须提供、须为全量归档且文件名与 manifest 记录一致.

    Raises:
        RestoreError: 基线缺失、基线为增量归档或文件名与 manifest 记录不匹配.
    """
    objects_base_name = str(manifest["objects"].get("base", ""))
    if not objects_base_name:
        return
    if base is None:
        raise RestoreError(
            f"增量备份还原需提供基线归档（manifest 记录基线: {objects_base_name}），请通过 base 参数传入"
        )
    base_manifest = inspect_backup(base)
    if str(base_manifest["objects"].get("base", "")):
        raise RestoreError(f"基线归档须为全量归档（增量归档不含被跳过的对象）: {base}")
    if base.name != objects_base_name:
        raise RestoreError(f"基线归档不匹配: manifest 记录 {objects_base_name}，实际传入 {base.name}")


def restore_backup(
    archive: Path,
    *,
    include_objects: bool = True,
    database_url: str | None = None,
    objects_dir: Path | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """从备份归档完整还原数据库与对象存储.

    流程：校验归档（协议版本 / 数据库文件存在）→ SQLite backup API 覆盖目标库
    （不删除目标文件，服务运行中也可恢复）→ 解包 objects（内容寻址，同名覆盖幂等）→
    重置全局引擎/存储单例 → 还原后逐表行数与 manifest 比对，不一致抛 RestoreError。

    增量备份（manifest.objects.base 非空）：需通过 ``base`` 提供基线归档，
    先还原基线对象、再还原增量对象；数据库不受影响（增量备份中亦为全量快照）。

    Args:
        archive: ``.tar.gz`` 备份归档路径.
        include_objects: 是否还原 objects 对象目录.
        database_url: 覆盖配置中的数据库连接串（测试用）.
        objects_dir: 覆盖配置中的对象存储目录（测试用）.
        base: 增量备份的基线归档路径（文件名须与 manifest.objects.base 一致）.

    Returns:
        manifest 字典（含还原结果的行数校验依据）.

    Raises:
        RestoreError: 归档校验失败、目标数据库非 SQLite、基线缺失/不匹配或还原后行数校验不一致.
    """
    from iterd.core import database as dbmod
    from iterd.core import storage as stmod
    from iterd.core.config import get_settings

    settings = get_settings()
    db_url = database_url or settings.database_url
    obj_dir = objects_dir or settings.objects_dir

    if not db_url.startswith("sqlite"):
        raise RestoreError(f"还原目标仅支持 SQLite，当前 database_url: {db_url}")

    tar, manifest = _read_manifest(archive)
    if include_objects:
        _validate_incremental_base(manifest, base)
    objects_base_name = str(manifest["objects"].get("base", ""))

    temp_root = Path(tempfile.mkdtemp(prefix="iterd-restore-", dir=_ensure_tmp_dir(settings)))
    base_root: Path | None = None
    base_temp_root: Path | None = None
    try:
        tar.extractall(temp_root, filter="data")
    finally:
        tar.close()

    try:
        if objects_base_name and include_objects and base is not None:
            base_tar, _ = _read_manifest(base)
            base_temp_root = Path(tempfile.mkdtemp(prefix="iterd-restore-base-", dir=_ensure_tmp_dir(settings)))
            try:
                base_tar.extractall(base_temp_root, filter="data")
            finally:
                base_tar.close()
            base_root = base_temp_root / "backup"

        extracted = temp_root / "backup"
        _restore_sqlite(extracted, _resolve_sqlite_path(db_url))
        if include_objects:
            if base_root is not None and (base_root / _OBJECTS_DIR_NAME).is_dir():
                shutil.copytree(base_root / _OBJECTS_DIR_NAME, obj_dir, dirs_exist_ok=True)
            if (extracted / _OBJECTS_DIR_NAME).is_dir():
                shutil.copytree(extracted / _OBJECTS_DIR_NAME, obj_dir, dirs_exist_ok=True)
        dbmod.reset_database()
        stmod.reset_storage()
        logger.info("还原完成: %s → %s", archive, db_url)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        if base_temp_root is not None:
            shutil.rmtree(base_temp_root, ignore_errors=True)

    # 还原后校验：逐表行数与 manifest 比对，保证恢复数据零丢失
    conn = sqlite3.connect(str(_resolve_sqlite_path(db_url)))
    try:
        actual = _row_counts_of(conn)
    finally:
        conn.close()
    expected: dict[str, int] = manifest["database"].get("row_counts", {})
    mismatched = {
        table: (expected.get(table), actual.get(table))
        for table in set(expected) | set(actual)
        if expected.get(table) != actual.get(table)
    }
    if mismatched:
        raise RestoreError(f"还原后行数校验不一致: {mismatched}")
    return manifest


def auto_backup_if_due() -> Path | None:
    """serve 启动时的自动备份：距最近一次归档超过配置间隔才执行.

    Returns:
        本次创建的归档路径；未到期或被禁用时返回 None.

    Raises:
        BackupError: 备份过程中发生业务错误（由调用方决定是否中断启动）.
    """
    from iterd.core.config import get_settings

    settings = get_settings()
    if settings.backup_interval_hours <= 0:
        return None
    backup_dir = _ensure_backup_dir(settings.backup_dir)
    archives = sorted(backup_dir.glob(f"{_BACKUP_PREFIX}-*.tar.gz"), reverse=True)
    if archives:
        age_hours = (dt.datetime.now(dt.UTC).timestamp() - archives[0].stat().st_mtime) / 3600
        if age_hours < settings.backup_interval_hours:
            logger.info(
                "距上次备份 %.1f 小时，未到 %d 小时间隔，跳过自动备份", age_hours, settings.backup_interval_hours
            )
            return None
    logger.info("执行启动自动备份（间隔 %d 小时）", settings.backup_interval_hours)
    return create_backup()
