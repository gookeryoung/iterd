"""SQLAlchemy 声明基类与公共 mixin."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_uid() -> str:
    """生成对外暴露的 UUID 字符串."""
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类，统一命名约定."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # eager_defaults：INSERT/UPDATE 后立即取回服务端生成字段，避免序列化时懒加载
    __mapper_args__ = {"eager_defaults": True}


class TimestampMixin:
    """公共时间戳字段：创建时间与更新时间（数据库端生成）."""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )


class UidMixin:
    """对外唯一标识 uid（uuid hex，全局唯一）."""

    uid: Mapped[str] = mapped_column(default=new_uid, unique=True, nullable=False, index=True)
