"""workflows Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowIn(BaseModel):
    """创建审查模板入参."""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    project_id: int | None = None
    definition: str = Field(min_length=1)
    enabled: bool = True


class WorkflowUpdateIn(BaseModel):
    """更新审查模板入参（部分更新，definition 变更时重新校验）."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    definition: str | None = None
    enabled: bool | None = None


class WorkflowJobDefOut(BaseModel):
    """解析后的作业定义结构（模板详情展示）."""

    key: str
    name: str
    uses: str
    needs: list[str] = []
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")

    model_config = ConfigDict(populate_by_name=True)


class WorkflowOut(BaseModel):
    """审查模板对外结构（含解析后 jobs）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    code: str
    name: str
    description: str
    definition: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    jobs: list[WorkflowJobDefOut] = []


class WorkflowRunIn(BaseModel):
    """发起审查运行入参."""

    workflow_id: int


class SubmissionIn(BaseModel):
    """提交迭代方案入参."""

    title: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=1024)


class WorkflowJobStepOut(BaseModel):
    """流水线步骤对外结构（logs 行含相对时间戳与级别）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    step_key: str
    name: str
    status: str
    conclusion: str | None
    order_index: int
    logs: list[dict[str, Any]] | None
    started_at: datetime | None
    finished_at: datetime | None


class SubmissionOut(BaseModel):
    """提交方案对外结构（嵌触发产生的运行概要）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    iteration_id: int
    title: str
    note: str
    submitted_by: int | None
    created_at: datetime
    runs: list[WorkflowRunOut] = []


class WorkflowRunOut(BaseModel):
    """审查运行对外结构（含作业概要）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    iteration_id: int
    workflow_id: int
    workflow_code: str
    definition: str
    status: str
    summary: dict[str, Any] | None
    created_by: int | None
    submission_id: int | None
    trigger: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    task_id: int | None = None
    submission_title: str = ""
    jobs: list[WorkflowJobOut] = []


class WorkflowJobOut(BaseModel):
    """流水线作业对外结构（绑定展示字段与步骤由服务层填充）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    job_key: str
    name: str
    job_type: str
    needs: list[str] | None
    config: dict[str, Any] | None
    status: str
    conclusion: str | None
    check_run_id: int | None
    sim_job_id: int | None
    logs: list[dict[str, Any]] | None
    order_index: int
    started_at: datetime | None
    finished_at: datetime | None
    rule_set_name: str = ""
    template_code: str = ""
    template_name: str = ""
    solver_type: str = ""
    artifact_code: str = ""
    version_no: int | None = None
    steps: list[WorkflowJobStepOut] = []


class ProjectRunItemOut(BaseModel):
    """项目级审查运行列表项（跨迭代汇总，下钻复用运行详情）."""

    id: int
    iteration_id: int
    iteration_number: int
    iteration_title: str
    workflow_id: int
    workflow_code: str
    status: str
    summary: dict[str, Any] | None
    trigger: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class ApprovalIn(BaseModel):
    """审批签署入参."""

    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=1024)


class ApprovalRecordOut(BaseModel):
    """审批记录对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    run_id: int
    approver_id: int
    approver_name: str
    decision: str
    comment: str
    created_at: datetime


class ApprovalEntryOut(BaseModel):
    """待审批列表内嵌审批意见."""

    approver_name: str
    decision: str
    comment: str
    created_at: datetime


class PendingApprovalOut(BaseModel):
    """待审批作业列表项（跨运行汇总）."""

    job_id: int
    run_id: int
    workflow_code: str
    iteration_id: int
    project_id: int
    job_key: str
    job_name: str
    approvers: list[str]
    min_count: int
    approved_count: int
    approvals: list[ApprovalEntryOut] = []
    can_approve: bool
    created_at: datetime
