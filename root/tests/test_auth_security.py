import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from jose import JWTError, jwt
from passlib.hash import bcrypt
from sqlalchemy import select

from app.auth.security import (
    LEGACY_BCRYPT_MAX_BYTES,
    _truncate_for_bcrypt,
    create_access_token,
    decode_token,
    get_password_hash,
    verify_and_update_password,
    verify_password,
)
from app.models import models
from app.core.config import settings


def _make_legacy_hash(password: str) -> str:
    prepared = _truncate_for_bcrypt(password)
    # Directly call the legacy handler to avoid deprecated CryptContext APIs
    return bcrypt.hash(prepared)


def test_get_password_hash_uses_argon2id_by_default():
    password = "Secur3P@ss!"
    hashed = get_password_hash(password)
    assert hashed.startswith("$argon2id$")


def test_get_password_hash_enforces_length_bounds():
    with pytest.raises(ValueError) as exc_ru:
        get_password_hash("short", locale="ru")

    assert str(exc_ru.value) == "Пароль должен содержать от 8 до 200 символов."

    with pytest.raises(ValueError) as exc_en:
        get_password_hash("x" * 201, locale="en")

    assert str(exc_en.value) == "Password must be between 8 and 200 characters long."


def test_password_policy_allows_limits():
    minimal = "Abcd123!"
    maximal = "A" * 196 + "1234"

    assert len(minimal) == 8
    assert len(maximal) == 200

    assert get_password_hash(minimal).startswith("$argon2id$")
    assert get_password_hash(maximal).startswith("$argon2id$")


def test_verify_and_update_password_migrates_bcrypt():
    password = "LegacySecur3!"
    legacy_hash = _make_legacy_hash(password)

    assert legacy_hash.startswith("$2")

    verified, new_hash = verify_and_update_password(password, legacy_hash)

    assert verified is True
    assert new_hash is not None
    assert new_hash.startswith("$argon2id$")
    assert verify_password(password, new_hash)


def test_verify_and_update_password_invalid_password():
    password = "ValidPassw0rd!"
    legacy_hash = _make_legacy_hash(password)

    verified, new_hash = verify_and_update_password("wrong", legacy_hash)

    assert verified is False
    assert new_hash is None


def test_verify_and_update_password_up_to_date_hash():
    password = "UpToDateP@ss1"
    current_hash = get_password_hash(password)

    verified, new_hash = verify_and_update_password(password, current_hash)

    assert verified is True
    assert new_hash is None


def test_unicode_password_hashing():
    password = "Пароль🔒1234"
    hashed = get_password_hash(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)


def test_legacy_bcrypt_truncation_behavior():
    long_password = "a" * 80
    legacy_hash = _make_legacy_hash(long_password)

    truncated = _truncate_for_bcrypt(long_password)
    assert len(truncated.encode("utf-8")) == LEGACY_BCRYPT_MAX_BYTES

    assert verify_password(long_password, legacy_hash)

    mutated_after_limit = long_password[:72] + "b" * 8
    assert verify_password(mutated_after_limit, legacy_hash)

    mutated_before_limit = "b" + long_password[1:]
    assert not verify_password(mutated_before_limit, legacy_hash)


@pytest.mark.anyio
async def test_create_access_token_uses_active_signing_key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        ["new-key:new-secret", "legacy-key:old-secret"],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "new-key")

    token = await create_access_token("user-123")

    header = jwt.get_unverified_header(token)
    assert header["kid"] == "new-key"

    with pytest.raises(JWTError):
        jwt.decode(token, "old-secret", algorithms=[settings.algorithm])

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-123"


@pytest.mark.anyio
async def test_decode_token_accepts_legacy_and_active_secrets(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        ["active:new-secret", "legacy:old-secret"],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "active")

    now = datetime.now(UTC)
    legacy_payload = {
        "sub": "legacy-user",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "legacy-jti",
    }
    legacy_token = jwt.encode(legacy_payload, "old-secret", algorithm=settings.algorithm)

    rotated_token = await create_access_token("current-user")

    legacy_decoded = decode_token(legacy_token)
    assert legacy_decoded is not None
    assert legacy_decoded["sub"] == "legacy-user"

    rotated_decoded = decode_token(rotated_token)
    assert rotated_decoded is not None
    assert rotated_decoded["sub"] == "current-user"


@pytest.mark.anyio
async def test_login_migrates_legacy_hash(async_client, user_factory, db_session):
    password = "LegacyLog1n!"
    legacy_hash = _make_legacy_hash(password)

    user = await user_factory(hashed_password=legacy_hash, is_active=True)

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    await db_session.refresh(user)
    assert user.hashed_password.startswith("$argon2id$")
    assert verify_password(password, user.hashed_password)


@pytest.mark.anyio
async def test_create_user_requires_authentication(async_client):
    payload = {
        "email": "unauthorized@example.com",
        "password": "ValidPass123!",
        "role": "student",
    }

    response = await async_client.post("/users", json=payload)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.anyio
async def test_create_user_forbidden_for_non_admin(async_client, user_factory):
    password = "UserPass123!"
    user = await user_factory(
        role="student",
        hashed_password=get_password_hash(password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

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
    assert response.json() == {"detail": "Access denied"}


@pytest.mark.anyio
async def test_create_user_allows_admin(async_client, user_factory):
    password = "AdminPass123!"
    admin = await user_factory(
        role="admin",
        hashed_password=get_password_hash(password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

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


@pytest.mark.anyio
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

    user = await db_session.get(models.User, body["id"])
    assert user is not None
    assert user.email == raw_email.lower()


@pytest.mark.anyio
async def test_login_accepts_mixed_case_username(async_client, user_factory):
    password = "ValidLogin123!"
    user = await user_factory(
        email="login-case@example.com",
        hashed_password=get_password_hash(password),
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
    assert body["access_token"]


@pytest.mark.anyio
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

    after = await db_session.execute(base_query)
    after_count = len(after.scalars().all())
    assert after_count == before_count + 1


@pytest.mark.anyio
async def test_admin_update_normalizes_email(async_client, user_factory, db_session):
    admin_password = "AdminMixed123!"
    admin = await user_factory(
        role="admin",
        hashed_password=get_password_hash(admin_password),
    )

    login_response = await async_client.post(
        "/auth/login",
        data={"username": admin.email, "password": admin_password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]

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
