"""敏感字段访问审计服务 — Phase 5 B24.

依据 docs/ROADMAP.md Phase 5 B24:

> 数据访问审计: B20 每次读敏感字段写 audit event
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from hscredit_studio.core.logging import get_logger
from hscredit_studio.services.audit import AuditAction, ResourceType, record_event
from hscredit_studio.services.data_classification import (
    DataSensitivity,
    classify_field,
)

_log = get_logger(__name__)


async def log_sensitive_data_access(
    *,
    session: Any,
    tenant_id: UUID,
    user_id: UUID | None,
    resource_type: str,
    resource_id: UUID,
    field_name: str,
    field_value_hash: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """记录敏感字段访问 (Phase 5 B24).

    Args:
        session: AsyncSession.
        tenant_id: 租户 ID.
        user_id: 访问者 (None = 匿名/系统).
        resource_type: 资源类型 (例: dataset / run / tenant_config).
        resource_id: 资源 ID.
        field_name: 访问的字段名.
        field_value_hash: 字段值的 hash (避免明文落日志).
        extra: 额外上下文 (查询条件 / 命中行数等).
    """
    sensitivity = classify_field(field_name)
    if sensitivity not in (DataSensitivity.SENSITIVE, DataSensitivity.HIGHLY_SENSITIVE):
        # 公开/内部字段不记录
        return

    await record_event(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action=AuditAction.DATA_ACCESS,
        resource_type=resource_type,
        resource_id=resource_id,
        details={
            "field_name": field_name,
            "sensitivity": sensitivity.value,
            "field_value_hash": field_value_hash or "",
            **(extra or {}),
        },
    )
    _log.info(
        "sensitive_data_access",
        tenant_id=str(tenant_id),
        user_id=str(user_id) if user_id else None,
        resource_type=resource_type,
        resource_id=str(resource_id),
        field_name=field_name,
        sensitivity=sensitivity.value,
    )


async def log_data_export(
    *,
    session: Any,
    tenant_id: UUID,
    user_id: UUID | None,
    export_format: str,
    row_count: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """记录数据导出事件 (Phase 5 B24).

    Args:
        session: AsyncSession.
        tenant_id: 租户 ID.
        user_id: 导出操作者.
        export_format: 导出格式 (csv / xlsx / parquet / json).
        row_count: 导出行数.
        extra: 额外上下文 (字段列表 / 过滤条件等).
    """
    await record_event(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action=AuditAction.DATA_EXPORT,
        resource_type=ResourceType.DATASET,
        resource_id=None,
        details={
            "export_format": export_format,
            "row_count": row_count,
            **(extra or {}),
        },
    )
    _log.info(
        "data_exported",
        tenant_id=str(tenant_id),
        export_format=export_format,
        row_count=row_count,
    )


__all__ = [
    "log_data_export",
    "log_sensitive_data_access",
]
