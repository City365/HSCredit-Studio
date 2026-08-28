"""业务服务层.

按业务域拆分（auth / workflow / run / node 等），
service 层负责组合 ORM 模型、JWT、事务与业务规则，
路由层仅做参数校验和响应序列化。
"""

from __future__ import annotations

from hscredit_studio.services import rbac as _rbac

__all__ = ["_rbac"]
