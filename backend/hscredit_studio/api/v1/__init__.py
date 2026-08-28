"""v1 API 路由聚合.

集中导出各子模块 router，便于 :mod:`hscredit_studio.main` 一次性挂载.
"""

from __future__ import annotations

from hscredit_studio.api.v1 import (
    audit,
    auth,
    billing,
    contracts,
    data_classification,
    health,
    monitor,
    nodes,
    notifications,
    pipl,
    quota,
    runs,
    security,
    templates,
    usage,
    workflows,
    ws,
)

__all__ = [
    "audit",
    "auth",
    "billing",
    "contracts",
    "data_classification",
    "health",
    "monitor",
    "nodes",
    "notifications",
    "pipl",
    "quota",
    "runs",
    "security",
    "templates",
    "usage",
    "workflows",
    "ws",
]
