"""集成测试 — Run 提交（占位）."""

import pytest


@pytest.mark.skip(reason="需 testcontainers + Celery worker")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_run_creates_node_executions():
    pass


@pytest.mark.skip(reason="需 testcontainers + Celery worker")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_run_with_duplicate_run_number():
    pass


@pytest.mark.skip(reason="需 testcontainers + Celery worker")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_run_in_running_state():
    pass
