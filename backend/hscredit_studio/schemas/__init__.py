"""Workflow 后端 Pydantic schema 集合.

按主题拆分到子模块：

- :mod:`common` — 通用基类、分页、错误响应
- :mod:`auth` — 登录、令牌、用户信息
- :mod:`workflow` — 工作流 CRUD、版本、react-flow 序列化
- :mod:`run` — Run / NodeExecution / Artifact
- :mod:`node_contract` — 节点契约（核心：节点注册表对外暴露）

业务代码应 ``from hscredit_studio.schemas import ...`` 一次性导入。
"""

from __future__ import annotations

# ----- 通用 -----
from hscredit_studio.schemas.common import (
    BaseSchema,
    ErrorDetail,
    ErrorResponse,
    IDSchema,
    PaginatedResponse,
    Pagination,
    SuccessResponse,
    TimestampedSchema,
)

# ----- 认证 -----
from hscredit_studio.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    TokenPair,
    UserInfo,
)

# ----- 工作流 -----
from hscredit_studio.schemas.workflow import (
    EdgeDef,
    NodeDef,
    NodePosition,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowExportRequest,
    WorkflowExportResponse,
    WorkflowImportRequest,
    WorkflowListItem,
    WorkflowResponse,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionResponse,
)

# ----- Run / 节点执行 / 产物 -----
from hscredit_studio.schemas.run import (
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactType,
    NodeExecutionListItem,
    NodeExecutionLogItem,
    NodeExecutionLogsResponse,
    NodeExecutionResponse,
    NodeExecutionStatus,
    RunCancelResponse,
    RunListItem,
    RunMetricsResponse,
    RunResponse,
    RunStatus,
    RunSubmitRequest,
)

# ----- 节点契约 -----
from hscredit_studio.schemas.node_contract import (
    CacheConfig,
    CacheStrategy,
    NodeCategory,
    NodeContract,
    NodeDefinitionListResponse,
    NodeDefinitionResponse,
    NodeTestRequest,
    NodeTestResponse,
    ParamChoice,
    ParamSpec,
    ParamType,
    PortSchema,
    PortType,
)

__all__ = [
    # common
    "BaseSchema",
    "IDSchema",
    "TimestampedSchema",
    "Pagination",
    "PaginatedResponse",
    "ErrorDetail",
    "ErrorResponse",
    "SuccessResponse",
    # auth
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "RefreshRequest",
    "RefreshResponse",
    "TokenPair",
    "UserInfo",
    # workflow
    "EdgeDef",
    "NodeDef",
    "NodePosition",
    "WorkflowCreate",
    "WorkflowDefinition",
    "WorkflowExportRequest",
    "WorkflowExportResponse",
    "WorkflowImportRequest",
    "WorkflowListItem",
    "WorkflowResponse",
    "WorkflowUpdate",
    "WorkflowVersionCreate",
    "WorkflowVersionResponse",
    # run
    "ArtifactListResponse",
    "ArtifactResponse",
    "ArtifactType",
    "NodeExecutionListItem",
    "NodeExecutionLogItem",
    "NodeExecutionLogsResponse",
    "NodeExecutionResponse",
    "NodeExecutionStatus",
    "RunCancelResponse",
    "RunListItem",
    "RunMetricsResponse",
    "RunResponse",
    "RunStatus",
    "RunSubmitRequest",
    # node_contract
    "CacheConfig",
    "CacheStrategy",
    "NodeCategory",
    "NodeContract",
    "NodeDefinitionListResponse",
    "NodeDefinitionResponse",
    "NodeTestRequest",
    "NodeTestResponse",
    "ParamChoice",
    "ParamSpec",
    "ParamType",
    "PortSchema",
    "PortType",
]