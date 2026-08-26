"""多租户中间件 — 校验 URL ``{tenant_slug}`` 与 JWT ``tenant_slug`` 一致.

设计要点（见 ``docs/design/14-api-specification.md`` 14.5.2）：

1. **公开路径**（认证、健康检查、Prometheus 指标、OpenAPI 文档）跳过校验。
2. 解析 ``Authorization: Bearer <jwt>`` 头，无 / 非法 → ``401 E_AUTH_REQUIRED``。
3. ``decode_token`` 失败 → ``401 E_AUTH_INVALID``（含 ``WWW-Authenticate: Bearer``）。
4. ``type`` 不是 ``access`` → ``401 E_AUTH_TOKEN_TYPE``（防止误用 refresh token）。
5. URL ``tenant_slug`` ≠ JWT ``tenant_slug`` → ``403 E_TENANT_FORBIDDEN``。
6. 校验通过后注入 ``request.state``（``tenant_slug`` / ``tenant_id`` /
   ``user_id`` / ``role``）供下游 handler 使用。

注入顺序：在 ``RequestIDMiddleware`` 之后、在 ``SecurityHeadersMiddleware`` /
``GZipMiddleware`` 之前（main.py 注册顺序保证）。
"""

from __future__ import annotations

import re

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from hscredit_studio.core.security import decode_token

# URL path 中包含 ``/{tenant_slug}/`` 的 API 路径（不区分大小写）
_TENANT_PATH_PATTERN = re.compile(
    r"^/api/v\d+/([a-z0-9-]+)(/|$)",
    re.IGNORECASE,
)

# 公开路径（无需 tenant 校验）
_PUBLIC_PATHS: tuple[str, ...] = (
    "/api/v1/auth/",
    "/api/v1/healthz",
    "/api/v1/readyz",
    "/api/v1/openapi.json",
    "/metrics",
    "/api/docs",
    "/api/redoc",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """校验 URL tenant_slug 与 JWT tenant_slug 一致的多租户中间件."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 1. 公开路径直接放行
        if any(path.startswith(p) for p in _PUBLIC_PATHS):
            return await call_next(request)

        # 2. 提取 URL 中的 tenant_slug
        m = _TENANT_PATH_PATTERN.match(path)
        if m is None:
            # 非 tenant 路径（如根路径 ``/``、metrics 等），不强制
            return await call_next(request)
        tenant_slug = m.group(1)

        # 3. 解析 Authorization 头
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "code": "E_AUTH_REQUIRED",
                    "message": "缺少或非法的 Authorization 头",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = auth_header[len("Bearer "):]

        # 4. 解码 JWT
        try:
            payload = decode_token(token)
        except (ValueError, JWTError) as e:
            return JSONResponse(
                status_code=401,
                content={
                    "code": "E_AUTH_INVALID",
                    "message": f"Token 无效: {e}",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 5. 必须为 access token（防止误用 refresh token 访问 API）
        if payload.get("type") != "access":
            return JSONResponse(
                status_code=401,
                content={
                    "code": "E_AUTH_TOKEN_TYPE",
                    "message": "需要 access token",
                },
            )

        # 6. 校验 URL tenant_slug 与 JWT tenant_slug 一致
        token_tenant = payload.get("tenant_slug")
        if token_tenant != tenant_slug:
            return JSONResponse(
                status_code=403,
                content={
                    "code": "E_TENANT_FORBIDDEN",
                    "message": f"Token 不属于租户 {tenant_slug}",
                },
            )

        # 7. 注入 request.state 供下游 handler / deps 使用
        request.state.tenant_slug = tenant_slug
        request.state.tenant_id = payload.get("tenant_id")
        request.state.user_id = payload.get("sub")
        request.state.role = payload.get("role")

        return await call_next(request)