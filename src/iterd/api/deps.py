"""公共认证依赖：JWT / API Token 双通道，注入 request.state.user_id."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.config import get_settings
from iterd.core.database import get_session
from iterd.core.errors import IterdError
from iterd.core.security import decode_access_token, hash_api_token
from iterd.plugins.accounts.models import ApiToken, User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    """认证依赖：Bearer JWT 或 X-API-Token 头，返回当前用户."""
    user: User | None = None

    authorization = request.headers.get("Authorization")
    scheme, param = get_authorization_scheme_param(authorization or "")
    if scheme.lower() == "bearer" and param:
        uid = decode_access_token(param, get_settings())
        user = (await session.execute(select(User).where(User.uid == uid))).scalar_one_or_none()
    elif (api_token := request.headers.get("X-API-Token")) is not None:
        token_hash = hash_api_token(api_token)
        token = (await session.execute(select(ApiToken).where(ApiToken.token_hash == token_hash))).scalar_one_or_none()
        if token is not None:
            user = await session.get(User, token.user_id)

    if user is None or not user.is_active:
        raise IterdError("未认证或凭证无效", code="ITERD-UNAUTHORIZED", status_code=401)
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_superuser(user: CurrentUser) -> User:
    """超级管理员依赖."""
    if not user.is_superuser:
        raise IterdError("需要超级管理员权限", code="ITERD-PERMISSION_DENIED", status_code=403)
    return user
