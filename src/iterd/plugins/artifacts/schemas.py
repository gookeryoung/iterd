"""artifacts Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ArtifactIn(BaseModel):
    """创建产物入参."""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(pattern="^(drawing|model|spec|manual|result)$")
    description: str = ""
    metadata: dict[str, Any] | None = None


class ArtifactUpdate(BaseModel):
    """更新产物基本信息（不含版本）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    metadata: dict[str, Any] | None = None
    category: str | None = Field(default=None, pattern="^(drawing|model|spec|manual|result)$")


class ArtifactOut(BaseModel):
    """产物对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    project_id: int
    iteration_id: int
    code: str
    name: str
    category: str
    description: str
    current_version_id: int | None
    created_at: datetime
    updated_at: datetime


class ArtifactVersionOut(BaseModel):
    """版本对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    artifact_id: int
    version_no: int
    filename: str
    content_type: str
    size: int
    sha256: str
    metadata_json: dict[str, Any] | None = None
    uploaded_by: int | None
    note: str
    created_at: datetime


class ArtifactLinkIn(BaseModel):
    """创建关联入参."""

    dst_artifact_id: int
    link_type: str = Field(pattern="^(part_of|refers_to|derived_from)$")


class ReviewFindingOut(BaseModel):
    """项目审查状态聚合中的单条发现项."""

    id: int
    check_run_id: int
    artifact_version_id: int
    version_no: int
    rule_id: int
    rule_code: str
    rule_name: str
    severity: str
    location: str
    message: str


class ArtifactReviewStatusOut(BaseModel):
    """项目级产物审查状态聚合（版本感知：passed/failed/running/unreviewed/stale）."""

    artifact_id: int
    code: str
    name: str
    category: str
    iteration_id: int
    current_version_id: int | None
    status: str
    check_run_id: int | None = None
    check_run_status: str | None = None
    last_checked_at: datetime | None = None
    last_check_started_at: datetime | None = None
    findings: list[ReviewFindingOut] = []


class ProjectLinkOut(BaseModel):
    """项目级产物关联边（两端点均在项目内）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    src_artifact_id: int
    dst_artifact_id: int
    link_type: str


class ArtifactLinkOut(BaseModel):
    """关联对外结构（对端产物编码/名称由路由层联表填充）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    src_artifact_id: int
    dst_artifact_id: int
    link_type: str
    src_code: str = ""
    src_name: str = ""
    dst_code: str = ""
    dst_name: str = ""
