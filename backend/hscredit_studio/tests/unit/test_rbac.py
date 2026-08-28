"""Phase 6 B28 — RBAC 细化单元测试.

依据 docs/ROADMAP.md Phase 6 B28 验收:

- 5 角色: super_admin / tenant_admin / analyst / viewer / none
- 5 资源 × 3 动作 矩阵
- check_permission / permission_decision / normalize_role
- role_at_least / menu_for_role
- viewer POST /workflows 应被拒绝 (集成中间件)
"""
from __future__ import annotations

import pytest

from hscredit_studio.services.rbac import (
    LEGACY_TO_ROLE,
    MENU_REQUIREMENTS,
    PERMISSION_MATRIX,
    Action,
    Resource,
    Role,
    check_permission,
    menu_for_role,
    normalize_role,
    permission_decision,
    role_at_least,
)

# ===== 角色枚举 =====


def test_role_enum_values():
    """Role 枚举包含 5 个角色值."""
    assert {r.value for r in Role} == {
        "super_admin",
        "tenant_admin",
        "analyst",
        "viewer",
        "none",
    }


def test_role_rank_order():
    """Role.rank 严格递减 (权限等级)."""
    assert Role.SUPER_ADMIN.rank > Role.TENANT_ADMIN.rank
    assert Role.TENANT_ADMIN.rank > Role.ANALYST.rank
    assert Role.ANALYST.rank > Role.VIEWER.rank
    assert Role.VIEWER.rank > Role.NONE.rank


# ===== Action 枚举 =====


def test_action_enum_values():
    """Action 枚举包含 3 个动作值."""
    assert {a.value for a in Action} == {"read", "write", "admin"}


def test_action_rank_order():
    """Action.rank: read < write < admin."""
    assert Action.READ.rank < Action.WRITE.rank
    assert Action.WRITE.rank < Action.ADMIN.rank


# ===== Resource 枚举 =====


def test_resource_enum_values():
    """Resource 枚举包含 5 个资源."""
    assert {r.value for r in Resource} == {
        "workflow",
        "run",
        "model",
        "template",
        "billing",
    }


# ===== 权限矩阵覆盖 =====


def test_permission_matrix_complete():
    """PERMISSION_MATRIX 必须覆盖全部 5 角色 × 5 资源 = 25 个组合."""
    assert set(PERMISSION_MATRIX.keys()) == set(Role)
    for role in Role:
        assert set(PERMISSION_MATRIX[role].keys()) == set(Resource), f"{role} 资源不全"


def test_permission_matrix_super_admin_full():
    """SUPER_ADMIN: 全部资源 = ADMIN."""
    for resource in Resource:
        assert PERMISSION_MATRIX[Role.SUPER_ADMIN][resource] == Action.ADMIN


def test_permission_matrix_tenant_admin_full():
    """TENANT_ADMIN: 全部资源 = ADMIN (与 super_admin 同权限, 仅作用域不同)."""
    for resource in Resource:
        assert PERMISSION_MATRIX[Role.TENANT_ADMIN][resource] == Action.ADMIN


def test_permission_matrix_analyst_write_business():
    """ANALYST: workflow/run/model = WRITE, billing/template = READ."""
    assert PERMISSION_MATRIX[Role.ANALYST][Resource.WORKFLOW] == Action.WRITE
    assert PERMISSION_MATRIX[Role.ANALYST][Resource.RUN] == Action.WRITE
    assert PERMISSION_MATRIX[Role.ANALYST][Resource.MODEL] == Action.WRITE
    assert PERMISSION_MATRIX[Role.ANALYST][Resource.BILLING] == Action.READ
    assert PERMISSION_MATRIX[Role.ANALYST][Resource.TEMPLATE] == Action.READ


def test_permission_matrix_viewer_read_only():
    """VIEWER: 全部资源 = READ."""
    for resource in Resource:
        assert PERMISSION_MATRIX[Role.VIEWER][resource] == Action.READ


def test_permission_matrix_none_empty():
    """NONE: 全部资源 = None (拒绝)."""
    for resource in Resource:
        assert PERMISSION_MATRIX[Role.NONE][resource] is None


# ===== check_permission =====


def test_check_permission_viewer_read_workflow():
    """viewer + read workflow = True (Phase 6 B28 验收)."""
    assert check_permission(Role.VIEWER, Resource.WORKFLOW, Action.READ) is True


def test_check_permission_viewer_write_workflow_denied():
    """viewer + write workflow = False (Phase 6 B28 验收: viewer POST /workflows → 403)."""
    assert check_permission(Role.VIEWER, Resource.WORKFLOW, Action.WRITE) is False


def test_check_permission_viewer_admin_billing_denied():
    """viewer + admin billing = False."""
    assert check_permission(Role.VIEWER, Resource.BILLING, Action.ADMIN) is False


def test_check_permission_analyst_write_workflow_allowed():
    """analyst + write workflow = True."""
    assert check_permission(Role.ANALYST, Resource.WORKFLOW, Action.WRITE) is True


def test_check_permission_analyst_admin_billing_denied():
    """analyst + admin billing = False (B28 验收要点)."""
    assert check_permission(Role.ANALYST, Resource.BILLING, Action.ADMIN) is False


def test_check_permission_analyst_write_billing_denied():
    """analyst + write billing = False."""
    assert check_permission(Role.ANALYST, Resource.BILLING, Action.WRITE) is False


def test_check_permission_tenant_admin_all():
    """tenant_admin 任何资源任何动作均 True."""
    for resource in Resource:
        for action in Action:
            assert check_permission(Role.TENANT_ADMIN, resource, action) is True


def test_check_permission_none_always_false():
    """none 任何组合 = False."""
    for resource in Resource:
        for action in Action:
            assert check_permission(Role.NONE, resource, action) is False


