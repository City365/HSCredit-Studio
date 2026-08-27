"""节点产物序列化与持久化服务.

Phase 1 简化策略（见设计文档 09 第 9.3.4 节 + 14 第 14.6 节）：

- **DataFrame** → Apache Parquet（pyarrow，含 schema 校验，体积小）
- **Model/Binner/Encoder/Scorecard/Rule/Selector**（任意 sklearn 兼容对象）→ pickle
- **bytes** → 透传（按 content_type 推断 artifact_type）
- **str / dict** → JSON

每个 output 写入 :class:`NodeArtifact` ORM 一行（含 ``sha256`` 用于去重与缓存命中判断）。
"""

from __future__ import annotations

import hashlib
import io
import json
import pickle
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hscredit_studio.core.logging import get_logger
from hscredit_studio.models.artifact import NodeArtifact
from hscredit_studio.models.run import NodeExecution
from hscredit_studio.services import storage

_log = get_logger(__name__)

# 节点契约里 output_port 的 type 字段约定：
# - "DataFrame" / "Binner" / "Encoder" / "Selector" / "ScoreCard" / "Model" / "Rule"
# - "bytes" / "str" / "dict"
# 节点 run() 返回的 Python 对象 type(value).__name__ 通常能匹配上面字符串。

DATAFRAME_TYPES = ("DataFrame",)


def infer_artifact_type(value: Any) -> str:
    """根据 Python 对象类型推断 artifact_type（用于 NodeArtifact 落库与 S3 metadata）.

    规则：
        - pandas.DataFrame → ``parquet``
        - bytes / bytearray → ``bin``（透传；如有 contract 声明则覆盖）
        - str → ``json``
        - dict / list → ``json``
        - 其他（Model/Binner/Encoder/...）→ ``model``（pickle）
    """
    type_name = type(value).__name__
    module_name = getattr(type(value), "__module__", "")

    if type_name == "DataFrame" or module_name.startswith("pandas"):
        return "parquet"
    if isinstance(value, (bytes, bytearray)):
        return "bin"
    if isinstance(value, str):
        return "json"
    if isinstance(value, (dict, list)):
        return "json"
    return "model"


def content_type_for(artifact_type: str) -> str:
    """artifact_type → S3 Content-Type."""
    mapping = {
        "parquet": "application/vnd.apache.parquet",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pmml": "application/pmml+xml",
        "json": "application/json",
        "png": "image/png",
        "model": "application/octet-stream",
        "binner": "application/octet-stream",
        "scorecard": "application/octet-stream",
        "bin": "application/octet-stream",
    }
    return mapping.get(artifact_type, "application/octet-stream")


def serialize_for_upload(value: Any, artifact_type: str | None = None) -> tuple[bytes, str, str, int]:
    """序列化对象为可上传字节流.

    Parameters
    ----------
    value:
        任意 Python 对象。
    artifact_type:
        显式指定产物类型（与节点契约对应）。None 时按 :func:`infer_artifact_type` 推断。

    Returns
    -------
    (bytes, content_type, sha256, size_bytes)
    """
    atype = artifact_type or infer_artifact_type(value)

    if atype == "parquet":
        # 显式 import 延迟到调用时，避免 pandas 强依赖
        import pandas as pd

        if not isinstance(value, pd.DataFrame):
            # 包装单元素 DataFrame（防御性）
            value = pd.DataFrame({"value": [value]})
        buf = io.BytesIO()
        value.to_parquet(buf, index=False, engine="pyarrow")
        data = buf.getvalue()
    elif atype == "json":
        if isinstance(value, (dict, list)):
            data = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(value, str):
            data = value.encode("utf-8")
        else:
            data = json.dumps(str(value), ensure_ascii=False).encode("utf-8")
    elif atype == "bin":
        data = bytes(value)
    else:
        # model / binner / scorecard 等任意 pickle-able 对象
        data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)

    sha = hashlib.sha256(data).hexdigest()
    return data, content_type_for(atype), sha, len(data)


def deserialize_from_storage(artifact_type: str, data: bytes) -> Any:
    """反序列化字节流为 Python 对象."""
    if artifact_type == "parquet":
        import pandas as pd

        return pd.read_parquet(io.BytesIO(data))
    if artifact_type == "json":
        return json.loads(data.decode("utf-8"))
    if artifact_type == "bin":
        return data
    # model / binner / scorecard 等
    return pickle.loads(data)


