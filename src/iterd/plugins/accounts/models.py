"""accounts 数据模型：users / api_tokens.

三员角色参考 GB/T 22239 等级保护（对标 cndb accounts 设计）：
系统管理员 / 安全管理员 / 审计管理员，三员分立、相互制约；
user 为普通用户默认角色。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin, UidMixin


class UserRole(StrEnum):
    """用户角色枚举（三员 + 普通用户）.

    - system_admin: 系统管理员 — 系统配置、用户管理、项目管理
    - security_admin: 安全管理员 — 权限策略、访问控制
    - audit_admin: 审计管理员 — 审计日志查看、合规检查
    - user: 普通用户 — 默认角色，日常业务操作
    """

    SYSTEM_ADMIN = "system_admin"
    SECURITY_ADMIN = "security_admin"
    AUDIT_ADMIN = "audit_admin"
    USER = "user"

    @property
    def display_name(self) -> str:
        """角色中文显示名."""
        return {
            UserRole.SYSTEM_ADMIN: "系统管理员",
            UserRole.SECURITY_ADMIN: "安全管理员",
            UserRole.AUDIT_ADMIN: "审计管理员",
            UserRole.USER: "普通用户",
        }[self]


class User(Base, TimestampMixin, UidMixin):
    """用户表."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 三员角色字段（默认普通用户）
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.USER.value, index=True)


class ApiToken(Base, TimestampMixin):
    """API Token：仅存 SHA-256 哈希，明文只在创建时展示."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = ["ApiToken", "User", "UserRole"]
