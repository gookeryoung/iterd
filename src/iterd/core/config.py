"""应用配置：pydantic-settings，环境变量前缀 ITERD_."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，全部可用 ITERD_ 前缀环境变量覆盖."""

    model_config = SettingsConfigDict(env_prefix="ITERD_", env_file=".env", extra="ignore")

    app_name: str = "iterd"
    debug: bool = False

    # 数据库：SQLite 默认，生产切 PostgreSQL（ITERD_DATABASE_URL）
    database_url: str = "sqlite+aiosqlite:///./data/iterd.db"

    # 数据目录（对象存储根目录）
    data_dir: Path = Path("./data")

    # 安全
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 12 * 60

    # 任务：内置 worker（API 进程内）开关；独立部署时关闭并用 `iterd worker`
    task_worker_in_app: bool = True
    task_heartbeat_timeout: int = 60
    task_max_attempts: int = 3

    # 初始管理员（seed 时使用）
    admin_username: str = "admin"
    admin_password: str = "admin123"

    host: str = "0.0.0.0"
    port: int = 8000


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