def build_storage_key(
    tenant_id: UUID | None,
    run_id: UUID,
    node_exec_id: UUID,
    output_name: str,
    artifact_type: str,
) -> str:
    """构造租户隔离的 S3 存储 key.

    路径: ``tenants/{tenant_id}/runs/{run_id}/nodes/{node_exec_id}/{output_name}.{ext}``
    """
    ext_map = {
        "parquet": "parquet",
        "excel": "xlsx",
        "pmml": "pmml",
        "json": "json",
        "png": "png",
        "model": "pkl",
        "binner": "pkl",
        "scorecard": "pkl",
        "bin": "bin",
    }
    ext = ext_map.get(artifact_type, "bin")
    base = f"runs/{run_id}/nodes/{node_exec_id}/{output_name}.{ext}"
    if tenant_id is not None:
        return f"tenants/{tenant_id}/{base}"
    return base


async def save_node_output(
    session: AsyncSession,
    tenant_id: UUID,
    ne: NodeExecution,
    output_name: str,
    value: Any,
    artifact_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """序列化 + 上传 + 写 NodeArtifact 一行.

    Returns
    -------
    storage_path: S3 key（不含 bucket），供 ``NodeExecution.artifact_paths[output_name]`` 存储。
    """
    atype = artifact_type or infer_artifact_type(value)
    data, ctype, sha, size = serialize_for_upload(value, atype)

    storage_key = build_storage_key(tenant_id, ne.run_id, ne.node_exec_id, output_name, atype)

    # 上传到 S3
    await storage.upload_bytes(
        tenant_id=tenant_id,
        key=storage_key,
        data=data,
        content_type=ctype,
        metadata={"sha256": sha, "artifact_type": atype},
    )

    # 落 NodeArtifact 元数据（幂等：同 node_exec_id + artifact_type + sha256 唯一）
    # 用 Postgres ``ON CONFLICT DO NOTHING`` 处理节点重试时产物完全相同的情况
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    insert_stmt = pg_insert(NodeArtifact).values(
        node_exec_id=ne.node_exec_id,
        tenant_id=tenant_id,
        artifact_type=atype,
        storage_path=storage_key,
        size_bytes=size,
        sha256=sha,
        metadata_=metadata or {},
    )
    insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["node_exec_id", "artifact_type", "sha256"])
    await session.execute(insert_stmt)

    _log.debug(
        "artifact_saved",
        node_exec_id=str(ne.node_exec_id),
        output_name=output_name,
        artifact_type=atype,
        size_bytes=size,
        sha256=sha[:12],
    )
    return storage_key


async def load_node_inputs(
    session: AsyncSession,
    tenant_id: UUID,
    artifact_paths: dict[str, str],
    _input_ne: Any | None = None,
) -> dict[str, Any]:
    """从 artifact_paths 反序列化上游节点输出.

    Parameters
    ----------
    artifact_paths:
        ``NodeExecution.artifact_paths`` —— ``{output_name: storage_key}`` 或
        executor 写入的 ``{upstream_node_id}.{output_name}: storage_key`` 形式。
    """
    if not artifact_paths:
        return {}

    inputs: dict[str, Any] = {}
    for qualified_key, storage_key in artifact_paths.items():
        # 兼容 executor 写入的 "{upstream_node_id}.{output_name}" 命名空间形式
        if "." in qualified_key and _input_ne is not None:
            _upstream_node_id, _, output_name = qualified_key.partition(".")
        else:
            output_name = qualified_key
        # 从 S3 key 解析 artifact_type：取 .pkl/.parquet/.json 后缀
        ext = storage_key.rsplit(".", 1)[-1]
        ext_to_type = {
            "parquet": "parquet",
            "json": "json",
            "pkl": "model",
            "xlsx": "excel",
            "pmml": "pmml",
            "png": "png",
            "bin": "bin",
        }
        atype = ext_to_type.get(ext, "bin")

        data = await storage.download_bytes(tenant_id, storage_key)
        value = deserialize_from_storage(atype, data)
        # 同一 output_name 被多个上游节点覆盖（如 3 个 bin_* 节点都输出 df），
        # 合并为 list 保留全部上游输出，避免后续节点拿到不完整输入。
        if output_name in inputs:
            if not isinstance(inputs[output_name], list):
                inputs[output_name] = [inputs[output_name]]
            inputs[output_name].append(value)
        else:
            inputs[output_name] = value
    return inputs


__all__ = [
    "build_storage_key",
    "content_type_for",
    "deserialize_from_storage",
    "infer_artifact_type",
    "load_node_inputs",
    "save_node_output",
    "serialize_for_upload",
]
