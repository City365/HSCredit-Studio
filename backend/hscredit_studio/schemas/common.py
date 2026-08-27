"""通用 schema 基类与分页 / 错误响应.

所有业务 schema 应继承 :class:`BaseSchema` 或其子类
(:class:`IDSchema`, :class:`TimestampedSchema`)，
以保证 ``from_attributes=True``（与 ORM 直接互转）、``populate_by_name=True``
（兼容 ORM snake_case 字段）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """所有业务 schema 的基类.

    Attributes
    ----------
    model_config:
        - ``from_attributes``: 允许 ``model_validate(orm_obj)`` 直接从
          SQLAlchemy ORM 对象构造。
        - ``populate_by_name``: 允许同时接受 ``field_name`` 和
          ``field_name`` 两种风格（兼容 ORM snake_case 与前端 camelCase）。
        - ``use_enum_values=False``: 保留 Literal / Enum 原值，便于序列化。
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=False,
        str_strip_whitespace=True,
        extra="ignore",
    )


class IDSchema(BaseSchema):
    """仅含 UUID 主键的 schema.

    用于列表项 / 嵌入引用的最小表示。
    """

    id: UUID = Field(..., description="资源 UUID")


class TimestampedSchema(BaseSchema):
    """带审计时间戳的 schema.

    要求 ``created_at`` / ``updated_at`` 两个字段；
    与 ORM ``TimestampMixin`` 字段一一对应。
    """

    created_at: datetime = Field(..., description="创建时间（UTC）")
    updated_at: datetime = Field(..., description="更新时间（UTC）")


class Pagination(BaseModel):
    """分页查询参数（query string 风格）.

    Attributes
    ----------
    page:
        页码（从 1 开始）。
    page_size:
        每页条数（1-200）。
    sort_by:
        排序字段名（ORM 列名，snake_case）。
    sort_order:
        排序方向，默认 ``"desc"``。
    """

    page: int = Field(default=1, ge=1, description="页码（从 1 开始）")
    page_size: int = Field(default=20, ge=1, le=200, description="每页条数")
    sort_by: str | None = Field(default=None, description="排序字段名（ORM 列名）")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="排序方向")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装.

    示例::

        PaginatedResponse[WorkflowListItem](
            items=[...], total=145, page=1, page_size=20, total_pages=8
        )

    Attributes
    ----------
    items:
        当前页的数据列表。
    total:
        总记录数。
    page:
        当前页码。
    page_size:
        每页条数。
    total_pages:
        总页数（向上取整）。
    """

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(ge=0, description="总记录数")
    page: int = Field(ge=1, description="当前页码")
    page_size: int = Field(ge=1, description="每页条数")
    total_pages: int = Field(ge=0, description="总页数")


class ErrorDetail(BaseModel):
    """字段级错误详情.

    Attributes
    ----------
    field:
        出错的字段路径（如 ``params.max_n_bins``），可空（顶层错误）。
    message:
        人类可读错误信息（中文）。
    code:
        字段级错误码（可选）。
    """

    field: str | None = Field(default=None, description="出错字段路径")
    message: str = Field(..., min_length=1, description="错误描述")
    code: str | None = Field(default=None, description="字段级错误码")


class ErrorResponse(BaseModel):
    """统一错误响应.

    与 docs/design/14 第 14.3.4 节 ``error`` 字段结构对齐，但拆出 ``code``/
    ``message``/``details``/``request_id``/``timestamp`` 顶层，便于前端直接读取。

    Attributes
    ----------
    code:
        机器可读错误码（如 ``"E_VALIDATION_INPUT"``）。
    message:
        人类可读错误描述（中文）。
    details:
        字段级详情（list 或 dict），由调用方按错误类型传。
    request_id:
        请求追踪 ID（与 X-Request-ID 对齐）。
    timestamp:
        错误发生时间（UTC）。
    """

    code: str = Field(..., description="机器可读错误码")
    message: str = Field(..., description="错误描述")
    details: list[ErrorDetail] | dict[str, Any] | None = Field(
        default=None,
        description="错误详情；列表表示字段级错误，字典表示上下文",
    )
    request_id: str | None = Field(default=None, description="请求追踪 ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
        description="时间戳（UTC）",
    )


class SuccessResponse(BaseModel, Generic[T]):
    """统一成功响应包装.

    Attributes
    ----------
    data:
        业务数据。
    request_id:
        请求追踪 ID。
    """

    data: T = Field(..., description="业务数据")
    request_id: str | None = Field(default=None, description="请求追踪 ID")


__all__ = [
    "BaseSchema",
    "ErrorDetail",
    "ErrorResponse",
    "IDSchema",
    "PaginatedResponse",
    "Pagination",
    "SuccessResponse",
    "T",
    "TimestampedSchema",
]
