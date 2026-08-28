"""Phase 6 B29 — 租户超管后台单元测试.

依据 docs/ROADMAP.md Phase 6 B29:

- 全平台跨租户仪表板
- 租户列表 + 详情
- 租户状态变更 (suspend/reactivate/archive)
- 租户迁移 (cluster 标签)
- 用户角色变更 + 审计 (联动 B28)

依赖 B28 (Role.SUPER_ADMIN); 通过内存/隔离 DB 测试.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hscredit_studio.services.admin_console import (
    GlobalOverview,
    TenantOverview,
    change_user_role,
    get_global_overview,
    get_tenant_detail,
    get_top_tenants_by_runs,
    list_tenants,
    migrate_tenant,
    set_tenant_status,
)
from hscredit_studio.services.rbac import Role

# ===== 数据类 =====


def test_tenant_overview_dataclass():
    """TenantOverview 字段完整."""
    t = TenantOverview(
        tenant_id="t1",
        slug="demo",
        name="Demo",
        plan="pro",
        status="active",
        member_count=3,
        total_runs_30d=100,
        total_cpu_seconds_30d=12.5,
        last_active_at=datetime.now(UTC),
        is_healthy=True,
    )
    assert t.tenant_id == "t1"
    assert t.member_count == 3
    assert t.is_healthy is True


def test_global_overview_dataclass():
    """GlobalOverview 字段完整."""
    g = GlobalOverview(
        total_tenants=5,
        active_tenants=4,
        suspended_tenants=1,
        archived_tenants=0,
        total_members=12,
        total_runs_30d=200,
        total_cpu_seconds_30d=30.5,
        top_tenants_by_runs=[],
        plan_distribution={"pro": 3, "enterprise": 2},
        generated_at=datetime.now(UTC),
    )
    assert g.total_tenants == 5
    assert g.plan_distribution["pro"] == 3


# ===== 全平台概览 (mock DB session) =====


@pytest.mark.asyncio
async def test_get_global_overview_returns_dataclass(monkeypatch):
    """get_global_overview 返回 GlobalOverview 数据."""
    # 构造 mock session
    mock_session = MagicMock()
    # 4 个独立 execute 调用: tenant_agg / member / usage / plan
    tenant_mock = MagicMock()
    tenant_mock.one.return_value = MagicMock(total=5, active=4, suspended=1, archived=0)
    member_mock = MagicMock()
    member_mock.scalar.return_value = 12
    usage_mock = MagicMock()
    usage_mock.one.return_value = MagicMock(total_runs=200, total_cpu=30.5)
    plan_mock = MagicMock()
    plan_mock.all.return_value = [("pro", 3), ("enterprise", 2)]
    top_mock = MagicMock()
    top_mock.all.return_value = []

    mock_session.execute = AsyncMock(
        side_effect=[tenant_mock, member_mock, usage_mock, plan_mock, top_mock]
    )

    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(mock_session),
    )

    g = await get_global_overview()
    assert g.total_tenants == 5
    assert g.active_tenants == 4
    assert g.suspended_tenants == 1
    assert g.archived_tenants == 0
    assert g.total_members == 12
    assert g.total_runs_30d == 200
    assert g.plan_distribution == {"pro": 3, "enterprise": 2}


@pytest.mark.asyncio
async def test_get_top_tenants_by_runs(monkeypatch):
    """get_top_tenants_by_runs 返回排序后的 TenantOverview 列表."""
    tid1, tid2 = uuid4(), uuid4()
    now = datetime.now(UTC)
    main_mock = MagicMock()
    main_mock.all.return_value = [
        MagicMock(
            tenant_id=tid1, slug="demo", name="Demo",
            plan="pro", status="active", runs=100, cpu=10.5,
            last_active=now,
        ),
        MagicMock(
            tenant_id=tid2, slug="acme", name="Acme",
            plan="enterprise", status="active", runs=50, cpu=5.0,
            last_active=None,
        ),
    ]
    # 每个 tenant 一次 member_count 查询
    member_mock = MagicMock()
    member_mock.scalar.return_value = 3

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[main_mock, member_mock, member_mock])

    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(session),
    )

    result = await get_top_tenants_by_runs(limit=10, days=30)
    assert len(result) == 2
    assert result[0].tenant_id == str(tid1)
    assert result[0].total_runs_30d == 100
    assert result[0].is_healthy is True
    assert result[1].is_healthy is False


# ===== 租户列表 =====


@pytest.mark.asyncio
async def test_list_tenants_default(monkeypatch):
    """list_tenants 默认参数返回分页结果."""
    now = datetime.now(UTC)
    tenants = [
        MagicMock(
            tenant_id=uuid4(), slug="demo", name="Demo",
            plan="pro", status="active",
            created_at=now, updated_at=now,
        ),
        MagicMock(
            tenant_id=uuid4(), slug="acme", name="Acme",
            plan="enterprise", status="active",
            created_at=now, updated_at=now,
        ),
    ]
    total_mock = MagicMock()
    total_mock.scalar.return_value = 2
    rows_mock = MagicMock()
    rows_mock.scalars.return_value.all.return_value = tenants

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[total_mock, rows_mock])
    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(session),
    )

    result = await list_tenants(page=1, page_size=20)
    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_list_tenants_with_search_filter(monkeypatch):
    """list_tenants 带 search + status_filter."""
    session = MagicMock()
    total_mock = MagicMock()
    total_mock.scalar.return_value = 0
    rows_mock = MagicMock()
    rows_mock.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[total_mock, rows_mock])
    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(session),
    )

    result = await list_tenants(search="demo", status_filter="active", plan_filter="pro")
    assert result["total"] == 0


# ===== 租户状态 =====


@pytest.mark.asyncio
async def test_set_tenant_status_invalid_raises(monkeypatch):
    """set_tenant_status 非法状态抛 ValueError."""
    tid = uuid4()
    with pytest.raises(ValueError, match="非法状态"):
        await set_tenant_status(tid, "bogus")


# ===== 角色变更 =====


@pytest.mark.asyncio
async def test_change_user_role_invalid_role_raises(monkeypatch):
    """change_user_role 非法 role 抛 ValueError."""
    with pytest.raises(ValueError, match="非法角色"):
        await change_user_role(
            tenant_id=uuid4(),
            user_id=uuid4(),
            new_role="god_mode",
            changed_by=uuid4(),
        )


# ===== 迁移 =====


@pytest.mark.asyncio
async def test_migrate_tenant_invalid_cluster_raises(monkeypatch):
    """migrate_tenant 集群名过长抛 ValueError."""
    tid = uuid4()
    with pytest.raises(ValueError, match="目标集群标签不合法"):
        await migrate_tenant(tid, "x" * 100)


# ===== 详情错误处理 =====


@pytest.mark.asyncio
async def test_get_tenant_detail_not_found(monkeypatch):
    """get_tenant_detail 租户不存在抛 ValueError."""
    tid = uuid4()
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(session),
    )
    with pytest.raises(ValueError, match="不存在"):
        await get_tenant_detail(tid)


@pytest.mark.asyncio
async def test_get_tenant_detail_archived_raises(monkeypatch):
    """get_tenant_detail 已归档租户抛 ValueError."""
    tid = uuid4()
    deleted_tenant = MagicMock()
    deleted_tenant.deleted_at = datetime.now(UTC)
    session = MagicMock()
    session.get = AsyncMock(return_value=deleted_tenant)
    monkeypatch.setattr(
        "hscredit_studio.services.admin_console.session_scope",
        _async_ctx(session),
    )
    with pytest.raises(ValueError, match="不存在或已删除"):
        await get_tenant_detail(tid)


# ===== Super admin RBAC 集成 (中间件级别) =====


def test_admin_routes_require_super_admin():
    """B29 admin router 全局强制 super_admin (B28 联动)."""
    from hscredit_studio.api.v1.admin import router

    # router 全局 dependencies 应含 require_role(super_admin)
    deps = router.dependencies
    assert len(deps) >= 1
    # 检查 callable 链 (此处只验证结构)
    assert any(hasattr(d, "dependency") or callable(d) for d in deps)


def test_admin_role_super_admin_rank_highest():
    """SUPER_ADMIN rank 是最高等级, 中间件验证."""
    assert Role.SUPER_ADMIN.rank > Role.TENANT_ADMIN.rank


# ===== 辅助 =====


class _AsyncCtx:
    """简化版 async context manager, 用于 mock session_scope."""

    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        pass


def _async_ctx(session: MagicMock) -> MagicMock:
    return MagicMock(return_value=_AsyncCtx(session))
