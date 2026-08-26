"""集成测试 — 认证 API（需 testcontainers 或本地 PG）.

Phase 1 默认 skip（无 PG 环境）；Phase 1.5 启用。
"""
import pytest


@pytest.mark.skip(reason="Phase 1 默认无 PG；Phase 1.5 接入 testcontainers 后启用")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """错误密码应返回 401."""
    from httpx import AsyncClient, ASGITransport
    from hscredit_studio.main import app
    from hscredit_studio.api.exception_handlers import register_exception_handlers
    register_exception_handlers(app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "wrong@example.com",
                "password": "wrongpassword",
                "tenant_slug": "nonexistent",
            },
        )
        assert response.status_code in (401, 503)  # 401 没用户，503 DB 不可用


@pytest.mark.skip(reason="Phase 1 默认无 PG；Phase 1.5 启用")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_validation_error():
    """缺字段应返回 400 E_VALIDATION_INPUT."""
    from httpx import AsyncClient, ASGITransport
    from hscredit_studio.main import app
    from hscredit_studio.api.exception_handlers import register_exception_handlers
    register_exception_handlers(app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/login", json={"email": "x@x.com"})
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "E_VALIDATION_INPUT"
        assert "details" in body