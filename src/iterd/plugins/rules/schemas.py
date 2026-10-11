"""rules Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleItemIn(BaseModel):
    """创建/更新规则入参."""

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    category: str = Field(pattern="^(drafting|tolerance|material|process)$")
    checker_type: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] | None = None
    severity_default: str = Field(default="warning", pattern="^(error|warning|info)$")
    enabled: bool = True
    description: str = ""


class RuleItemOut(RuleItemIn):
    """规则对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class RuleSetIn(BaseModel):
    """创建规则集入参."""

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    project_id: int | None = None
    rule_ids: list[int] = []


class RuleSetOut(BaseModel):
    """规则集对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    name: str
    description: str
    created_at: datetime


class RuleSetDetailOut(RuleSetOut):
    """规则集详情：含成员规则 id 列表."""

    rule_ids: list[int] = []


class RuleSetRuleIn(BaseModel):
    """规则集成员变更入参."""

    rule_ids: list[int] = []


class RuleSetBindIn(BaseModel):
    """规则集绑定入参."""

    rule_set_id: int


class RuleSetBindingOut(BaseModel):
    """迭代规则集绑定（未绑定时 rule_set_id 为 null）。"""

    iteration_id: int
    rule_set_id: int | None


class CheckRunIn(BaseModel):
    """发起批量检查入参."""

    rule_set_id: int


class CheckRunOut(BaseModel):
    """检查运行对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    iteration_id: int
    rule_set_id: int
    status: str
    summary: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    task_id: int | None = None


class CheckFindingOut(BaseModel):
    """发现项对外结构（规则与产物信息由服务层联表填充）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    check_run_id: int
    artifact_version_id: int
    rule_item_id: int
    severity: str
    location: str
    message: str
    rule_code: str = ""
    rule_name: str = ""
    artifact_code: str = ""
    artifact_name: str = ""
    version_no: int = 0
