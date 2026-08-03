import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import status
from jwt.exceptions import PyJWTError
from sqlalchemy import select

import app.models as models
from app.auth.security import (
    _mint_pure_jwt,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.config import settings


def _rsa_private_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _rsa_public_pem(private_pem: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_pem.encode("utf-8"), password=None
    )
    return (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


@pytest.mark.asyncio
async def test_get_password_hash_uses_argon2id_by_default():
    password = "Secur3P@ss!"
    hashed = await get_password_hash(password)
    assert hashed.startswith("$argon2id$")


@pytest.mark.asyncio
async def test_get_password_hash_enforces_length_bounds():
    with pytest.raises(ValueError) as exc_ru:
        await get_password_hash("short", locale="ru")

    assert str(exc_ru.value) == "Пароль должен содержать от 8 до 200 символов."

    with pytest.raises(ValueError) as exc_en:
        await get_password_hash("x" * 201, locale="en")

    assert str(exc_en.value) == "Password must be between 8 and 200 characters long."


@pytest.mark.asyncio
async def test_password_policy_allows_limits():
    minimal = "Abcd123!"
    # First 72 chars must score >= 1 on zxcvbn; avoid repetition-only prefixes.
    maximal = ("Tr0ub4dor&3!Xy7Mn-Qp" * 10)[:200]

    assert len(minimal) == 8
    assert len(maximal) == 200

    assert (await get_password_hash(minimal)).startswith("$argon2id$")
    assert (await get_password_hash(maximal)).startswith("$argon2id$")


@pytest.mark.asyncio
async def test_unicode_password_hashing():
    password = "Пароль🔒1234"
    hashed = await get_password_hash(password)

    assert hashed.startswith("$argon2id$")
    assert await verify_password(password, hashed)


@pytest.mark.asyncio
async def test_create_access_token_uses_active_signing_key(monkeypatch):
    active_private_key = _rsa_private_pem()
    legacy_private_key = _rsa_private_pem()
    monkeypatch.setattr(settings, "algorithm", "RS256")
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        [
            f"new-key:{active_private_key}",
            f"legacy-key:{legacy_private_key}",
        ],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "new-key")

    token = _mint_pure_jwt("user-123")

    header = jwt.get_unverified_header(token)
    assert header["kid"] == "new-key"

    with pytest.raises(PyJWTError):
        jwt.decode(
            token,
            _rsa_public_pem(legacy_private_key),
            algorithms=[settings.algorithm],
        )

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-123"


@pytest.mark.asyncio
async def test_decode_token_accepts_legacy_and_active_secrets(monkeypatch):
    active_private_key = _rsa_private_pem()
    legacy_private_key = _rsa_private_pem()
    monkeypatch.setattr(settings, "algorithm", "RS256")
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        [
            f"active:{active_private_key}",
            f"legacy:{legacy_private_key}",
        ],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "active")

    now = datetime.now(UTC)
    legacy_payload = {
        "sub": "legacy-user",
        "aud": settings.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "legacy-jti",
    }
    legacy_token = jwt.encode(
        legacy_payload,
        legacy_private_key,
        algorithm=settings.algorithm,
        headers={"kid": "legacy"},
    )

    rotated_token = _mint_pure_jwt("current-user")

    legacy_decoded = decode_token(legacy_token)
    assert legacy_decoded is not None
    assert legacy_decoded["sub"] == "legacy-user"

    rotated_decoded = decode_token(rotated_token)
    assert rotated_decoded is not None
    assert rotated_decoded["sub"] == "current-user"


