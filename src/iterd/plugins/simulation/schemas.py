"""simulation Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimTemplateIn(BaseModel):
    """创建仿真模板入参."""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    solver_type: str = Field(min_length=1, max_length=64)
    project_id: int | None = None
    params: dict[str, Any] | None = None
    thresholds: dict[str, Any] | None = None
    description: str = ""
    enabled: bool = True


class SimTemplateUpdateIn(BaseModel):
    """更新仿真模板入参（部分更新，solver_type 变更时重新校验求解器已注册）."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    solver_type: str | None = Field(default=None, min_length=1, max_length=64)
    params: dict[str, Any] | None = None
    thresholds: dict[str, Any] | None = None
    description: str | None = None
    enabled: bool | None = None


class SimTemplateOut(BaseModel):
    """仿真模板对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    code: str
    name: str
    solver_type: str
    params: dict[str, Any] | None
    thresholds: dict[str, Any] | None
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SimJobIn(BaseModel):
    """发起仿真作业入参."""

    template_id: int
    artifact_version_id: int | None = None
    inputs: dict[str, Any] | None = None


class SimJobOut(BaseModel):
    """仿真作业对外结构（template_name 由服务层填充）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    iteration_id: int
    template_id: int
    artifact_version_id: int | None
    status: str
    inputs: dict[str, Any] | None
    summary: dict[str, Any] | None
    error: str | None
    created_by: int | None
    started_at: datetime | None
    finished_at: datetime | None
    task_id: int | None = None
    template_name: str = ""
    solver_type: str = ""
    artifact_code: str = ""
    version_no: int | None = None


class SimResultOut(BaseModel):
    """仿真结果对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sim_job_id: int
    metrics: dict[str, Any] | None
    verdict: str
    failures: int
    detail: list[dict[str, Any]] | None
    created_at: datetime
