"""RBAC 权限矩阵 — Phase 6 B28.

依据 docs/ROADMAP.md Phase 6 B28:

> 角色: super_admin / tenant_admin / analyst / viewer 四级
> 资源权限矩阵: Workflow / Run / Model / Template / Billing 各自 read/write/admin
> 前端基于角色显隐菜单项
> 后端中间件强制检查 (不仅前端隐藏)
> 验收: viewer 角色调 POST /workflows 返回 403

设计要点:

- **5 级角色** (扩展原 4 级 owner/admin/analyst/viewer, 新增 super_admin 跨租户):
    * ``super_admin`` 平台级超管 (B29 后台使用), 跨租户访问
    * ``tenant_admin`` 租户管理员 (即原 owner/admin), 租户内全部权限
    * ``analyst`` 业务分析师, 读写工作流/运行/模型, 无 billing/admin 权限
    * ``viewer`` 只读, 不能写任何资源
    * ``none`` 已移除/禁用的成员

- **资源 × 动作矩阵**: 见 :data:`PERMISSION_MATRIX`. 资源 5 类 × 动作 3 类
  (read / write / admin) = 15 个授权点, 由 :func:`check_permission` 决策.

- **API 装饰器**: :func:`require_permission` 与 :func:`require_role`
  供 FastAPI 依赖注入使用, 后端中间件强制检查.

- **菜单项**: :func:`menu_for_role` 返回前端菜单可见性 (供 B29 super_admin 后台复用).
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):  # noqa: UP042
    """角色枚举 — Phase 6 B28.

    排序按权限从高到低, 便于 :func:`role_at_least` 比较.
    """

    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    NONE = "none"  # 已移除成员

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]


_ROLE_RANK: dict[Role, int] = {
    Role.SUPER_ADMIN: 100,
    Role.TENANT_ADMIN: 80,
    Role.ANALYST: 50,
    Role.VIEWER: 20,
    Role.NONE: 0,
}


class Resource(str, Enum):  # noqa: UP042
    """受保护资源类型 — Phase 6 B28."""

    WORKFLOW = "workflow"
    RUN = "run"
    MODEL = "model"
    TEMPLATE = "template"
    BILLING = "billing"


class Action(str, Enum):  # noqa: UP042
    """动作枚举 — Phase 6 B28.

    ``read`` < ``write`` < ``admin`` (后者包含前者).
    """

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return _ACTION_RANK[self]


_ACTION_RANK: dict[Action, int] = {
    Action.READ: 10,
    Action.WRITE: 20,
    Action.ADMIN: 30,
}


# ===== 权限矩阵 =====
#
# 表结构: PERMISSION_MATRIX[role][resource] = 最高允许 action
# 未列出视为 NONE (拒绝).
#
# 设计原则:
# - super_admin: 跨租户全权 (含 billing.admin, workflow.admin 等)
# - tenant_admin: 租户内全权 (含 billing), 但跨租户操作被 RLS 拦截
# - analyst: 读写业务资源, 不能 admin (不能删/改他人资源, 不能碰 billing)
# - viewer: 只能 read
# - none: 全部拒绝

PERMISSION_MATRIX: dict[Role, dict[Resource, Action | None]] = {
    Role.SUPER_ADMIN: {
        Resource.WORKFLOW: Action.ADMIN,
        Resource.RUN: Action.ADMIN,
        Resource.MODEL: Action.ADMIN,
        Resource.TEMPLATE: Action.ADMIN,
        Resource.BILLING: Action.ADMIN,
    },
    Role.TENANT_ADMIN: {
        Resource.WORKFLOW: Action.ADMIN,
        Resource.RUN: Action.ADMIN,
        Resource.MODEL: Action.ADMIN,
        Resource.TEMPLATE: Action.ADMIN,
        Resource.BILLING: Action.ADMIN,
    },
    Role.ANALYST: {
        Resource.WORKFLOW: Action.WRITE,
        Resource.RUN: Action.WRITE,
        Resource.MODEL: Action.WRITE,
        Resource.TEMPLATE: Action.READ,
        Resource.BILLING: Action.READ,
    },
    Role.VIEWER: {
        Resource.WORKFLOW: Action.READ,
        Resource.RUN: Action.READ,
        Resource.MODEL: Action.READ,
        Resource.TEMPLATE: Action.READ,
        Resource.BILLING: Action.READ,
    },
    Role.NONE: {
        Resource.WORKFLOW: None,
        Resource.RUN: None,
        Resource.MODEL: None,
        Resource.TEMPLATE: None,
        Resource.BILLING: None,
    },
}


def role_at_least(actual: Role, required: Role) -> bool:
    """判断 actual 角色是否 ≥ required (Phase 6 B28).

    Args:
        actual: 当前用户角色.
        required: 资源所需最低角色.

    Returns:
        bool — True 表示 actual 权限足够.
    """
    return actual.rank >= required.rank


def check_permission(
    role: Role,
    resource: Resource,
    action: Action,
) -> bool:
    """检查 role 对 resource 执行 action 是否被允许 (Phase 6 B28 验收).

    逻辑:

    1. 查表得到 role 对 resource 的最高允许 action (None 表示拒绝).
    2. 比较 action.rank ≤ allowed.rank 即允许.

    Examples:
        >>> check_permission(Role.VIEWER, Resource.WORKFLOW, Action.READ)
        True
        >>> check_permission(Role.VIEWER, Resource.WORKFLOW, Action.WRITE)
        False
        >>> check_permission(Role.ANALYST, Resource.BILLING, Action.WRITE)
        False
    """
    allowed = PERMISSION_MATRIX.get(role, {}).get(resource)
    if allowed is None:
        return False
    return action.rank <= allowed.rank


def permission_decision(
    role: Role,
    resource: Resource,
    action: Action,
) -> tuple[bool, str]:
    """带原因的权限决策 (供中间件 / 日志使用).

    Returns:
        (allowed, reason)
    """
    allowed_action = PERMISSION_MATRIX.get(role, {}).get(resource)
    if allowed_action is None:
        return False, f"角色 {role.value} 对资源 {resource.value} 无任何权限"
    if action.rank > allowed_action.rank:
        return (
            False,
            f"角色 {role.value} 对资源 {resource.value} 最高权限为 {allowed_action.value}, "
            f"请求 {action.value} 不满足",
        )
    return True, ""


# ===== 菜单可见性 =====


# 前端菜单项 → 最低角色要求
MENU_REQUIREMENTS: dict[str, Role] = {
    "admin_console": Role.SUPER_ADMIN,
    "billing": Role.ANALYST,
    "audit": Role.TENANT_ADMIN,
    "user_management": Role.TENANT_ADMIN,
    "workflows": Role.VIEWER,
    "runs": Role.VIEWER,
    "models": Role.VIEWER,
    "templates": Role.VIEWER,
    "dashboard": Role.VIEWER,
}


def menu_for_role(role: Role) -> list[str]:
    """返回 role 可见的前端菜单项列表 (Phase 6 B28).

    供前端根据当前角色显隐菜单项. 后端仍走 :func:`check_permission` 强制,
    前端只是 UX 优化.
    """
    return [item for item, required in MENU_REQUIREMENTS.items() if role_at_least(role, required)]


# ===== 旧 → 新 角色映射 (兼容 Phase 5 及更早数据) =====


LEGACY_TO_ROLE: dict[str, Role] = {
    "owner": Role.TENANT_ADMIN,
    "admin": Role.TENANT_ADMIN,
    "analyst": Role.ANALYST,
    "viewer": Role.VIEWER,
    "super_admin": Role.SUPER_ADMIN,
    "none": Role.NONE,
}
"""原 tenant_members.role (owner/admin/analyst/viewer) → 新 Role 映射."""


def normalize_role(raw: str | None) -> Role:
    """将任意来源的 role 字符串规范化为 :class:`Role` (Phase 6 B28).

    兼容:

    - ``tenant_members.role`` 旧值 (owner / admin / analyst / viewer)
    - JWT payload 中的 ``role`` 字段
    - 已是新 Role.value 的输入

    未识别值一律返回 ``Role.NONE`` (拒绝访问).
    """
    if not raw:
        return Role.NONE
    normalized = raw.strip().lower()
    if normalized in LEGACY_TO_ROLE:
        return LEGACY_TO_ROLE[normalized]
    try:
        return Role(normalized)
    except ValueError:
        return Role.NONE


__all__ = [
    "MENU_REQUIREMENTS",
    "PERMISSION_MATRIX",
    "Action",
    "Resource",
    "Role",
    "check_permission",
    "menu_for_role",
    "normalize_role",
    "permission_decision",
    "role_at_least",
]
