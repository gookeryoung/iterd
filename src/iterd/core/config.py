"""iterd 应用配置：pydantic-settings，环境变量前缀 ITERD_.

路径约定（对齐 cndb 的数据目录设计理念）：
- HOME_DIR：用户主目录（~），全局持久化数据根目录的宿主。
- DATA_DIR：用户可写数据根目录，统一为 ~/.iterd；
  ITERD_DATA_DIR 环境变量可整体覆盖（测试隔离 / 便携部署场景），
  覆盖后其下所有子目录与默认 DATABASE_URL 一并切换（子目录不可经 .env 设置，
  否则与整体覆盖语义冲突）。下分子目录职责：
  - CONFIG_DIR:   配置文件（.env，ITERD_ 前缀环境变量的落地文件）
  - DATABASE_DIR: SQLite 数据库文件（iterd.db）
  - OBJECTS_DIR:  产物内容寻址存储（objects/{sha256[:2]}/{sha256}，版本不可变）
  - BACKUP_DIR:   备份归档默认输出目录
  - TMP_DIR:      运行时临时文件（备份拼装、上传暂存等，可随时清空）
  - CACHE_DIR:    运行时缓存（可随时清空，删除不影响正确性）
  - LOG_DIR:      日志文件
- 包内 static/（前端构建产物）为只读资源，随包分发，不入数据目录。

权限要求：数据根目录应仅当前用户可读写（Windows 继承用户 Profile 的 ACL；
POSIX 建议对 ~/.iterd 执行 chmod 700）。
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BACKUP_DIR",
    "CACHE_DIR",
    "CONFIG_DIR",
    "DATABASE_DIR",
    "DATA_DIR",
    "HOME_DIR",
    "LOG_DIR",
    "OBJECTS_DIR",
    "TMP_DIR",
    "Settings",
    "get_settings",
    "reset_settings",
]

HOME_DIR = Path.home()

# 用户可写数据根目录：默认 ~/.iterd，ITERD_DATA_DIR 整体覆盖（导入期读环境变量，
# .env 中设置 ITERD_DATA_DIR 无效 —— 配置文件自身的位置依赖该值，存在先后依赖）
DATA_DIR = Path(os.environ.get("ITERD_DATA_DIR") or (HOME_DIR / ".iterd"))

CONFIG_DIR = DATA_DIR / "config"
DATABASE_DIR = DATA_DIR / "data"
OBJECTS_DIR = DATA_DIR / "objects"
BACKUP_DIR = DATA_DIR / "backups"
TMP_DIR = DATA_DIR / "tmp"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"

# 子目录名 → Settings 字段名映射（供整体覆盖时派生子目录路径）
_SUBDIR_FIELDS: dict[str, str] = {
    "config_dir": "config",
    "database_dir": "data",
    "objects_dir": "objects",
    "backup_dir": "backups",
    "tmp_dir": "tmp",
    "cache_dir": "cache",
    "log_dir": "logs",
}

# 首次导入即创建默认数据目录树（打包 / 开发 / wheel 安装模式一致），
# 保证 serve / seed / worker 首次运行时 SQLite 有可写的父目录
for _d in (DATA_DIR, CONFIG_DIR, DATABASE_DIR, OBJECTS_DIR, BACKUP_DIR, TMP_DIR, CACHE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """全局配置，全部可用 ITERD_ 前缀环境变量覆盖."""

    model_config = SettingsConfigDict(env_prefix="ITERD_", env_file=str(CONFIG_DIR / ".env"), extra="ignore")

    app_name: str = "iterd"
    debug: bool = False

    # 数据库：SQLite 默认（位于 DATABASE_DIR），生产切 PostgreSQL（ITERD_DATABASE_URL）
    database_url: str = f"sqlite+aiosqlite:///{DATABASE_DIR / 'iterd.db'}"

    # 数据目录（~/.iterd，ITERD_DATA_DIR 整体覆盖后子目录与数据库一并切换）
    data_dir: Path = DATA_DIR
    config_dir: Path = CONFIG_DIR
    database_dir: Path = DATABASE_DIR
    objects_dir: Path = OBJECTS_DIR
    backup_dir: Path = BACKUP_DIR
    tmp_dir: Path = TMP_DIR
    cache_dir: Path = CACHE_DIR
    log_dir: Path = LOG_DIR

    # 安全
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # 任务：内置 worker（API 进程内）开关；独立部署时关闭并用 `iterd worker`
    task_worker_in_app: bool = True
    task_heartbeat_timeout: int = 60
    task_max_attempts: int = 3

    # SQLite 并发参数：WAL 模式下写锁等待上限（毫秒），缓解多 worker 并发写锁冲突
    sqlite_busy_timeout_ms: int = 5000

    # 备份：serve 启动时距上次归档超过间隔自动执行一次；0 关闭自动备份
    backup_interval_hours: int = 24
    backup_keep: int = 30  # 备份目录最大保留归档数，超出按时间从旧到新清理

    # 初始管理员（seed 时使用）
    admin_username: str = "admin"
    admin_password: str = "admin1234"

    host: str = "0.0.0.0"
    port: int = 8000

    @model_validator(mode="before")
    @classmethod
    def _derive_dirs(cls, values: object) -> object:
        """data_dir 整体覆盖时派生子目录与默认数据库路径（未显式给出的字段）."""
        if not isinstance(values, dict) or values.get("data_dir") is None:
            return values
        root = Path(str(values["data_dir"]))
        for field_name, subdir in _SUBDIR_FIELDS.items():
            values.setdefault(field_name, root / subdir)
        values.setdefault("database_url", f"sqlite+aiosqlite:///{root / 'iterd.db'}")
        return values


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回全局配置（首次调用时从环境加载，此后复用单例）."""
    global _settings  # noqa: PLW0603 - 模块级单例
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(settings: Settings | None = None) -> None:
    """重置配置单例（测试用：注入自定义配置或置空以便重新加载）."""
    global _settings  # noqa: PLW0603 - 模块级单例
    _settings = settings
