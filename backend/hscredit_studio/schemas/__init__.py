"""Workflow 后端 Pydantic schema 集合.

按主题拆分到子模块：

- :mod:`common` — 通用基类、分页、错误响应
- :mod:`auth` — 登录、令牌、用户信息
- :mod:`workflow` — 工作流 CRUD、版本、react-flow 序列化
- :mod:`run` — Run / NodeExecution / Artifact
- :mod:`node_contract` — 节点契约（核心：节点注册表对外暴露）
- :mod:`usage` — 租户用量查询 (Phase 4 B18)

业务代码应 ``from hscredit_studio.schemas import ...`` 一次性导入。
"""

from __future__ import annotations

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
from hscredit_studio.schemas.data_classification import (
    FieldClassificationInfo,
    MaskResult,
    RedactRequest,
    RedactResponse,
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
from hscredit_studio.schemas.usage import (
    DimensionUsage,
    NodeTypeUsage,
    TenantUsageResponse,
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

__all__ = [
    # run
    "ArtifactListResponse",
    "ArtifactResponse",
    "ArtifactType",
    # common
    "BaseSchema",
    # node_contract
    "CacheConfig",
    "CacheStrategy",
    # 用量 (Phase 4 B18)
    "DimensionUsage",
    # workflow
    "EdgeDef",
    "ErrorDetail",
    "ErrorResponse",
    # 数据脱敏 (Phase 5 B24)
    "FieldClassificationInfo",
    "IDSchema",
    # auth
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "MaskResult",
    "NodeCategory",
    "NodeContract",
    "NodeDef",
    "NodeDefinitionListResponse",
    "NodeDefinitionResponse",
    "NodeExecutionListItem",
    "NodeExecutionLogItem",
    "NodeExecutionLogsResponse",
    "NodeExecutionResponse",
    "NodeExecutionStatus",
    "NodePosition",
    "NodeTestRequest",
    "NodeTestResponse",
    # 用量 (Phase 4 B18)
    "NodeTypeUsage",
    "PaginatedResponse",
    "Pagination",
    "ParamChoice",
    "ParamSpec",
    "ParamType",
    "PortSchema",
    "PortType",
    "RedactRequest",
    "RedactResponse",
    "RefreshRequest",
    "RefreshResponse",
    "RunCancelResponse",
    "RunListItem",
    "RunMetricsResponse",
    "RunResponse",
    "RunStatus",
    "RunSubmitRequest",
    "SuccessResponse",
    "TenantUsageResponse",
    "TimestampedSchema",
    "TokenPair",
    "UserInfo",
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
]
