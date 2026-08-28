"""审计事件服务 — 记录 / 查询 / 导出.

设计要点:

- 写入是 append-only,绝不允许 UPDATE/DELETE (合规要求)
- 高频路径(登录/Run 提交/工作流编辑)走 fire-and-forget,失败只记录 WARN,
  不阻塞业务请求
- 查询支持丰富过滤: 租户/用户/动作/资源类型/时间区间/分页
- 导出 CSV (前端 Excel/CSV 导出), 支持时间区间过滤
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models import AuditEvent

_log = get_logger(__name__)


# ===== 标准动作常量 (审计字典) =====


class AuditAction:
    """审计动作字符串常量 — 避免业务代码中出现 magic strings.

    Phase 5 B22 扩展:
    - DATA_ACCESS — 数据访问 (含敏感字段读取)
    - PERMISSION_CHANGE — 权限变更 (角色/成员)
    - CONFIG_CHANGE — 配置变更 (租户 plan / 限额 / 设置)
    - EXPORT — 数据/模型导出
    - AUTH_FAILURE — 鉴权失败 (含 JWT 无效 / 越权访问)
    """

    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESH = "token_refresh"
    WORKFLOW_CREATE = "workflow_create"
    WORKFLOW_UPDATE = "workflow_update"
    WORKFLOW_DELETE = "workflow_delete"
    WORKFLOW_RUN_SUBMIT = "workflow_run_submit"
    WORKFLOW_RUN_CANCEL = "workflow_run_cancel"
    WORKFLOW_RUN_RETRY_NODE = "workflow_run_retry_node"
    TEMPLATE_INSTANTIATE = "template_instantiate"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    APIKEY_CREATE = "apikey_create"
    APIKEY_REVOKE = "apikey_revoke"
    CUSTOM_NODE_PUBLISH = "custom_node_publish"
    # Phase 5 B22 新增
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    IMAGE_EXPORT = "image_export"
    MODEL_EXPORT = "model_export"
    PERMISSION_CHANGE = "permission_change"
    CONFIG_CHANGE = "config_change"
    AUTH_FAILURE = "auth_failure"
    CONTRACT_SIGN = "contract_sign"
    VAT_INVOICE_APPLY = "vat_invoice_apply"
    BILL_GENERATE = "bill_generate"
    PAYMENT_INIT = "payment_init"


class ResourceType:
    WORKFLOW = "workflow"
    WORKFLOW_VERSION = "workflow_version"
    RUN = "run"
    NODE_EXECUTION = "node_execution"
    TEMPLATE = "template"
    USER = "user"
    APIKEY = "apikey"
    CUSTOM_NODE = "custom_node"
    # Phase 5 B22 新增
    DATASET = "dataset"
    BILL = "bill"
    INVOICE = "invoice"
    CONTRACT = "contract"
    TENANT_CONFIG = "tenant_config"
    ROLE = "role"
    MODEL_ARTIFACT = "model_artifact"


# ===== 写入 =====


async def record_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent | None:
    """记录一条审计事件.

    使用 ON CONFLICT DO NOTHING (event_id 是 PK) 保证幂等, 避免重复写入
    在极高并发情况下造成主键冲突.
    """
    import uuid as _uuid

    event_id = _uuid.uuid4()
    stmt = (
        pg_insert(AuditEvent)
        .values(
            event_id=event_id,
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    try:
        await session.execute(stmt)
        return await session.get(AuditEvent, event_id)
    except Exception as e:
        # 审计写入失败不应阻塞业务 — 仅记录 WARN
        _log.warning("audit_write_failed", extra={"action": action, "error": str(e)[:200]})
        return None


async def record_login(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    email: str | None = None,
) -> None:
    """记录登录事件 (成功 / 失败)."""
    await record_event(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        action=AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED,
        resource_type=ResourceType.USER,
        resource_id=user_id,
        details={"email": email} if email else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


# ===== 查询 =====


async def list_events(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    user_id: UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditEvent], int]:
    """分页查询审计事件 (新到旧)."""
    conditions = [AuditEvent.tenant_id == tenant_id]
    if user_id is not None:
        conditions.append(AuditEvent.user_id == user_id)
    if action:
        conditions.append(AuditEvent.action == action)
    if resource_type:
        conditions.append(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditEvent.resource_id == resource_id)
    if since is not None:
        conditions.append(AuditEvent.occurred_at >= since)
    if until is not None:
        conditions.append(AuditEvent.occurred_at <= until)

    where_clause = and_(*conditions)

    # 总数
    total = await session.scalar(select(func.count(AuditEvent.event_id)).where(where_clause))

    # 分页数据
    offset = (page - 1) * page_size
    rows = (
        await session.scalars(
            select(AuditEvent)
            .where(where_clause)
            .order_by(AuditEvent.occurred_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()

    return list(rows), int(total or 0)


async def iter_events_csv(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    batch_size: int = 500,
) -> AsyncIterator[bytes]:
    """流式导出 CSV — 避免一次性加载大量审计数据到内存.

    使用 yield chunk 模式: HTTPX/StreamingResponse 会逐块下发.
    """
    conditions = [AuditEvent.tenant_id == tenant_id]
    if since is not None:
        conditions.append(AuditEvent.occurred_at >= since)
    if until is not None:
        conditions.append(AuditEvent.occurred_at <= until)
    where_clause = and_(*conditions)

    # CSV header (BOM 让 Excel 正确识别 UTF-8)
    yield b"\xef\xbb\xbf"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "event_id",
            "occurred_at",
            "tenant_id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "details",
        ]
    )
    yield buf.getvalue().encode("utf-8")
    buf.seek(0)
    buf.truncate()

    # 分块查询
    last_event_id: UUID | None = None
    while True:
        query = (
            select(AuditEvent)
            .where(where_clause)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.event_id.desc())
            .limit(batch_size)
        )
        if last_event_id is not None:
            # keyset 分页: 避免 OFFSET 性能问题
            query = query.where(AuditEvent.event_id < last_event_id)
        rows = (await session.scalars(query)).all()
        if not rows:
            break

        buf.seek(0)
        buf.truncate()
        for row in rows:
            writer.writerow(
                [
                    str(row.event_id),
                    row.occurred_at.isoformat() if row.occurred_at else "",
                    str(row.tenant_id),
                    str(row.user_id) if row.user_id else "",
                    row.action,
                    row.resource_type or "",
                    str(row.resource_id) if row.resource_id else "",
                    row.ip_address or "",
                    (row.user_agent or "")[:500],
                    _safe_json(row.details),
                ]
            )
        yield buf.getvalue().encode("utf-8")
        last_event_id = rows[-1].event_id


def _safe_json(obj: Any) -> str:
    """JSON 安全序列化."""
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)[:2000]
    except Exception:
        return str(obj)[:2000]


# ===== 保留策略 =====

DEFAULT_HOT_RETENTION_DAYS = 90  # 热存储保留 90 天


def hot_retention_cutoff(now: datetime | None = None) -> datetime:
    """热存储保留截止时间 (用于定时归档/删除任务)."""
    now = now or datetime.utcnow()
    return now - timedelta(days=DEFAULT_HOT_RETENTION_DAYS)


__all__ = [
    "DEFAULT_HOT_RETENTION_DAYS",
    "AuditAction",
    "ResourceType",
    "hot_retention_cutoff",
    "iter_events_csv",
    "list_events",
    "record_event",
    "record_login",
]
