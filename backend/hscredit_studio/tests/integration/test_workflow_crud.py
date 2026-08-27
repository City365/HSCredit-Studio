"""集成测试 — 工作流 CRUD（占位：实际跑需要 testcontainers PG）."""

import pytest


# Phase 1.5 接入 testcontainers 后启用这些测试
@pytest.mark.skip(reason="需 testcontainers PG，跳过 Phase 1 验收")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_workflow():
    pass


@pytest.mark.skip(reason="需 testcontainers PG，跳过 Phase 1 验收")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_workflow_creates_new_version():
    pass


@pytest.mark.skip(reason="需 testcontainers PG，跳过 Phase 1 验收")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_workflow_soft_delete():
    pass


@pytest.mark.skip(reason="需 testcontainers PG，跳过 Phase 1 验收")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_workflow_with_definition():
    pass
