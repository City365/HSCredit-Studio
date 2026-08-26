"""对象存储客户端 — MinIO/S3 按租户分桶.

依据 :file:`docs/design/01-system-architecture.md` 第 1.2.3 节
以及 :file:`docs/design/06-non-functional.md` 第 6.2 节:

- Bucket 命名: ``{s3_bucket_prefix}-{tenant_slug}``(slug 由 UUID 去横线截 32 位)。
- 路径格式: ``tenants/{tenant_id}/runs/{run_id}/nodes/{node_exec_id}/{key}``。
- 跨租户防护: 所有上传/下载都需传入 ``tenant_id``,
  路径必须以 ``tenants/{tenant_id}/`` 前缀开头(SDK 层校验)。

底层使用 :mod:`aiobotocore` 异步 S3 SDK;
每次操作通过 ``session.create_client`` 创建短生命周期 client,
复用的是 ``AioSession`` 的 HTTP 连接池。
"""
from __future__ import annotations

from typing import Any, BinaryIO
from uuid import UUID

import aiobotocore.session

from hscredit_studio.core.config import settings
from hscredit_studio.core.logging import get_logger

_log = get_logger(__name__)

_session: aiobotocore.session.AioSession | None = None


async def get_storage_client() -> aiobotocore.session.AioSession:
    """获取 aiobotocore :class:`AioSession` 单例.

    ``AioSession`` 是顶层连接池容器;具体请求通过
    ``session.create_client("s3", ...)`` 创建短生命周期 client。
    """
    global _session
    if _session is None:
        _session = aiobotocore.session.AioSession()
        _log.info("storage_session_created", endpoint=settings.s3_endpoint)
    return _session


def get_tenant_bucket(tenant_id: UUID | str) -> str:
    """按租户 ID 获取 bucket 名称.

    规则:
        ``{s3_bucket_prefix}-{tenant_slug}``

    其中 ``tenant_slug`` 是去除 UUID 横线后的前 32 个字符。

    Args:
        tenant_id: 租户 UUID 或其字符串形式。

    Returns:
        完整 bucket 名称,例: ``hscredit-dev-a1b2c3d4...``.
    """
    slug = str(tenant_id).replace("-", "")[:32]
    return f"{settings.s3_bucket_prefix}-{slug}"


def _build_s3_client_kwargs() -> dict[str, Any]:
    """构造 aiobotocore ``create_client`` 的公共参数.

    集中起来便于测试替换(注入假的 endpoint_url 等)。
    """
    return {
        "endpoint_url": settings.s3_endpoint,
        "aws_access_key_id": settings.s3_access_key,
        "aws_secret_access_key": settings.s3_secret_key,
        "region_name": settings.s3_region,
    }


async def upload_bytes(
    tenant_id: UUID,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> str:
    """上传字节数据到租户 bucket.

    Args:
        tenant_id: 租户 UUID。
        key: 对象 key,必须以 ``tenants/{tenant_id}/`` 开头(SDK 层校验)。
        data: 字节内容。
        content_type: MIME 类型,默认 ``application/octet-stream``。
        metadata: 自定义元数据(S3 限制键值对均为 ASCII 字符串)。

    Returns:
        完整 ``s3://{bucket}/{key}`` 路径。
    """
    session = await get_storage_client()
    bucket = get_tenant_bucket(tenant_id)
    async with session.create_client("s3", **_build_s3_client_kwargs()) as client:
        await client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata=metadata or {},
        )
    return f"s3://{bucket}/{key}"


async def upload_fileobj(
    tenant_id: UUID,
    key: str,
    fileobj: BinaryIO,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> str:
    """上传文件对象到租户 bucket.

    Args:
        tenant_id: 租户 UUID。
        key: 对象 key。
        fileobj: 二进制文件对象。
        content_type: MIME 类型。
        metadata: 自定义元数据。

    Returns:
        完整 ``s3://{bucket}/{key}`` 路径。
    """
    data = fileobj.read()
    return await upload_bytes(tenant_id, key, data, content_type, metadata)


async def download_bytes(tenant_id: UUID, key: str) -> bytes:
    """下载字节数据.

    Args:
        tenant_id: 租户 UUID。
        key: 对象 key。

    Returns:
        完整字节内容。

    Raises:
        Exception: S3 抛 ``ClientError``(NoSuchKey / NoSuchBucket 等),
                  由调用方按业务上下文处理。
    """
    session = await get_storage_client()
    bucket = get_tenant_bucket(tenant_id)
    async with session.create_client("s3", **_build_s3_client_kwargs()) as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        async with response["Body"] as stream:
            return await stream.read()


async def object_exists(tenant_id: UUID, key: str) -> bool:
    """检查对象是否存在.

    通过 ``head_object`` 实现(比 ``get_object`` 更轻量,不下载 body)。
    """
    from botocore.exceptions import ClientError  # aiobotocore 依赖 botocore

    session = await get_storage_client()
    bucket = get_tenant_bucket(tenant_id)
    try:
        async with session.create_client("s3", **_build_s3_client_kwargs()) as client:
            await client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


async def presigned_download_url(
    tenant_id: UUID,
    key: str,
    expires_in: int = 3600,
) -> str:
    """生成预签名下载 URL.

    Args:
        tenant_id: 租户 UUID。
        key: 对象 key。
        expires_in: URL 有效期(秒),默认 1 小时。

    Returns:
        浏览器可直接 ``GET`` 的 URL。
    """
    session = await get_storage_client()
    bucket = get_tenant_bucket(tenant_id)
    async with session.create_client("s3", **_build_s3_client_kwargs()) as client:
        url = await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url


async def close_storage_client() -> None:
    """关闭存储客户端.

    ``AioSession`` 没有顶层 close(连接在 ``create_client`` 上下文内释放);
    这里仅清空单例指针,便于 GC。
    """
    global _session
    _session = None


__all__ = [
    "get_storage_client",
    "get_tenant_bucket",
    "upload_bytes",
    "upload_fileobj",
    "download_bytes",
    "object_exists",
    "presigned_download_url",
    "close_storage_client",
]