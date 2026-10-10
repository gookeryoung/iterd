"""accounts 服务层."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError
from iterd.core.security import hash_api_token, hash_password, verify_password
from iterd.plugins.accounts.models import ApiToken, User


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    """按用户名查询用户."""
    return (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()


async def create_user(
    session: AsyncSession, *, username: str, password: str, email: str = "", is_superuser: bool = False
) -> User:
    """创建用户；用户名重复抛 DUPLICATE_CODE。"""
    if await get_by_username(session, username) is not None:
        raise IterdError(f"用户名已存在: {username}", code="ITERD-DUPLICATE_CODE", status_code=400)
    user = User(username=username, email=email, is_superuser=is_superuser, hashed_password=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> User:
    """口令登录校验，失败统一 401（不区分用户不存在与口令错误）。"""
    user = await get_by_username(session, username)
    if user is None or not verify_password(password, user.hashed_password):
        raise IterdError("用户名或密码错误", code="ITERD-UNAUTHORIZED", status_code=401)
    if not user.is_active:
        raise IterdError("用户已被停用", code="ITERD-UNAUTHORIZED", status_code=401)
    return user


async def create_api_token(session: AsyncSession, user: User, name: str) -> tuple[ApiToken, str]:
    """创建 API Token，返回 (记录, 明文 token)——明文仅此一次."""
    raw = f"itk_{secrets.token_urlsafe(32)}"
    token = ApiToken(user_id=user.id, name=name, token_hash=hash_api_token(raw))
    session.add(token)
    await session.flush()
    return token, raw


async def list_users(session: AsyncSession) -> list[User]:
    """用户列表（管理用）。"""
    return list((await session.execute(select(User).order_by(User.id))).scalars())
