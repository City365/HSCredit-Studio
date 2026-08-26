"""产物（artifact）相关模型.

按 09 第 9.3.4 节实现：

- :class:`NodeArtifact` — 节点级产物元数据
- :class:`RunArtifact` — Run 级产物聚合
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from hscredit_studio.core.database import Base
from hscredit_studio.models.base import (
    ModelSerializerMixin,
    TenantMixin,
    TimestampMixin,
)


NODE_ARTIFACT_TYPE_VALUES = ("parquet", "excel", "pmml", "json", "png", "model", "binner", "scorecard")
"""NodeArtifact.artifact_type 枚举值.

注：09 文档使用 ``Excel/Parquet/...`` 等 Mixed case；
此处统一小写，迁移层添加 PG enum 类型时也会用小写。
"""

RUN_ARTIFACT_TYPE_VALUES = ("model_report", "scorecard", "pmml", "binner", "metrics")
"""RunArtifact.artifact_type 枚举值."""


class NodeArtifact(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """节点级产物元数据.

    ``storage_path`` 指向 MinIO/S3；``sha256`` 用于去重（同一节点同一
    artifact_type 下唯一）。
    """

    __tablename__ = "node_artifacts"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    node_exec_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("node_executions.node_exec_id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=f"产物类型，取值 {NODE_ARTIFACT_TYPE_VALUES}",
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, comment="S3/MinIO 对象路径")
    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="文件大小（字节）",
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="文件 sha256（用于去重）",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="类型相关元数据（如 binner 的特征名）",
    )

    __table_args__ = (
        # 同节点同类型同哈希唯一
        UniqueConstraint(
            "node_exec_id",
            "artifact_type",
            "sha256",
            name="uq_node_artifact_dedup",
        ),
        # 按节点查产物
        Index("ix_node_artifacts_node_exec", "node_exec_id"),
        # 租户维度时间排序
        Index("ix_node_artifacts_tenant_created", "tenant_id", "created_at"),
    )


class RunArtifact(Base, TimestampMixin, TenantMixin, ModelSerializerMixin):
    """Run 级产物聚合（最终交付物）.

    PK 为 ``run_id``（每个 run 多个 artifact_type 时通过单独列区分）。
    设计上每个 run 每种 artifact_type 各一行记录；如有多个，需添加 PK 列。
    """

    __tablename__ = "run_artifacts"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=f"产物类型，取值 {RUN_ARTIFACT_TYPE_VALUES}",
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="类型相关元数据",
    )

    __table_args__ = (
        Index("ix_run_artifacts_run", "run_id"),
        Index("ix_run_artifacts_tenant_created", "tenant_id", "created_at"),
    )


__all__ = [
    "NODE_ARTIFACT_TYPE_VALUES",
    "RUN_ARTIFACT_TYPE_VALUES",
    "NodeArtifact",
    "RunArtifact",
]
