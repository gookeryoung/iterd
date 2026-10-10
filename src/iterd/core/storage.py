"""存储后端：StorageBackend 协议 + 本地内容寻址实现."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass
class StorageObject:
    """写入结果：对象大小与内容哈希."""

    size: int
    sha256: str


class StorageBackend(Protocol):
    """对象存储协议：对齐 boto3 接口子集，切换 MinIO 仅换实现."""

    def put(self, key: str, stream: BinaryIO) -> StorageObject:
        """写入对象（内容寻址，同内容天然去重），返回 size 与 sha256."""

    def open(self, key: str) -> BinaryIO:
        """读取对象，返回二进制流."""

    def delete(self, key: str) -> None:
        """删除对象（不存在时静默）."""

    def exists(self, key: str) -> bool:
        """对象是否存在."""

    def local_path(self, key: str) -> Path:
        """返回对象本地路径（local 实现用于零拷贝读取）."""


class LocalStorage:
    """本地内容寻址存储：{sha256[:2]}/{sha256}，版本不可变."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _object_path(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256

    def put(self, _key: str, stream: BinaryIO) -> StorageObject:
        data = stream.read()
        sha256 = hashlib.sha256(data).hexdigest()
        path = self._object_path(sha256)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            shutil.move(str(tmp), str(path))
        return StorageObject(size=len(data), sha256=sha256)

    def open(self, key: str) -> BinaryIO:
        return BytesIO(self._object_path(key).read_bytes())

    def delete(self, key: str) -> None:
        self._object_path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._object_path(key).exists()

    def local_path(self, key: str) -> Path:
        return self._object_path(key)


def get_storage() -> LocalStorage:
    """返回全局本地存储实例（按配置 objects_dir 初始化）。"""
    from iterd.core.config import get_settings

    global _storage  # noqa: PLW0603 - 模块级单例
    if _storage is None:
        _storage = LocalStorage(get_settings().objects_dir)
    return _storage


_storage: LocalStorage | None = None


def reset_storage() -> None:
    """重置存储单例（测试用）."""
    global _storage  # noqa: PLW0603 - 模块级单例
    _storage = None
