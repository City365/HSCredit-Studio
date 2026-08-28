"""v1 API 路由聚合.

集中导出各子模块 router，便于 :mod:`hscredit_studio.main` 一次性挂载.
"""

from __future__ import annotations

from hscredit_studio.api.v1 import (
    admin,
    alerts,
    audit,
    auth,
    bi_export,
    billing,
    contracts,
    data_classification,
    health,
    industry_templates,
    model_export,
    monitor,
    nodes,
    notifications,
    pipl,
    quota,
    rbac,
    runs,
    security,
    template_sharing,
    templates,
    usage,
    workflows,
    ws,
)

__all__ = [
    "admin",
    "alerts",
    "audit",
    "auth",
    "bi_export",
    "billing",
    "contracts",
    "data_classification",
    "health",
    "industry_templates",
    "model_export",
    "monitor",
    "nodes",
    "notifications",
    "pipl",
    "quota",
    "rbac",
    "runs",
    "security",
    "template_sharing",
    "templates",
    "usage",
    "workflows",
    "ws",
]
