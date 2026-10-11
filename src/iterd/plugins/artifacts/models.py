"""artifacts 数据模型：artifacts / artifact_versions / artifact_links.

不变量：artifact_versions 不可变（无 UPDATE 路径）；同内容版本共享存储对象。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin, UidMixin

CATEGORIES = ("drawing", "model", "spec", "manual", "result")
LINK_TYPES = ("part_of", "refers_to", "derived_from")


class Artifact(Base, TimestampMixin, UidMixin):
    """设计产物（图纸/模型/技术规范/仿真结果）。"""

    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_artifact_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    # use_alter：与 ArtifactVersion.artifact_id 构成循环外键，建表后单独添加约束（PG 必需）
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifact_versions.id", use_alter=True, name="fk_artifacts_current_version_id_artifact_versions"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)  # 软删


class ArtifactVersion(Base, TimestampMixin, UidMixin):
    """产物版本：不可变记录，指向内容寻址存储对象."""

    __tablename__ = "artifact_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(512), default="", nullable=False)


class ArtifactLink(Base, TimestampMixin):
    """产物关联：part_of / refers_to / derived_from."""

    __tablename__ = "artifact_links"
    __table_args__ = (UniqueConstraint("src_artifact_id", "dst_artifact_id", "link_type", name="uq_artifact_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True, nullable=False)
    dst_artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True, nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)


__all__ = ["Artifact", "ArtifactLink", "ArtifactVersion"]