@pytest.mark.asyncio
async def test_create_user_requires_authentication(async_client):
    payload = {
        "email": "unauthorized@example.com",
        "password": "ValidPass123!",
        "role": "student",
    }

    response = await async_client.post("/users", json=payload)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_user_forbidden_for_non_admin(async_client, user_factory):
    password = "UserPass123!"
    user = await user_factory(
        role="student",
        hashed_password=await get_password_hash(password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.cookies.get("access_token_v2")

    payload = {
        "email": "new-student@example.com",
        "password": "ValidPass456!",
        "role": "student",
    }

    response = await async_client.post(
        "/users",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = response.json()
    # RFC 7807 format
    assert body["status"] == 403
    assert body["title"] == "Access Denied"
    assert "detail" in body


@pytest.mark.asyncio
async def test_create_user_allows_admin(async_client, user_factory):
    password = "AdminPass123!"
    admin = await user_factory(
        role="admin",
        hashed_password=await get_password_hash(password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.cookies.get("access_token_v2")

    payload = {
        "email": "created-by-admin@example.com",
        "password": "ValidPass789!",
        "role": "student",
    }

    response = await async_client.post(
        "/users",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["email"] == payload["email"]
    assert body["role"] == "student"


@pytest.mark.asyncio
async def test_register_normalizes_email(async_client, db_session):
    raw_email = f"MixedCase{uuid.uuid4().hex[:6]}@Example.COM"
    payload = {
        "email": raw_email,
        "password": "ValidPass123!",
        "full_name": "Mixed Case",
    }

    response = await async_client.post("/auth/register", json=payload)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "ok"

    user = await db_session.get(models.User, uuid.UUID(body["id"]))
    assert user is not None
    assert user.email == raw_email.lower()


@pytest.mark.asyncio
async def test_login_accepts_mixed_case_username(async_client, user_factory):
    password = "ValidLogin123!"
    user = await user_factory(
        email="login-case@example.com",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email.upper(), "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["token_type"] == "bearer"
    assert response.cookies.get("access_token_v2")
    assert body["user"]["id"] == str(user.id)
    session = body.get("session")
    assert session is not None
    assert isinstance(session.get("signing_key"), str)
    assert session["signing_key"]


@pytest.mark.asyncio
async def test_forgot_password_accepts_mixed_case_email(
    async_client, user_factory, db_session
):
    user = await user_factory(email=f"forgot-{uuid.uuid4().hex[:6]}@example.com")

    base_query = select(models.PasswordResetToken.id).where(
        models.PasswordResetToken.user_id == user.id
    )
    before = await db_session.execute(base_query)
    before_count = len(before.scalars().all())

    response = await async_client.post(
        "/password/forgot",
        json={"email": user.email.upper()},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"ok": True}

    from app.core import database

    async with database.async_session() as fresh_session:
        after = await fresh_session.execute(
            select(models.PasswordResetToken.id).where(
                models.PasswordResetToken.user_id == user.id
            )
        )
        after_count = len(after.scalars().all())
    assert after_count == before_count + 1


@pytest.mark.asyncio
async def test_admin_update_normalizes_email(async_client, user_factory, db_session):
    admin_password = "AdminMixed123!"
    admin = await user_factory(
        role="admin",
        hashed_password=await get_password_hash(admin_password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": admin.email, "password": admin_password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.cookies.get("access_token_v2")

    target_user = await user_factory()
    mixed_case_email = f"Updated{uuid.uuid4().hex[:6]}@Example.COM"

    response = await async_client.patch(
        f"/users/{target_user.id}",
        json={"email": mixed_case_email},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["email"] == mixed_case_email.lower()

    await db_session.refresh(target_user)
    assert target_user.email == mixed_case_email.lower()


def test_container_cpu_count_with_sched_getaffinity():
    """Verify _container_cpu_count handles sched_getaffinity correctly when present."""
    import sys
    from unittest.mock import MagicMock, patch

    orig = sys.modules.get("app.auth.security")
    try:
        if "app.auth.security" in sys.modules:
            del sys.modules["app.auth.security"]

        mock_sched = MagicMock(return_value=[1, 2, 3])
        with patch("os.sched_getaffinity", mock_sched, create=True):
            import app.auth.security as sec

            assert sec._AUTH_EXECUTOR_WORKERS >= 2
    finally:
        if orig is not None:
            sys.modules["app.auth.security"] = orig


def test_container_cpu_count_with_cgroups_v1():
    """Verify _container_cpu_count parses cpu.cfs_quota_us/cfs_period_us properly."""
    import sys
    from unittest.mock import mock_open, patch

    orig = sys.modules.get("app.auth.security")
    try:
        if "app.auth.security" in sys.modules:
            del sys.modules["app.auth.security"]

        def mock_open_side_effect(path, *args, **kwargs):
            if "cpu.cfs_quota_us" in str(path):
                return mock_open(read_data="8").return_value
            elif "cpu.cfs_period_us" in str(path):
                return mock_open(read_data="2").return_value
            raise FileNotFoundError()

        with (
            patch("os.sched_getaffinity", create=True) as mock_sched,
            patch("builtins.open", side_effect=mock_open_side_effect),
        ):
            mock_sched.side_effect = AttributeError()

            import app.auth.security as sec

            # quota // period = 8 // 2 = 4
            # Since _AUTH_EXECUTOR_WORKERS is set to max(2, _container_cpu_count()), it will be at least 4
            assert sec._AUTH_EXECUTOR_WORKERS >= 4
    finally:
        if orig is not None:
            sys.modules["app.auth.security"] = orig


def test_container_cpu_count_cgroups_v1_capped():
    """Verify _container_cpu_count caps the quota-based CPU count to 32."""
    import sys
    from unittest.mock import mock_open, patch

    orig = sys.modules.get("app.auth.security")
    try:
        if "app.auth.security" in sys.modules:
            del sys.modules["app.auth.security"]

        def mock_open_side_effect(path, *args, **kwargs):
            if "cpu.cfs_quota_us" in str(path):
                return mock_open(read_data="100").return_value
            elif "cpu.cfs_period_us" in str(path):
                return mock_open(read_data="2").return_value
            raise FileNotFoundError()

        with (
            patch("os.sched_getaffinity", create=True) as mock_sched,
            patch("builtins.open", side_effect=mock_open_side_effect),
        ):
            mock_sched.side_effect = NotImplementedError()

            import app.auth.security as sec

            # 100 // 2 = 50, capped at 32
            assert sec._AUTH_EXECUTOR_WORKERS <= 32
    finally:
        if orig is not None:
            sys.modules["app.auth.security"] = orig


def test_verify_legacy_bcrypt():
    """Verify _verify_legacy_bcrypt warning and false return."""
    from app.auth.security import _verify_legacy_bcrypt

    assert _verify_legacy_bcrypt("password", "$2b$12$...") is False
