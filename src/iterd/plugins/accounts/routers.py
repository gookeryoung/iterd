"""accounts 路由：登录 / 当前用户 / 用户管理 / API Token."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from iterd.api.deps import CurrentUser, SessionDep, require_superuser
from iterd.core.config import get_settings
from iterd.core.security import create_access_token
from iterd.plugins.accounts import schemas, services

router = APIRouter(prefix="/api/v1", tags=["auth"])
admin_router = APIRouter(prefix="/api/v1", tags=["admin"], dependencies=[Depends(require_superuser)])


@router.post("/auth/login", response_model=schemas.TokenOut)
async def login(body: schemas.LoginIn, session: SessionDep) -> schemas.TokenOut:
    """口令登录，返回 JWT."""
    user = await services.authenticate(session, body.username, body.password)
    token = create_access_token(user.uid, get_settings())
    return schemas.TokenOut(access_token=token, user=schemas.UserOut.model_validate(user))


@router.get("/auth/me", response_model=schemas.UserOut)
async def me(user: CurrentUser) -> schemas.UserOut:
    """当前登录用户."""
    return schemas.UserOut.model_validate(user)


@admin_router.get("/users", response_model=list[schemas.UserOut])
async def list_users(session: SessionDep) -> list[schemas.UserOut]:
    """用户列表（管理员）。"""
    users = await services.list_users(session)
    return [schemas.UserOut.model_validate(u) for u in users]


@admin_router.post("/users", response_model=schemas.UserOut, status_code=201)
async def create_user(body: schemas.UserCreate, session: SessionDep) -> schemas.UserOut:
    """创建用户（管理员）。"""
    created = await services.create_user(session, **body.model_dump())
    await session.commit()
    return schemas.UserOut.model_validate(created)


@router.post("/api-tokens", response_model=schemas.ApiTokenCreated, status_code=201)
async def create_api_token(
    body: schemas.ApiTokenCreate, user: CurrentUser, session: SessionDep
) -> schemas.ApiTokenCreated:
    """创建 API Token，明文仅返回一次."""
    token, raw = await services.create_api_token(session, user, body.name)
    await session.commit()
    out = schemas.ApiTokenCreated.model_validate(token, from_attributes=True)
    out.token = raw
    return out
