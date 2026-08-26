"""ORM 模型集中导出.

为 alembic autogenerate 提供一个干净的"所有 model 都已注册"入口。
新模型应：

1. 定义于单独文件（如 ``tenant.py``）。
2. 在本 ``__init__`` 中 re-export 类与枚举常量。

导入时序：先 :mod:`base` (mixin)，再 :mod:`user` (无依赖)，
最后各业务表（依赖 user / tenant）。
"""

from __future__ import annotations

# Base mixin
from hscredit_studio.models.base import (
    Base,
    ModelSerializerMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)

# 租户与用户
from hscredit_studio.models.user import (
    USER_STATUS_VALUES,
    User,
)
from hscredit_studio.models.tenant import (
    ApiKey,
    MEMBER_ROLE_VALUES,
    MEMBER_STATUS_VALUES,
    PLAN_VALUES,
    TENANT_STATUS_VALUES,
    Tenant,
    TenantMember,
    UserInvitation,
)

# 业务表
from hscredit_studio.models.workflow import (
    Workflow,
    WorkflowTemplate,
    WorkflowVersion,
)
from hscredit_studio.models.run import (
    LOG_STREAM_VALUES,
    NodeExecution,
    NodeExecutionLog,
    NODE_STATUS_VALUES,
    Run,
    RUN_STATUS_VALUES,
)
from hscredit_studio.models.artifact import (
    NodeArtifact,
    NODE_ARTIFACT_TYPE_VALUES,
    RunArtifact,
    RUN_ARTIFACT_TYPE_VALUES,
)
from hscredit_studio.models.node import (
    CustomNode,
    CustomNodeTestRun,
    CustomNodeVersion,
    CUSTOM_NODE_TEST_RUN_STATUS_VALUES,
    NodeDefinition,
    VISIBILITY_VALUES,
)
from hscredit_studio.models.template import (
    Template,
    TemplateRating,
    TEMPLATE_VISIBILITY_VALUES,
    TemplateVersion,
)
from hscredit_studio.models.audit import (
    AuditEvent,
)


__all__ = [
    # base mixin
    "Base",
    "TimestampMixin",
    "TenantMixin",
    "SoftDeleteMixin",
    "ModelSerializerMixin",
    # 用户
    "User",
    "USER_STATUS_VALUES",
    # 租户
    "Tenant",
    "TenantMember",
    "UserInvitation",
    "ApiKey",
    "PLAN_VALUES",
    "TENANT_STATUS_VALUES",
    "MEMBER_ROLE_VALUES",
    "MEMBER_STATUS_VALUES",
    # 工作流
    "Workflow",
    "WorkflowVersion",
    "WorkflowTemplate",
    # 执行
    "Run",
    "NodeExecution",
    "NodeExecutionLog",
    "RUN_STATUS_VALUES",
    "NODE_STATUS_VALUES",
    "LOG_STREAM_VALUES",
    # 产物
    "NodeArtifact",
    "RunArtifact",
    "NODE_ARTIFACT_TYPE_VALUES",
    "RUN_ARTIFACT_TYPE_VALUES",
    # 节点
    "NodeDefinition",
    "CustomNode",
    "CustomNodeVersion",
    "CustomNodeTestRun",
    "VISIBILITY_VALUES",
    "CUSTOM_NODE_TEST_RUN_STATUS_VALUES",
    # 模板
    "Template",
    "TemplateVersion",
    "TemplateRating",
    "TEMPLATE_VISIBILITY_VALUES",
    # 审计
    "AuditEvent",
]
