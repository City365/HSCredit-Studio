"""单元测试 — JWT + bcrypt."""
import pytest
from datetime import timedelta
from hscredit_studio.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from hscredit_studio.core.exceptions import AuthenticationError


def test_hash_and_verify_password():
    plain = "mySecurePassword123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrongPassword", hashed) is False


def test_create_access_token():
    token = create_access_token(subject="user-123")
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_create_refresh_token():
    token = create_refresh_token(subject="user-123")
    payload = decode_token(token)
    assert payload["type"] == "refresh"


def test_decode_token_with_invalid_signature():
    from hscredit_studio.core.security import decode_token
    with pytest.raises(ValueError):
        decode_token("invalid.token.here")


def test_token_with_extra_claims():
    token = create_access_token(
        subject="user-123",
        extra_claims={"tenant_id": "tid-1", "role": "admin"},
    )
    payload = decode_token(token)
    assert payload["tenant_id"] == "tid-1"
    assert payload["role"] == "admin"


def test_token_expiration():
    token = create_access_token(subject="user-123", expires_delta=timedelta(seconds=-1))
    from hscredit_studio.core.security import decode_token
    with pytest.raises(ValueError):
        decode_token(token)


def test_bcrypt_hash_is_not_plaintext():
    """哈希不应回显原密码."""
    plain = "secret123"
    hashed = hash_password(plain)
    assert plain not in hashed
    assert hashed.startswith("$2")  # bcrypt 哈希标识


def test_different_passwords_produce_different_hashes():
    """同一密码两次哈希结果不同（bcrypt salt）."""
    plain = "samePassword"
    h1 = hash_password(plain)
    h2 = hash_password(plain)
    assert h1 != h2
    assert verify_password(plain, h1) is True
    assert verify_password(plain, h2) is True