# ===== permission_decision =====


def test_permission_decision_allowed_reason_empty():
    """allowed=True 时 reason 为空."""
    allowed, reason = permission_decision(Role.VIEWER, Resource.WORKFLOW, Action.READ)
    assert allowed is True
    assert reason == ""


def test_permission_decision_denied_with_reason():
    """denied 时 reason 含原因."""
    allowed, reason = permission_decision(Role.VIEWER, Resource.WORKFLOW, Action.WRITE)
    assert allowed is False
    assert "viewer" in reason
    assert "workflow" in reason


# ===== role_at_least =====


def test_role_at_least_self():
    """自己 ≥ 自己 = True."""
    for role in Role:
        assert role_at_least(role, role) is True


def test_role_at_least_higher():
    """super_admin ≥ viewer = True."""
    assert role_at_least(Role.SUPER_ADMIN, Role.VIEWER) is True
    assert role_at_least(Role.TENANT_ADMIN, Role.ANALYST) is True


def test_role_at_least_lower():
    """viewer ≥ super_admin = False."""
    assert role_at_least(Role.VIEWER, Role.SUPER_ADMIN) is False
    assert role_at_least(Role.ANALYST, Role.TENANT_ADMIN) is False


# ===== normalize_role =====


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("owner", Role.TENANT_ADMIN),
        ("admin", Role.TENANT_ADMIN),
        ("analyst", Role.ANALYST),
        ("viewer", Role.VIEWER),
        ("super_admin", Role.SUPER_ADMIN),
        ("tenant_admin", Role.TENANT_ADMIN),
        ("TENANT_ADMIN", Role.TENANT_ADMIN),  # 大小写不敏感
        ("  viewer  ", Role.VIEWER),  # 空白
        ("", Role.NONE),
        (None, Role.NONE),
        ("unknown_role", Role.NONE),
        ("deleted_user", Role.NONE),
    ],
)
def test_normalize_role(raw, expected):
    """normalize_role 兼容 Phase 5 及更早的角色值 (Phase 6 B28 兼容)."""
    assert normalize_role(raw) == expected


def test_legacy_to_role_complete():
    """LEGACY_TO_ROLE 至少覆盖 5 个原值."""
    assert set(LEGACY_TO_ROLE.keys()) >= {
        "owner",
        "admin",
        "analyst",
        "viewer",
        "super_admin",
    }


# ===== menu_for_role =====


def test_menu_for_role_super_admin():
    """super_admin 看到全部菜单 (含 admin_console)."""
    items = menu_for_role(Role.SUPER_ADMIN)
    assert "admin_console" in items
    assert "billing" in items
    assert "workflows" in items


def test_menu_for_role_tenant_admin():
    """tenant_admin: 无 admin_console, 有 user_management + audit."""
    items = menu_for_role(Role.TENANT_ADMIN)
    assert "admin_console" not in items
    assert "user_management" in items
    assert "audit" in items


def test_menu_for_role_analyst():
    """analyst: 有 billing (read), 无 user_management / audit."""
    items = menu_for_role(Role.ANALYST)
    assert "billing" in items
    assert "user_management" not in items
    assert "audit" not in items


def test_menu_for_role_viewer():
    """viewer: 仅基础菜单."""
    items = menu_for_role(Role.VIEWER)
    assert "admin_console" not in items
    assert "billing" not in items
    assert "user_management" not in items
    assert "audit" not in items
    assert "workflows" in items
    assert "dashboard" in items


def test_menu_for_role_none():
    """none: 全部菜单均不可见 (即使最低要求的 dashboard 也看不到)."""
    items = menu_for_role(Role.NONE)
    assert items == []


def test_menu_requirements_consistency():
    """MENU_REQUIREMENTS 全部菜单项可被 menu_for_role 解释."""
    for item in MENU_REQUIREMENTS:
        assert item in menu_for_role(Role.SUPER_ADMIN)


# ===== 集成: require_permission 依赖对象 =====


def test_require_permission_dependency_object_repr():
    """require_permission 返回的依赖对象可被实例化并 repr."""
    from hscredit_studio.api.deps import require_permission

    dep = require_permission(Resource.WORKFLOW, Action.WRITE)
    assert isinstance(repr(dep), str)
    assert "workflow" in repr(dep)
    assert "write" in repr(dep)


def test_require_role_dependency_object_repr():
    """require_role 返回的依赖对象可被实例化."""
    from hscredit_studio.api.deps import require_role

    dep = require_role(Role.SUPER_ADMIN)
    assert "super_admin" in repr(dep)


# ===== 验收: viewer POST /workflows 期望被中间件拒绝 =====


def test_acceptance_viewer_workflow_write_denied():
    """Phase 6 B28 验收: viewer 调 POST /workflows 期望返回 403.

    该约束由 :func:`check_permission` 实现.
    """
    # viewer + write workflow
    assert check_permission(Role.VIEWER, Resource.WORKFLOW, Action.WRITE) is False
    # 也通过 decision 接口确认
    allowed, reason = permission_decision(Role.VIEWER, Resource.WORKFLOW, Action.WRITE)
    assert allowed is False
    assert "viewer" in reason.lower() or "viewer" in reason


def test_acceptance_analyst_can_create_workflow():
    """analyst + write workflow = True (业务分析师可创建工作流)."""
    assert check_permission(Role.ANALYST, Resource.WORKFLOW, Action.WRITE) is True


def test_acceptance_tenant_admin_can_admin_billing():
    """tenant_admin + admin billing = True (B20 账单管理)."""
    assert check_permission(Role.TENANT_ADMIN, Resource.BILLING, Action.ADMIN) is True
