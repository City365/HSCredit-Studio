"""ORM 模型集中导出.

为 alembic autogenerate 提供一个干净的"所有 model 都已注册"入口。
新模型应：

1. 定义于单独文件（如 ``tenant.py``）。
2. 在本 ``__init__`` 中 re-export 类与枚举常量。

导入时序：先 :mod:`base` (mixin)，再 :mod:`user` (无依赖)，
最后各业务表（依赖 user / tenant）。
"""

from __future__ import annotations

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
    TEMPLATE_VISIBILITY_VALUES,
    Template,
    TemplateRating,
    TemplateVersion,
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

# 业务表
from hscredit_studio.models.workflow import (
    Workflow,
    WorkflowTemplate,
    WorkflowVersion,
)

__all__ = [
    "ACCOUNT_LOCKOUT_STATUS_VALUES",  # Phase 5 B25
    "BILL_STATUS_VALUES",
    "CHAIN_CHECKPOINT_STATUS_VALUES",  # Phase 5 B25
    "CONTRACT_STATUS_VALUES",
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
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
    "TEMPLATE_VISIBILITY_VALUES",
    "TENANT_STATUS_VALUES",
    "USER_STATUS_VALUES",
    "VISIBILITY_VALUES",
    "VULNERABILITY_SEVERITY_VALUES",  # Phase 5 B25
    "VULNERABILITY_STATUS_VALUES",  # Phase 5 B25
    "AccountLockout",  # Phase 5 B25
    "ApiKey",
    # 审计
    "AuditChainCheckpoint",  # Phase 5 B25
    "AuditEvent",
    # base mixin
    "Base",
    "Bill",
    "Contract",
    "CustomNode",
    "CustomNodeTestRun",
    "CustomNodeVersion",
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
    # 执行
    "Run",
    "RunArtifact",
    "SoftDeleteMixin",
    # 模板
    "Template",
    "TemplateRating",
    "TemplateVersion",
    # 租户
    "Tenant",
    "TenantMember",
    "TenantMixin",
    "TimestampMixin",
    # 用户
    "User",
    "UserInvitation",
    # 安全加固 (Phase 5 B25)
    "Vulnerability",
    # 工作流
    "Workflow",
    "WorkflowTemplate",
    "WorkflowVersion",
]
