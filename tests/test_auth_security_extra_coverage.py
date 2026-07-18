from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, mock_open, patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.auth.security as sec
from app.auth.security import (
    _container_cpu_count,
    _format_password_class_labels,
    _get_cached_public_key_pem,
    close_hibp_client,
    decode_token,
    get_password_hash_sync,
    validate_password_hibp,
    verify_and_update_password_sync,
    verify_password_sync,
)
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_hibp_client() -> Generator[None]:
    sec._hibp_client = None
    yield
    sec._hibp_client = None


def test_container_cpu_count_cgroups_v1() -> None:
    # 1. Successful quota/period parsing
    m_open = mock_open()
    m_open.side_effect = lambda path, *args, **kwargs: mock_open(
        read_data="100000" if "quota" in path else "50000"
    )()

    with patch("builtins.open", m_open):
        with patch(
            "os.sched_getaffinity", create=True, side_effect=NotImplementedError
        ):
            val = _container_cpu_count()
            assert val == 2

    # 2. quota <= 0 or period <= 0 (causes fallback to os.cpu_count)
    m_open_zero = mock_open()
    m_open_zero.side_effect = lambda path, *args, **kwargs: mock_open(
        read_data="0" if "quota" in path else "50000"
    )()

    with patch("builtins.open", m_open_zero):
        with patch(
            "os.sched_getaffinity", create=True, side_effect=NotImplementedError
        ):
            val = _container_cpu_count()
            assert val == (os.cpu_count() or 2)


def test_format_password_class_labels() -> None:
    labels = _format_password_class_labels(["uppercase", "digit"], locale="en")
    assert "uppercase letters" in labels
    assert "digits" in labels


def test_password_policy_missing_classes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "password_require_uppercase", True)
    monkeypatch.setattr(settings, "password_require_digit", True)
    monkeypatch.setattr(settings, "password_require_lowercase", False)
    monkeypatch.setattr(settings, "password_require_special", False)

    with pytest.raises(ValueError) as exc:
        get_password_hash_sync("abcdefgh", validate_policy=True, locale="en")
    assert "uppercase letters" in str(exc.value)


def test_password_policy_min_classes(monkeypatch) -> None:
    # 1. Trigger min_classes check
    monkeypatch.setattr(settings, "password_require_uppercase", False)
    monkeypatch.setattr(settings, "password_require_lowercase", False)
    monkeypatch.setattr(settings, "password_require_digit", False)
    monkeypatch.setattr(settings, "password_require_special", False)
    monkeypatch.setattr(settings, "password_min_character_classes", 3)

    # Password only has 2 classes: lowercase and digits (no upper, no symbol)
    with pytest.raises(ValueError) as exc:
        get_password_hash_sync("abcdefgh123", validate_policy=True, locale="en")
    assert "categories" in str(exc.value)

    # 2. min_classes is 0 (takes False branch of min_classes > 0)
    monkeypatch.setattr(settings, "password_min_character_classes", 0)
    hashed = get_password_hash_sync("abcdefgh123", validate_policy=True, locale="en")
    assert hashed.startswith("$argon2id$")


def test_password_policy_zxcvbn_score(monkeypatch) -> None:
    monkeypatch.setattr(settings, "password_zxcvbn_min_score", 3)

    # 1. Trivial password with sufficient length and characters but weak zxcvbn score
    with pytest.raises(ValueError) as exc:
        get_password_hash_sync("abc123XYZ!!", validate_policy=True, locale="en")
    assert "weak" in str(exc.value)

    # 2. Strong password that passes zxcvbn checks (takes False branch of score < min_score)
    hashed = get_password_hash_sync(
        "Tr0ub4dor&3!Xy7Mn-Qp", validate_policy=True, locale="en"
    )
    assert hashed.startswith("$argon2id$")

    # 3. min_score is 0 (takes False branch of min_score > 0)
    monkeypatch.setattr(settings, "password_zxcvbn_min_score", 0)
    hashed2 = get_password_hash_sync("abc123XYZ!!", validate_policy=True, locale="en")
    assert hashed2.startswith("$argon2id$")


def test_get_password_hash_no_policy_validation() -> None:
    hashed = get_password_hash_sync("abc", validate_policy=False)
    assert hashed.startswith("$argon2id$")


def test_verify_password_sync_branches() -> None:
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    hashed = hasher.hash("password")
    assert verify_password_sync("wrong-password", hashed) is False
    assert verify_password_sync("password", "$argon2id$invalid-hash-structure") is False
    assert verify_password_sync("password", "legacy-hash-structure") is False


