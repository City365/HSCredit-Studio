"""ORM 共享基类与 mixin.

提供所有模型共用的字段：
- :class:`TimestampMixin` — ``created_at`` / ``updated_at`` 时间戳
- :class:`TenantMixin` — ``tenant_id`` 多租户外键
- :class:`SoftDeleteMixin` — ``deleted_at`` 软删除

所有 model 应组合使用这些 mixin，按需继承。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from hscredit_studio.core.database import Base


class TimestampMixin:
    """审计时间戳 mixin.

    自动维护 ``created_at`` / ``updated_at`` 两个 ``TIMESTAMPTZ`` 字段。
    数据库层 ``DEFAULT now()`` + ``ON UPDATE`` 由 PG 触发器或显式 SQL 保证。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间（UTC）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间（UTC）",
    )


class TenantMixin:
    """多租户隔离 mixin.

    添加 ``tenant_id`` UUID 外键列，指向 ``tenants.tenant_id``。
    索引由具体的表/迁移层声明（按 09 第 9.5 节的查询模式）。
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        """租户 ID 外键列."""
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="所属租户",
        )


class SoftDeleteMixin:
    """软删除 mixin.

    业务表使用 ``deleted_at`` 而非物理删除，配合 RLS 实现"逻辑删除"，
    物理删除仅用于临时数据（如 ETL 表）。
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="软删除时间戳（NULL 表示未删除）",
    )


class ModelSerializerMixin:
    """通用序列化 mixin.

    提供 ``to_dict()`` 方法，递归处理 ``datetime``、``UUID`` 等特殊类型，
    便于 API 层直接 ``model.to_dict()`` 返回。
    """

    def to_dict(self, exclude: set[str] | None = None, include_relationships: bool = False) -> dict[str, Any]:
        """转换为可序列化字典.

        Parameters
        ----------
        exclude:
            要排除的字段名集合。
        include_relationships:
            是否展开 SQLAlchemy 关系字段（默认否）。

        Returns
        -------
        dict[str, Any]
            字段名到 JSON 兼容值的映射。
        """
        exclude = exclude or set()
        result: dict[str, Any] = {}

        # 仅取标量字段
        for column in self.__table__.columns:  # type: ignore[attr-defined]
            name = column.name
            if name in exclude:
                continue
            value = getattr(self, name, None)
            result[name] = _serialize_value(value)

        # 关系字段按需展开
        if include_relationships:
            for rel_name in self.__mapper__.relationships:  # type: ignore[attr-defined]
                if rel_name in exclude:
                    continue
                rel_value = getattr(self, rel_name, None)
                if rel_value is None:
                    result[rel_name] = None
                elif isinstance(rel_value, list):
                    result[rel_name] = [
                        item.to_dict(exclude=exclude, include_relationships=False) if hasattr(item, "to_dict") else item
                        for item in rel_value
                    ]
                elif hasattr(rel_value, "to_dict"):
                    result[rel_name] = rel_value.to_dict(
                        exclude=exclude,
                        include_relationships=False,
                    )
                else:
                    result[rel_name] = rel_value

        return result


def _serialize_value(value: Any) -> Any:
    """将 ORM 字段值转换为 JSON 兼容类型."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    # Pydantic v2 等对象：尝试 .model_dump()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


__all__ = [
    "Base",
    "ModelSerializerMixin",
    "SoftDeleteMixin",
    "TenantMixin",
    "TimestampMixin",
]
