"""安全工具：口令哈希（bcrypt）、JWT、API Token 哈希."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from iterd.core.config import Settings
from iterd.core.errors import IterdError


def hash_password(raw: str) -> str:
    """生成 bcrypt 口令哈希."""
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    """校验口令与哈希是否匹配."""
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, settings: Settings) -> str:
    """签发 JWT，subject 为用户 uid."""
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str:
    """解析 JWT，返回用户 uid；无效或过期抛 401."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise IterdError("凭证无效或已过期", code="ITERD-UNAUTHORIZED", status_code=401) from exc
    sub = payload.get("sub")
    if not sub:
        raise IterdError("凭证无效或已过期", code="ITERD-UNAUTHORIZED", status_code=401)
    return str(sub)


def hash_api_token(raw: str) -> str:
    """API Token 仅存 SHA-256 哈希，明文只在创建时展示一次."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    """常量时间字符串比较（防时序攻击）."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