def test_verify_and_update_password_sync_branches() -> None:
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    hashed = hasher.hash("password")
    verified, new_hash = verify_and_update_password_sync("wrong-password", hashed)
    assert verified is False
    assert new_hash is None

    verified, new_hash = verify_and_update_password_sync(
        "password", "$argon2id$invalid"
    )
    assert verified is False
    assert new_hash is None

    with patch("app.auth.security._verify_legacy_bcrypt", return_value=True):
        verified, new_hash = verify_and_update_password_sync("password", "legacy-hash")
        assert verified is True
        assert new_hash.startswith("$argon2id$")

    with patch(
        "app.auth.security._verify_legacy_bcrypt", side_effect=RuntimeError("error")
    ):
        verified, new_hash = verify_and_update_password_sync("password", "legacy-hash")
        assert verified is False
        assert new_hash is None

    legacy_hasher = PasswordHasher(memory_cost=8192, time_cost=1, parallelism=1)
    legacy_hash = legacy_hasher.hash("password")
    verified, new_hash = verify_and_update_password_sync("password", legacy_hash)
    assert verified is True
    assert new_hash is not None
    assert new_hash.startswith("$argon2id$")


def test_get_cached_public_key_pem_and_eviction() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    pem1 = _get_cached_public_key_pem("kid-1", private_pem)
    pem2 = _get_cached_public_key_pem("kid-1", private_pem)
    assert pem1 == pem2

    with patch.dict(sec._public_key_cache, {f"k{i}": f"v{i}" for i in range(32)}):
        pem3 = _get_cached_public_key_pem("new-kid", private_pem)
        assert pem3 is not None

    # Test double-checked lock: key added while waiting for lock
    class MockCacheLock:
        def __enter__(self) -> MockCacheLock:
            sec._public_key_cache["new-kid-2"] = "some-cached-pem"
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    with patch("app.auth.security._public_key_cache_lock", MockCacheLock()):
        pem4 = _get_cached_public_key_pem("new-kid-2", private_pem)
        assert pem4 == "some-cached-pem"


def test_decode_token_branches(monkeypatch) -> None:
    with patch(
        "app.core.config.Settings.jwt_signing_key_registry",
        new_callable=PropertyMock,
    ) as mock_registry:
        mock_registry.return_value = {}
        assert decode_token("some-token") is None

    # Token with invalid format raising JWTError
    assert decode_token("invalid-token-dots") is None

    now = datetime.now(UTC)
    payload = {
        "sub": "user-123",
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=10),
        "jti": "some-jti",
    }
    token_no_kid = jwt.encode(payload, "secret", algorithm="HS256")
    assert decode_token(token_no_kid) is None

    token_unknown_kid = jwt.encode(
        payload, "secret", algorithm="HS256", headers={"kid": "unknown"}
    )
    assert decode_token(token_unknown_kid) is None

    # Token with wrong signature (causes JWTError in loop verification)
    token_wrong_sig = jwt.encode(
        payload,
        "wrong-secret-key-32-chars-long",
        algorithm="HS256",
        headers={"kid": "hskey"},
    )
    monkeypatch.setattr(
        settings, "jwt_signing_keys", ["hskey:another-secret-key-32-chars-long"]
    )
    assert decode_token(token_wrong_sig) is None

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    rs256_token = jwt.encode(
        payload, private_pem, algorithm="RS256", headers={"kid": "rskey"}
    )

    monkeypatch.setattr(settings, "algorithm", "RS256")

    # Pass the PEM string directly in python list (no replace is needed)
    monkeypatch.setattr(settings, "jwt_signing_keys", [f"rskey:{private_pem}"])
    decoded = decode_token(rs256_token)
    assert decoded is not None
    assert decoded["sub"] == "user-123"

    monkeypatch.setattr(settings, "jwt_signing_keys", [f"rskey:{public_pem}"])
    decoded2 = decode_token(rs256_token)
    assert decoded2 is not None
    assert decoded2["sub"] == "user-123"

    # Use a different kid to avoid cache hit
    rs256_token_invalid = jwt.encode(
        payload, private_pem, algorithm="RS256", headers={"kid": "rskey-invalid"}
    )
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        ["rskey-invalid:-----BEGIN PRIVATE KEY-----\ninvalid\n"],
    )
    assert decode_token(rs256_token_invalid) is None


@pytest.mark.asyncio
async def test_validate_password_hibp_real_flow_and_errors() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "ABC12:0\nDEF34:0\n"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    with patch("app.auth.security.httpx.AsyncClient", return_value=mock_client):
        await validate_password_hibp("SafePassword123!")
        assert sec._hibp_client is mock_client

        client = await sec._get_hibp_client()
        assert client is mock_client

        await close_hibp_client()
        assert sec._hibp_client is None
        mock_client.aclose.assert_awaited_once()

    # Test double-checked lock: _hibp_client initialized while waiting for lock
    class MockLock:
        async def __aenter__(self) -> MockLock:
            sec._hibp_client = "mocked-inside-lock"
            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    with patch("app.auth.security._get_hibp_client_lock", return_value=MockLock()):
        sec._hibp_client = None
        client2 = await sec._get_hibp_client()
        assert client2 == "mocked-inside-lock"

    # Reset client after lock test
    sec._hibp_client = None

    from app.auth.security import _calculate_lookup_hash

    sha1 = _calculate_lookup_hash("pass")
    suffix = sha1[5:]
    mock_resp.text = f"{suffix}:INVALID_COUNT\n"

    mock_client.get = AsyncMock(return_value=mock_resp)
    with patch("app.auth.security.httpx.AsyncClient", return_value=mock_client):
        await validate_password_hibp("pass")
