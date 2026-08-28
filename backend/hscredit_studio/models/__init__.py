"""ORM 模型集中导出.

为 alembic autogenerate 提供一个干净的"所有 model 都已注册"入口。
新模型应：

1. 定义于单独文件（如 ``tenant.py``）。
2. 在本 ``__init__`` 中 re-export 类与枚举常量。

导入时序：先 :mod:`base` (mixin)，再 :mod:`user` (无依赖)，
最后各业务表（依赖 user / tenant）。
"""

from __future__ import annotations

# 告警 (Phase 5 B27)
from hscredit_studio.models.alert import (
    ALERT_CHANNEL_VALUES,
    ALERT_SEVERITY_VALUES,
    ALERT_STATE_VALUES,
    AlertHistory,
    AlertInstance,
    AlertRule,
    AlertSilence,
)
from hscredit_studio.models.artifact import (
    NODE_ARTIFACT_TYPE_VALUES,
    RUN_ARTIFACT_TYPE_VALUES,
    NodeArtifact,
    RunArtifact,
)
from hscredit_studio.models.audit import (
    AuditEvent,
)

# Base mixin
from hscredit_studio.models.base import (
    Base,
    ModelSerializerMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from hscredit_studio.models.billing import (
    BILL_STATUS_VALUES,
    CONTRACT_STATUS_VALUES,
    INVOICE_STATUS_VALUES,
    INVOICE_TYPE_VALUES,
    PAYMENT_CHANNEL_VALUES,
    Bill,
    Contract,
    Invoice,
)
from hscredit_studio.models.node import (
    CUSTOM_NODE_TEST_RUN_STATUS_VALUES,
    VISIBILITY_VALUES,
    CustomNode,
    CustomNodeTestRun,
    CustomNodeVersion,
    NodeDefinition,
    NodeResourceUsage,
)

# 通知 (Phase 5 B23)
from hscredit_studio.models.notification import (
    NOTIFICATION_CHANNEL_VALUES,
    NOTIFICATION_STATUS_VALUES,
    NotificationConfig,
    NotificationLog,
)

# PIPL 数据保护 (Phase 5 B26)
from hscredit_studio.models.pipl import (
    CONSENT_PURPOSE_VALUES,
    CROSS_BORDER_BASIS_VALUES,
    DSR_STATUS_VALUES,
    DSR_TYPE_VALUES,
    ConsentRecord,
    CrossBorderTransfer,
    DataSubjectRequest,
    PrivacyPolicyVersion,
)

# RBAC 角色权限 (Phase 6 B28)
from hscredit_studio.models.rbac import (
    RolePolicy,
    UserRoleAudit,
)
from hscredit_studio.models.run import (
    LOG_STREAM_VALUES,
    NODE_STATUS_VALUES,
    RUN_STATUS_VALUES,
    NodeExecution,
    NodeExecutionLog,
    Run,
)

# 安全加固 (Phase 5 B25)
from hscredit_studio.models.security import (
    ACCOUNT_LOCKOUT_STATUS_VALUES,
    CHAIN_CHECKPOINT_STATUS_VALUES,
    IP_RULE_TYPE_VALUES,
    VULNERABILITY_SEVERITY_VALUES,
    VULNERABILITY_STATUS_VALUES,
    AccountLockout,
    AuditChainCheckpoint,
    IpAccessRule,
    Vulnerability,
)
from hscredit_studio.models.template import (
    TEMPLATE_REVIEW_STATUS_VALUES,
    TEMPLATE_VISIBILITY_VALUES,
    Template,
    TemplateRating,
    TemplateVersion,
)

# 模板审核 (Phase 6 B31)
from hscredit_studio.models.template_review import (
    TemplateReviewLog,
)
from hscredit_studio.models.tenant import (
    MEMBER_ROLE_VALUES,
    MEMBER_STATUS_VALUES,
    PLAN_VALUES,
    TENANT_STATUS_VALUES,
    ApiKey,
    Tenant,
    TenantMember,
    UserInvitation,
)

# 租户与用户
from hscredit_studio.models.user import (
    USER_STATUS_VALUES,
    User,
)
from hscredit_studio.models.webhook import (  # Phase 8 B35
    WebhookDelivery,
    WebhookSubscription,
)

# 业务表
from hscredit_studio.models.workflow import (
    Workflow,
    WorkflowTemplate,
    WorkflowVersion,
)

__all__ = [
    "ACCOUNT_LOCKOUT_STATUS_VALUES",  # Phase 5 B25
    "ALERT_CHANNEL_VALUES",  # Phase 5 B27
    "ALERT_SEVERITY_VALUES",  # Phase 5 B27
    "ALERT_STATE_VALUES",  # Phase 5 B27
    "BILL_STATUS_VALUES",
    "CHAIN_CHECKPOINT_STATUS_VALUES",  # Phase 5 B25
    "CONSENT_PURPOSE_VALUES",  # Phase 5 B26
    "CONTRACT_STATUS_VALUES",
    "CROSS_BORDER_BASIS_VALUES",  # Phase 5 B26
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
    "DSR_STATUS_VALUES",  # Phase 5 B26
    "DSR_TYPE_VALUES",  # Phase 5 B26
    "INVOICE_STATUS_VALUES",
    "INVOICE_TYPE_VALUES",
    "IP_RULE_TYPE_VALUES",  # Phase 5 B25
    "LOG_STREAM_VALUES",
    "MEMBER_ROLE_VALUES",
    "MEMBER_STATUS_VALUES",
    "NODE_ARTIFACT_TYPE_VALUES",
    "NODE_STATUS_VALUES",
    "NOTIFICATION_CHANNEL_VALUES",
    "NOTIFICATION_STATUS_VALUES",
    "PAYMENT_CHANNEL_VALUES",
    "PLAN_VALUES",
    "RUN_ARTIFACT_TYPE_VALUES",
    "RUN_STATUS_VALUES",
    "TEMPLATE_REVIEW_STATUS_VALUES",  # Phase 6 B31
    "TEMPLATE_VISIBILITY_VALUES",
    "TENANT_STATUS_VALUES",
    "USER_STATUS_VALUES",
    "VISIBILITY_VALUES",
    "VULNERABILITY_SEVERITY_VALUES",  # Phase 5 B25
    "VULNERABILITY_STATUS_VALUES",  # Phase 5 B25
    "AccountLockout",  # Phase 5 B25
    "AlertHistory",  # Phase 5 B27
    "AlertInstance",  # Phase 5 B27
    "AlertRule",  # Phase 5 B27
    "AlertSilence",  # Phase 5 B27
    "ApiKey",
    # 审计
    "AuditChainCheckpoint",  # Phase 5 B25
    "AuditEvent",
    # base mixin
    "Base",
    "Bill",
    "ConsentRecord",  # Phase 5 B26
    "Contract",
    "CrossBorderTransfer",  # Phase 5 B26
    "CustomNode",
    "CustomNodeTestRun",
    "CustomNodeVersion",
    "DataSubjectRequest",  # Phase 5 B26
    "Invoice",
    "IpAccessRule",  # Phase 5 B25
    "ModelSerializerMixin",
    # 产物
    "NodeArtifact",
    # 节点
    "NodeDefinition",
    "NodeExecution",
    "NodeExecutionLog",
    "NodeResourceUsage",
    # 通知 (Phase 5 B23)
    "NotificationConfig",
    "NotificationLog",
    "PrivacyPolicyVersion",  # Phase 5 B26
    # RBAC (Phase 6 B28)
    "RolePolicy",
    # 执行
    "Run",
    "RunArtifact",
    "SoftDeleteMixin",
    # 模板
    "Template",
    "TemplateRating",
    "TemplateReviewLog",  # Phase 6 B31
    "TemplateVersion",
    # 租户
    "Tenant",
    "TenantMember",
    "TenantMixin",
    "TimestampMixin",
    # 用户
    "User",
    "UserInvitation",
    # RBAC 角色变更审计 (Phase 6 B28)
    "UserRoleAudit",
    # 安全加固 (Phase 5 B25)
    "Vulnerability",
    # 工作流
    "WebhookDelivery",  # Phase 8 B35
    "WebhookSubscription",  # Phase 8 B35
    "Workflow",
    "WorkflowTemplate",
    "WorkflowVersion",
]
