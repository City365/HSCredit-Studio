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

# ----- 超管后台 (Phase 6 B29) -----
from hscredit_studio.schemas.admin import (
    GlobalOverviewResponse,
    RoleChangeRequest,
    RoleChangeResponse,
    TenantAuditEventInfo,
    TenantDetailResponse,
    TenantListItem,
    TenantListResponse,
    TenantMemberInfo,
    TenantMigrateRequest,
    TenantMigrateResponse,
    TenantOverviewItem,
    TenantStatusUpdateRequest,
    TenantStatusUpdateResponse,
    TenantTrendPoint,
    TenantUsageInfo,
)

# ----- 告警 (Phase 5 B27) -----
from hscredit_studio.schemas.alert import (
    AlertEvaluateRequest,
    AlertEvaluateResponse,
    AlertHistoryItem,
    AlertInstanceIngestRequest,
    AlertInstanceResponse,
    AlertmanagerConfigResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertSilenceCreate,
    AlertSilenceResponse,
    PrometheusRulesResponse,
)
from hscredit_studio.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    TokenPair,
    UserInfo,
)
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

# ----- 行业模板 (Phase 6 B30) -----
from hscredit_studio.schemas.industry_templates import (
    IndustryTemplateDetail,
    IndustryTemplateInstantiateRequest,
    IndustryTemplateInstantiateResponse,
    IndustryTemplateListResponse,
    IndustryTemplateRatingCreate,
    IndustryTemplateRatingResponse,
    IndustryTemplateSummary,
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

# ----- PIPL (Phase 5 B26) -----
from hscredit_studio.schemas.pipl import (
    AnonymizationResponse,
    ConsentGrantRequest,
    ConsentRevokeRequest,
    ConsentStateResponse,
    CrossBorderApproveRequest,
    CrossBorderRequestSchema,
    CrossBorderResponse,
    DsrListItem,
    DsrProcessRequest,
    DsrSubmitRequest,
    DsrSubmitResponse,
    PrivacyPolicyResponse,
    UserDataPackageResponse,
)
from hscredit_studio.schemas.rbac import (
    MenuResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    PermissionMatrixResponse,
    RoleAuditItem,
    RoleAuditListResponse,
    RoleInfo,
    RolePolicyCreate,
    RolePolicyResponse,
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

# ----- 安全加固 (Phase 5 B25) -----
from hscredit_studio.schemas.security import (
    ChainCheckResponse,
    IntrusionCheckRequest,
    IntrusionCheckResponse,
    IpAccessRuleCreate,
    IpAccessRuleResponse,
    IpCheckRequest,
    IpCheckResponse,
    LockoutStateResponse,
    PasswordCheckResponse,
    SecurityMetricsResponse,
    SiemExportRequest,
    SiemExportResponse,
    ThreatHitInfo,
    VulnerabilityCreate,
    VulnerabilityResponse,
    VulnerabilityStats,
    VulnerabilityUpdate,
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
    # PIPL (Phase 5 B26)
    "AlertEvaluateRequest",
    "AlertEvaluateResponse",
    "AlertHistoryItem",
    "AlertInstanceIngestRequest",
    "AlertInstanceResponse",
    "AlertRuleCreate",
    "AlertRuleResponse",
    "AlertSilenceCreate",
    "AlertSilenceResponse",
    "AlertmanagerConfigResponse",
    "AnonymizationResponse",
    # run
    "ArtifactListResponse",
    "ArtifactResponse",
    "ArtifactType",
    # common
    "BaseSchema",
    # node_contract
    "CacheConfig",
    "CacheStrategy",
    # 安全加固 (Phase 5 B25)
    "ChainCheckResponse",
    "ConsentGrantRequest",
    "ConsentRevokeRequest",
    "ConsentStateResponse",
    "CrossBorderApproveRequest",
    "CrossBorderRequestSchema",
    "CrossBorderResponse",
    # 用量 (Phase 4 B18)
    "DimensionUsage",
    "DsrListItem",
    "DsrProcessRequest",
    "DsrSubmitRequest",
    "DsrSubmitResponse",
    # workflow
    "EdgeDef",
    "ErrorDetail",
    "ErrorResponse",
    # 数据脱敏 (Phase 5 B24)
    "FieldClassificationInfo",
    "GlobalOverviewResponse",  # Phase 6 B29
    "IDSchema",
    "IndustryTemplateDetail",
    "IndustryTemplateInstantiateRequest",
    "IndustryTemplateInstantiateResponse",
    "IndustryTemplateListResponse",
    "IndustryTemplateRatingCreate",
    "IndustryTemplateRatingResponse",
    "IndustryTemplateSummary",
    "IntrusionCheckRequest",
    "IntrusionCheckResponse",
    "IpAccessRuleCreate",
    "IpAccessRuleResponse",
    "IpCheckRequest",
    "IpCheckResponse",
    "LockoutStateResponse",
    # auth
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "MaskResult",
    "MenuResponse",
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
    "PasswordCheckResponse",
    "PermissionCheckRequest",
    "PermissionCheckResponse",
    "PermissionMatrixResponse",
    "PortSchema",
    "PortType",
    "PrivacyPolicyResponse",
    "PrometheusRulesResponse",
    "RedactRequest",
    "RedactResponse",
    "RefreshRequest",
    "RefreshResponse",
    "RoleAuditItem",
    "RoleAuditListResponse",
    "RoleChangeRequest",
    "RoleChangeResponse",
    "RoleInfo",
    "RolePolicyCreate",
    "RolePolicyResponse",
    "RunCancelResponse",
    "RunListItem",
    "RunMetricsResponse",
    "RunResponse",
    "RunStatus",
    "RunSubmitRequest",
    "SecurityMetricsResponse",
    "SiemExportRequest",
    "SiemExportResponse",
    "SuccessResponse",
    "TenantAuditEventInfo",
    "TenantDetailResponse",
    "TenantListItem",
    "TenantListResponse",
    "TenantMemberInfo",
    "TenantMigrateRequest",
    "TenantMigrateResponse",
    "TenantOverviewItem",
    "TenantStatusUpdateRequest",
    "TenantStatusUpdateResponse",
    "TenantTrendPoint",
    "TenantUsageInfo",
    "TenantUsageResponse",
    "ThreatHitInfo",
    "TimestampedSchema",
    "TokenPair",
    "UserDataPackageResponse",
    "UserInfo",
    "VulnerabilityCreate",
    "VulnerabilityResponse",
    "VulnerabilityStats",
    "VulnerabilityUpdate",
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
