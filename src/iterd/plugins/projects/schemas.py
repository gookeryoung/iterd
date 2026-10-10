"""projects Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectIn(BaseModel):
    """创建/更新项目入参."""

    parent_id: int | None = None
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    status: str = "active"


class ProjectOut(BaseModel):
    """项目对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    parent_id: int | None
    code: str
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class MemberIn(BaseModel):
    """添加/更新成员入参."""

    user_id: int
    role: str = Field(pattern="^(viewer|designer|reviewer|admin|owner)$")


class MemberOut(BaseModel):
    """成员对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    role: str


class IterationIn(BaseModel):
    """创建/更新迭代入参."""

    number: int | None = None
    title: str = Field(min_length=1, max_length=128)
    objective: str = ""
    start_date: date | None = None
    end_date: date | None = None
    status: str = Field(default="planned", pattern="^(planned|active|closed)$")


class IterationOut(BaseModel):
    """迭代对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    project_id: int
    number: int
    title: str
    objective: str
    start_date: date | None
    end_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime


class BaselineIn(BaseModel):
    """建立基线入参."""

    name: str = Field(min_length=1, max_length=128)


class BaselineItemOut(BaseModel):
    """基线条目对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    artifact_id: int
    artifact_version_id: int


class BaselineOut(BaseModel):
    """基线对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    iteration_id: int
    name: str
    created_by: int | None
    created_at: datetime


class BaselineDetailOut(BaselineOut):
    """基线详情：含版本快照条目."""

    items: list[BaselineItemOut] = []
