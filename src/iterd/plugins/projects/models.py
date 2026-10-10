"""projects 数据模型：projects / project_members / iterations / baselines."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iterd.models import Base, TimestampMixin, UidMixin


class Project(Base, TimestampMixin, UidMixin):
    """项目/子项目（parent_id 自关联，多级树）。"""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    children: Mapped[list[Project]] = relationship(back_populates="parent")
    parent: Mapped[Project | None] = relationship(back_populates="children", remote_side=[id])


class ProjectMember(Base, TimestampMixin):
    """项目成员与角色：viewer/designer/reviewer/admin/owner."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)


class Iteration(Base, TimestampMixin, UidMixin):
    """迭代：项目内 number 唯一，状态机 planned→active→closed."""

    __tablename__ = "iterations"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_iteration_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    objective: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="planned", nullable=False)


class Baseline(Base, TimestampMixin, UidMixin):
    """基线：锁定迭代内产物版本快照."""

    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class BaselineItem(Base, TimestampMixin):
    """基线条目：建立后不可变（无 UPDATE 路径）。"""

    __tablename__ = "baseline_items"
    __table_args__ = (UniqueConstraint("baseline_id", "artifact_id", name="uq_baseline_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    baseline_id: Mapped[int] = mapped_column(ForeignKey("baselines.id"), index=True, nullable=False)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), nullable=False)
    artifact_version_id: Mapped[int] = mapped_column(ForeignKey("artifact_versions.id"), nullable=False)


__all__ = ["Baseline", "BaselineItem", "Iteration", "Project", "ProjectMember"]
