"""JWT 安全工具."""

from datetime import datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from hscredit_studio.core.config import settings


def _truncate_password(password: str) -> bytes:
    """bcrypt 限制 72 字节 — 截断以兼容长密码.

    注：长密码通常不应该出现，但为防御性兜底截断。
    """
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    """哈希密码 — 使用 bcrypt 直接（避开 passlib 的 wrap-bug 检测陷阱）."""
    pwd_bytes = _truncate_password(password)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码."""
    try:
        pwd_bytes = _truncate_password(plain_password)
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | dict[str, Any],
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """创建访问 token.

    Parameters
    ----------
    subject:
        用户标识（字符串 sub）或已包含 sub 的 claims dict。
    expires_delta:
        自定义过期时长；None 时使用 ``settings.jwt_access_token_expire_minutes``。
    extra_claims:
        额外 claims（合并到 token payload，例如 ``tenant_id`` / ``role``）。
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode: dict[str, Any] = {"exp": expire, "iat": datetime.utcnow(), "type": "access"}
    if isinstance(subject, str):
        to_encode["sub"] = subject
    else:
        to_encode.update(subject)
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """创建刷新 token.

    Parameters
    ----------
    subject:
        用户标识（sub）。
    extra_claims:
        额外 claims（合并到 token payload，例如 ``tenant_id`` / ``role``）。
    """
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """解码并验证 token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
