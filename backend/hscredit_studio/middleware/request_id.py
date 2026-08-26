"""请求 ID 中间件 — 为每个请求生成 UUID 并注入请求上下文.

实现要点：

- 优先使用客户端传入的 ``X-Request-ID`` 头（便于跨服务追踪）；
  缺失时服务端生成 ``uuid4``。
- 写入 ``request.state.request_id``，供下游 handler / 日志使用。
- 响应头回显 ``X-Request-ID``。
- ``structlog`` 上下文绑定：当前项目日志模块为 stdlib ``logging`` + JSON formatter，
  因此仅保留 ``request.state`` 注入；如未来引入 structlog，
  调用 ``bind_contextvars`` 即可生效，无需改动调用方代码。
"""

from __future__ import annotations

import uuid
from types import TracebackType

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)

_HEADER = "X-Request-ID"


class _nullcontext:
    """极简无操作上下文管理器（当 logger 不支持 contextualize 时使用）."""

    def __enter__(self) -> "_nullcontext":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return False


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求注入唯一 ``X-Request-ID`` 并回显至响应头."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        # 兼容 stdlib logger（无 contextualize）
        cm: _nullcontext | object = (
            _log.contextualize(request_id=request_id)
            if hasattr(_log, "contextualize")
            else _nullcontext()
        )

        with cm:
            response = await call_next(request)

        response.headers[_HEADER] = request_id
        return response