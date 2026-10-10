"""业务异常与全局错误处理."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class IterdError(Exception):
    """业务异常基类：统一映射为 `{"detail", "code"}` 响应契约."""

    status_code = 400
    code = "ITERD-INVALID_STATE"

    def __init__(
        self,
        detail: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.context = context or {}


def not_found(detail: str = "资源不存在") -> IterdError:
    """统一 404 业务异常."""
    return IterdError(detail, code="ITERD-NOT_FOUND", status_code=404)


def permission_denied(detail: str = "无权限执行该操作") -> IterdError:
    """统一 403 业务异常."""
    return IterdError(detail, code="ITERD-PERMISSION_DENIED", status_code=403)


def register_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，路由层禁止裸 500."""

    @app.exception_handler(IterdError)
    async def handle_iterd_error(_request: Request, exc: IterdError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code, "context": exc.context},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "内部错误", "code": "ITERD-INTERNAL_ERROR"},
        )


Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]
