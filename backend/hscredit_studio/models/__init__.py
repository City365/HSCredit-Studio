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
from hscredit_studio.models.node import (
    CUSTOM_NODE_TEST_RUN_STATUS_VALUES,
    VISIBILITY_VALUES,
    CustomNode,
    CustomNodeTestRun,
    CustomNodeVersion,
    NodeDefinition,
    NodeResourceUsage,
)
from hscredit_studio.models.run import (
    LOG_STREAM_VALUES,
    NODE_STATUS_VALUES,
    RUN_STATUS_VALUES,
    NodeExecution,
    NodeExecutionLog,
    Run,
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
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
    "LOG_STREAM_VALUES",
    "MEMBER_ROLE_VALUES",
    "MEMBER_STATUS_VALUES",
    "NODE_ARTIFACT_TYPE_VALUES",
    "NODE_STATUS_VALUES",
    "PLAN_VALUES",
    "RUN_ARTIFACT_TYPE_VALUES",
    "RUN_STATUS_VALUES",
    "TEMPLATE_VISIBILITY_VALUES",
    "TENANT_STATUS_VALUES",
    "USER_STATUS_VALUES",
    "VISIBILITY_VALUES",
    "ApiKey",
    # 审计
    "AuditEvent",
    # base mixin
    "Base",
    "CustomNode",
    "CustomNodeTestRun",
    "CustomNodeVersion",
    "ModelSerializerMixin",
    # 产物
    "NodeArtifact",
    # 节点
    "NodeDefinition",
    "NodeExecution",
    "NodeExecutionLog",
    "NodeResourceUsage",
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
    # 工作流
    "Workflow",
    "WorkflowTemplate",
    "WorkflowVersion",
]
