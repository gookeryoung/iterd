"""rules 数据模型：规则库 / 规则集 / 检查运行 / 发现项."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin

RULE_CATEGORIES = ("drafting", "tolerance", "material", "process")
SEVERITIES = ("error", "warning", "info")


class RuleItem(Base, TimestampMixin):
    """规则条目：checker_type 对应检查器实现，params 为检查器参数."""

    __tablename__ = "rule_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    checker_type: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    severity_default: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)


class RuleSet(Base, TimestampMixin):
    """规则集：project_id 为空表示全局."""

    __tablename__ = "rule_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)


class RuleSetItem(Base, TimestampMixin):
    """规则集成员."""

    __tablename__ = "rule_set_items"
    __table_args__ = (UniqueConstraint("rule_set_id", "rule_item_id", name="uq_rule_set_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("rule_sets.id"), index=True, nullable=False)
    rule_item_id: Mapped[int] = mapped_column(ForeignKey("rule_items.id"), nullable=False)


class CheckRun(Base, TimestampMixin):
    """检查运行：状态机 pending/running/succeeded/failed，summary 为计数."""

    __tablename__ = "check_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("rule_sets.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CheckFinding(Base, TimestampMixin):
    """检查发现项：结构化报告记录（context 迭代级发现项无产物版本关联）."""

    __tablename__ = "check_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_run_id: Mapped[int] = mapped_column(ForeignKey("check_runs.id"), index=True, nullable=False)
    artifact_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("artifact_versions.id"), index=True, nullable=True
    )
    rule_item_id: Mapped[int] = mapped_column(ForeignKey("rule_items.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    location: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)


__all__ = ["CheckFinding", "CheckRun", "RuleItem", "RuleSet", "RuleSetItem"]
