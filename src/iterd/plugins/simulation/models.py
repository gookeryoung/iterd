"""simulation 数据模型：sim_templates / sim_jobs / sim_results.

不变量：sim_results 一作业一条（重跑覆盖写入），sim_jobs 状态机 pending→running→succeeded/failed。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin

SIM_JOB_STATUS = ("pending", "running", "succeeded", "failed")
SIM_VERDICT = ("pass", "fail")


class SimTemplate(Base, TimestampMixin):
    """仿真模板：项目级可复用的求解配置（project_id 为空表示全局）。"""

    __tablename__ = "sim_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    solver_type: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # 默认输入参数
    thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # {指标: {min/max}}
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class SimJob(Base, TimestampMixin):
    """仿真作业：迭代内一次求解执行，可选绑定产物版本作为被验证对象。"""

    __tablename__ = "sim_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("sim_templates.id"), index=True, nullable=False)
    artifact_version_id: Mapped[int | None] = mapped_column(ForeignKey("artifact_versions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    inputs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SimResult(Base, TimestampMixin):
    """仿真结果：指标值与按模板阈值的逐项评估（一作业一条，重跑覆盖）。"""

    __tablename__ = "sim_results"
    __table_args__ = (UniqueConstraint("sim_job_id", name="uq_sim_result_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sim_job_id: Mapped[int] = mapped_column(ForeignKey("sim_jobs.id"), index=True, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # {指标: 数值}
    verdict: Mapped[str] = mapped_column(String(8), default="fail", nullable=False)  # pass/fail
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # 逐项判定明细


__all__ = ["SIM_JOB_STATUS", "SIM_VERDICT", "SimJob", "SimResult", "SimTemplate"]
