"""v1 API 路由聚合.

集中导出各子模块 router，便于 :mod:`hscredit_studio.main` 一次性挂载.
"""

from __future__ import annotations

from hscredit_studio.api.v1 import auth, health, nodes, runs, templates, workflows, ws

__all__ = ["auth", "health", "nodes", "runs", "templates", "workflows", "ws"]
