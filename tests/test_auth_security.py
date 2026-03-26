import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import status
from jwt.exceptions import PyJWTError
from sqlalchemy import select

from app.auth.security import (
    _mint_pure_jwt,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.config import settings
from app.models import models


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
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        [
            "new-key:new-secret-token-32-chars-long-here",
            "legacy-key:old-secret-token-32-chars-long-here",
        ],
    )
    monkeypatch.setattr(settings, "jwt_active_kid", "new-key")

    token = _mint_pure_jwt("user-123")

    header = jwt.get_unverified_header(token)
    assert header["kid"] == "new-key"

    with pytest.raises(PyJWTError):
        jwt.decode(
            token,
            "old-secret-token-32-chars-long-here",
            algorithms=[settings.algorithm],
        )

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-123"


@pytest.mark.asyncio
async def test_decode_token_accepts_legacy_and_active_secrets(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_signing_keys",
        [
            "active:new-secret-token-32-chars-long-here",
            "legacy:old-secret-token-32-chars-long-here",
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
        "old-secret-token-32-chars-long-here",
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

    after = await db_session.execute(base_query)
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
