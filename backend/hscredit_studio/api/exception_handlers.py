"""全局异常 handler — 把所有异常统一转为 ``application/json`` 响应.

设计要点（见 ``docs/design/06-non-functional.md`` 6.4）：

- 自定义异常 → 根据 ``_STATUS_MAP`` 映射到对应 HTTP 状态码，
  body 字段 ``{code, message, details, timestamp, request_id}``。
- ``RequestValidationError``（Pydantic）→ ``400 E_VALIDATION_INPUT``，
  details 列表包含 field / message / code 三元组。
- ``StarletteHTTPException`` → 透传状态码，code 按 401/403/404/405 映射。
- 数据库错误：``IntegrityError`` → ``409 E_CONFLICT``；
  ``OperationalError`` / ``DBAPIError`` → ``503 E_DB_UNAVAILABLE``。
- ``ClientDisconnect`` → ``499``（nginx 客户端断连约定）。
- 兜底 ``Exception`` → ``500 E_INTERNAL``，记录 stack trace。
- 所有响应携带 ``request.state.request_id``（由 RequestIDMiddleware 注入），
  便于日志关联。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from hscredit_studio.core.exceptions import (
    AuthenticationError,
    DependencyError,
    FeatureNotFoundError,
    HSCreditWorkflowError,
    NodeExecutionError,
    NodeNotFoundError,
    NotFittedError,
    SerializationError,
    StateError,
    TenantForbiddenError,
    ValidationError,
    WorkflowParseError,
)
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)


# ===== HTTP 状态码映射 =====
_STATUS_MAP: dict[type[Exception], int] = {
    ValidationError: status.HTTP_400_BAD_REQUEST,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    TenantForbiddenError: status.HTTP_403_FORBIDDEN,
    FeatureNotFoundError: status.HTTP_404_NOT_FOUND,
    NodeNotFoundError: status.HTTP_404_NOT_FOUND,
    StateError: status.HTTP_409_CONFLICT,
    NotFittedError: status.HTTP_409_CONFLICT,
    WorkflowParseError: status.HTTP_400_BAD_REQUEST,
    NodeExecutionError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    DependencyError: status.HTTP_503_SERVICE_UNAVAILABLE,
    SerializationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}

# Starlette HTTPException → 中文错误码
_STARLETTE_CODE_MAP: dict[int, str] = {
    401: "E_AUTH_REQUIRED",
    403: "E_FORBIDDEN",
    404: "E_NOT_FOUND",
    405: "E_METHOD_NOT_ALLOWED",
    429: "E_RATE_LIMITED",
}


def _build_error_response(
    code: str,
    message: str,
    http_status: int,
    details: Any | None = None,
    request: Request | None = None,
) -> JSONResponse:
    """构造统一错误 JSON 响应体."""
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if details is not None:
        body["details"] = details
    if request is not None:
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            body["request_id"] = request_id
    return JSONResponse(status_code=http_status, content=body)


# ===== Handlers =====


async def hscredit_error_handler(
    request: Request,
    exc: HSCreditWorkflowError,
) -> JSONResponse:
    """处理所有 ``HSCreditWorkflowError`` 子类异常.

    根据 ``_STATUS_MAP`` 映射 HTTP 状态；5xx 记录 stack trace，
    4xx 仅 WARN。
    """
    http_status = _STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    if http_status >= 500:
        _log.exception(
            "server_error",
            extra={"err_code": exc.code, "err_message": str(exc)},
        )
    else:
        _log.warning(
            "client_error",
            extra={
                "err_code": exc.code,
                "err_message": str(exc),
                "path": request.url.path,
            },
        )
    return _build_error_response(exc.code, str(exc), http_status, exc.details, request)


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """处理 FastAPI Pydantic 校验错误 → ``400 E_VALIDATION_INPUT``."""
    errors: list[dict[str, Any]] = []
    for err in exc.errors():
        errors.append(
            {
                "field": ".".join(str(p) for p in err.get("loc", [])),
                "message": err.get("msg", ""),
                "code": err.get("type", ""),
            }
        )
    return _build_error_response(
        "E_VALIDATION_INPUT",
        "请求参数校验失败",
        status.HTTP_400_BAD_REQUEST,
        errors,
        request,
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """处理 ``StarletteHTTPException``，透传状态码并按状态码映射 error code."""
    code = _STARLETTE_CODE_MAP.get(exc.status_code, "E_HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "HTTP error"
    return _build_error_response(code, message, exc.status_code, None, request)


async def integrity_error_handler(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    """处理数据库完整性错误（唯一约束 / 外键冲突） → ``409 E_CONFLICT``."""
    _log.warning("db_integrity_error", extra={"error": str(exc.orig)})
    return _build_error_response(
        "E_CONFLICT",
        "数据冲突（唯一约束或外键）",
        status.HTTP_409_CONFLICT,
        {"db_error": str(exc.orig)[:500]},
        request,
    )


async def database_error_handler(
    request: Request,
    exc: OperationalError | DBAPIError,
) -> JSONResponse:
    """处理数据库不可用错误 → ``503 E_DB_UNAVAILABLE``."""
    _log.exception("db_unavailable", extra={"error": str(exc.orig)})
    return _build_error_response(
        "E_DB_UNAVAILABLE",
        "数据库暂时不可用",
        status.HTTP_503_SERVICE_UNAVAILABLE,
        None,
        request,
    )


async def client_disconnect_handler(
    request: Request,
    exc: ClientDisconnect,
) -> JSONResponse:
    """客户端断连 → ``499``（nginx 约定，不记录 stack trace）."""
    _log.info("client_disconnected", extra={"path": request.url.path})
    return _build_error_response(
        "E_CLIENT_DISCONNECTED",
        "客户端断连",
        499,
        None,
        request,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """兜底未捕获异常 → ``500 E_INTERNAL``（记录 stack trace）."""
    _log.exception(
        "unhandled_exception",
        extra={"error": str(exc), "path": request.url.path},
    )
    return _build_error_response(
        "E_INTERNAL",
        "服务器内部错误",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        None,
        request,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册所有异常 handler 到 FastAPI app.

    注册顺序：先注册子类 → 后注册基类 / 兜底。
    注意：FastAPI/Starlette 按 MRO 匹配，因此先注册具体的（子类），
    再注册通用的（基类），保证最具体的 handler 优先触发。

    但因为使用了 ``add_exception_handler`` 的精确类型匹配，
    本实现中顺序仅影响 ``Exception`` 兜底最后注册即可。
    """
    # 自定义异常（基类统一处理 13 个子类）
    app.add_exception_handler(HSCreditWorkflowError, hscredit_error_handler)
    # FastAPI / Pydantic 校验
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    # Starlette HTTPException（404 / 405 / 401 等）
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    # 数据库
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, database_error_handler)
    app.add_exception_handler(DBAPIError, database_error_handler)
    # 客户端断连
    app.add_exception_handler(ClientDisconnect, client_disconnect_handler)
    # 兜底
    app.add_exception_handler(Exception, unhandled_exception_handler)