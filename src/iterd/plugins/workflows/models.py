"""workflows 数据模型：审查模板 / 审查运行 / 流水线作业.

不变量：运行固化模板快照（definition 与 with 引用解析结果）；
作业状态机 pending→running→succeeded/failed/skipped；conclusion 仅终态有值。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin

JOB_TYPES = ("rules", "simulation")
JOB_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
CONCLUSIONS = ("success", "failure", "skipped")
RUN_STATUSES = ("pending", "running", "succeeded", "failed")
STEP_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
TRIGGERS = ("submission", "manual", "rerun")
# 平台内置步骤序列：job_type → ((step_key, 步骤名), ...)（作业创建时同步生成）
JOB_STEP_SEQUENCES: dict[str, tuple[tuple[str, str], ...]] = {
    "rules": (("setup", "解析配置"), ("check", "执行规则检查"), ("report", "判定结论")),
    "simulation": (("setup", "解析配置"), ("solve", "执行仿真"), ("evaluate", "阈值判定")),
}


class WorkflowTemplate(Base, TimestampMixin):
    """审查模板：YAML 编排的迭代审查流水线定义（project_id 为空表示全局）。"""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class WorkflowRun(Base, TimestampMixin):
    """审查运行：模板在迭代上的一次执行（definition 为发起时快照）。"""

    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    workflow_code: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("iteration_submissions.id"), index=True, nullable=True)
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IterationSubmission(Base, TimestampMixin):
    """提交方案：设计者提交迭代方案的触发事件（每个启用模板各产生一条运行）。"""

    __tablename__ = "iteration_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class WorkflowJob(Base, TimestampMixin):
    """流水线作业：运行内一个环节（静态规则检查 / 动态仿真测试）。

    config 为发起时解析固化的执行入参（规则集/仿真模板/产物版本 id 等）；
    needs 门禁：上游任一非 success → 本作业 skipped。
    """

    __tablename__ = "workflow_jobs"
    __table_args__ = (UniqueConstraint("run_id", "job_key", name="uq_workflow_job_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True, nullable=False)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)
    needs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(16), nullable=True)
    check_run_id: Mapped[int | None] = mapped_column(ForeignKey("check_runs.id"), nullable=True)
    sim_job_id: Mapped[int | None] = mapped_column(ForeignKey("sim_jobs.id"), nullable=True)
    logs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowJobStep(Base, TimestampMixin):
    """流水线步骤：作业内平台内置执行环节（setup/执行/判定 三段）。

    状态机 pending→running→succeeded/failed/skipped；任一步骤 failure → 后续步骤 skipped。
    logs 行结构 {ts: 相对作业开始秒数, level: info|warning|error, message}。
    """

    __tablename__ = "workflow_job_steps"
    __table_args__ = (UniqueConstraint("job_id", "step_key", name="uq_workflow_job_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("workflow_jobs.id"), index=True, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(16), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    logs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = [
    "CONCLUSIONS",
    "JOB_STATUSES",
    "JOB_STEP_SEQUENCES",
    "JOB_TYPES",
    "RUN_STATUSES",
    "STEP_STATUSES",
    "TRIGGERS",
    "IterationSubmission",
    "WorkflowJob",
    "WorkflowJobStep",
    "WorkflowRun",
    "WorkflowTemplate",
]
