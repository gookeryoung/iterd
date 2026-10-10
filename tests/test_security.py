"""accounts 服务与安全工具单元测试."""

from __future__ import annotations

import pytest

from iterd.core.errors import IterdError
from iterd.core.security import (
    constant_time_equals,
    create_access_token,
    decode_access_token,
    hash_api_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_invalid_hash() -> None:
    assert not verify_password("x", "not-a-hash")


def test_api_token_hash() -> None:
    assert hash_api_token("abc") == hash_api_token("abc")
    assert hash_api_token("abc") != hash_api_token("abd")
    assert len(hash_api_token("abc")) == 64


def test_constant_time_equals() -> None:
    assert constant_time_equals("a", "a")
    assert not constant_time_equals("a", "b")


def test_jwt_roundtrip() -> None:
    from iterd.core.config import Settings

    settings = Settings(secret_key="k", jwt_expire_minutes=1)
    token = create_access_token("uid-1", settings)
    assert decode_access_token(token, settings) == "uid-1"


def test_jwt_expired() -> None:
    from datetime import UTC, datetime, timedelta

    from jose import jwt as jose_jwt

    from iterd.core.config import Settings

    settings = Settings(secret_key="k")
    expired = jose_jwt.encode({"sub": "u", "exp": datetime.now(UTC) - timedelta(hours=1)}, "k", algorithm="HS256")
    with pytest.raises(IterdError) as exc:
        decode_access_token(expired, settings)
    assert exc.value.status_code == 401


def test_jwt_missing_sub() -> None:
    from jose import jwt as jose_jwt

    from iterd.core.config import Settings

    settings = Settings(secret_key="k")
    with pytest.raises(IterdError):
        decode_access_token(jose_jwt.encode({"exp": 9999999999}, "k", algorithm="HS256"), settings)


def test_iterd_error_defaults() -> None:
    err = IterdError("oops")
    assert err.status_code == 400
    assert err.code == "ITERD-INVALID_STATE"
    assert err.context == {}
