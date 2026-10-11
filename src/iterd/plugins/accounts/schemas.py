"""accounts Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    """用户对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    username: str
    email: str
    is_superuser: bool
    is_active: bool
    role: str


class UserCreate(BaseModel):
    """创建用户入参（role 取值见 UserRole：三员 + user）."""

    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    email: str = ""
    is_superuser: bool = False
    role: str = "user"


class LoginIn(BaseModel):
    """登录入参."""

    username: str
    password: str


class TokenOut(BaseModel):
    """登录结果."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ApiTokenCreate(BaseModel):
    """创建 API Token 入参."""

    name: str = Field(min_length=1, max_length=64)


class ApiTokenOut(BaseModel):
    """API Token 信息（不含哈希）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ApiTokenCreated(ApiTokenOut):
    """创建成功响应：明文 token 仅此一次返回."""

    token: str = ""
