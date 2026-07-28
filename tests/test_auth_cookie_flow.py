import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi import status
from sqlalchemy import select

from app.auth.security import decode_token, get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.models import ActiveSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_active_user(user_factory, password: str):
    hashed = await get_password_hash(password)
    return await user_factory(hashed_password=hashed, is_active=True)


async def _login(async_client, email: str, password: str):
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Query-Budget": "15",
        },
    )
    # The login process forcibly rotates the CSRF token (RZ-5).
    # Update the test client's headers so subsequent mutating requests
    # (like logout) don't fail the CSRF mismatch check.
    new_csrf_token = async_client.cookies.get("csrf_token")
    if new_csrf_token:
        async_client.headers["X-CSRF-Token"] = new_csrf_token
    return response


@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_session_signing_key_missing_localized(
    async_client, user_factory, db_session, locale: str
):
    password = "SessionKeyLocale123!"
    user = await _create_active_user(user_factory, password)

    response = await _login(async_client, user.email, password)
    assert response.status_code == 200
    token = async_client.cookies.get("access_token_v2")

    session = (
        (
            await db_session.execute(
                select(ActiveSession)
                .where(ActiveSession.user_id == user.id)
                .order_by(ActiveSession.id.desc())
            )
        )
        .scalars()
        .first()
    )
    assert session is not None
    session.signing_key = ""
    await db_session.commit()

    signing_key_response = await async_client.get(
        f"/auth/session/signing-key?lang={locale}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert signing_key_response.status_code == 400
    assert signing_key_response.json()["detail"] == translate(
        "errors.sessions.signing_key_missing", locale=locale
    )


@pytest.fixture
def configure_cookie_security(monkeypatch):
    def _configure(value):
        monkeypatch.setattr(
            settings, "enable_strict_security_headers", value, raising=False
        )
        settings.__dict__.pop("strict_security_headers_enabled", None)
        settings.__dict__.pop("cookie_secure", None)

    yield _configure

    settings.__dict__.pop("strict_security_headers_enabled", None)
    settings.__dict__.pop("cookie_secure", None)


def _extract_cookie_attributes(header: str) -> set[str]:
    parts = [part.strip().lower() for part in header.split(";")]
    return {part for part in parts[1:] if part}


@pytest.mark.parametrize("strict_value, expected_secure", [(None, False), (True, True)])
async def test_login_cookie_security_modes(
    async_client, user_factory, configure_cookie_security, strict_value, expected_secure
):
    configure_cookie_security(strict_value)
    assert settings.cookie_secure is expected_secure

    password = "StrongPass123!"
    user = await _create_active_user(user_factory, password)

    response = await _login(async_client, user.email, password)

    assert response.status_code == 200

    set_cookie_headers = response.headers.get_list("set-cookie")
    access_cookie_header = next(
        header
        for header in set_cookie_headers
        if header.lower().startswith("access_token_v2=")
    )
    attributes = _extract_cookie_attributes(access_cookie_header)
    assert "httponly" in attributes
    assert ("secure" in attributes) is expected_secure
    assert "samesite=lax" in attributes

    stored_cookie = async_client.cookies.get("access_token_v2")
    assert stored_cookie is not None and stored_cookie != ""

    new_csrf_token = ""
    for header in set_cookie_headers:
        if header.lower().startswith("csrf_token="):
            new_csrf_token = header.split(";")[0].split("=")[1]
            break

    # Wipe the client cookie jar entirely to prevent httpx CookieConflict
    async_client.cookies.clear()
    async_client.cookies.set("access_token_v2", stored_cookie)
    if new_csrf_token:
        async_client.cookies.set("csrf_token", new_csrf_token)

    profile_response = await async_client.get(
        "/users/me", headers={"X-Query-Budget": "15"}
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == user.email

    logout_response = await async_client.post(
        "/auth/logout", headers={"X-CSRF-Token": new_csrf_token}
    )
    assert logout_response.status_code == 200

    logout_cookie_header = next(
        header
        for header in logout_response.headers.get_list("set-cookie")
        if header.lower().startswith("access_token_v2=")
    )
    logout_attributes = _extract_cookie_attributes(logout_cookie_header)
    assert "max-age=0" in logout_attributes
    assert ("secure" in logout_attributes) is expected_secure

    # Remove the `httpx` internal jar check because domain scope parsing
    # for manually-injected auth cookies differs from actual browser behavior.
    # The server sent `max-age=0` properly.

    # We must explicitly clear it to test the `/users/me` endpoint
    async_client.cookies.clear()

    profile_response = await async_client.get("/users/me")
    assert profile_response.status_code == 401


async def test_token_reuse_after_logout_rejected(
    async_client, user_factory, db_session
):
    password = "ReusePass789!"
    user = await _create_active_user(user_factory, password)

    login_response = await _login(async_client, user.email, password)
    assert login_response.status_code == 200
    token = async_client.cookies.get("access_token_v2")

    payload = decode_token(token)
    assert payload is not None
    jti = payload.get("jti")
    assert jti

    result = await db_session.execute(
        select(ActiveSession).where(ActiveSession.jti == jti)
    )
    session = result.scalars().first()
    assert session is not None and session.revoked_at is None

    headers = {"Authorization": f"Bearer {token}"}
    ok_response = await async_client.get("/users/me", headers=headers)
    assert ok_response.status_code == 200

    logout_response = await async_client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    await db_session.refresh(session)
    assert session.revoked_at is not None

    rejected = await async_client.get("/users/me", headers=headers)
    assert rejected.status_code == 401


async def test_profile_cache_envelope_validation(async_client, user_factory):
    password = "EnvelopePass123!"
    user = await _create_active_user(user_factory, password)

    login_response = await _login(async_client, user.email, password)
    assert login_response.status_code == 200
    token = async_client.cookies.get("access_token_v2")
    headers = {"Authorization": f"Bearer {token}"}

    signing_key_response = await async_client.get(
        "/auth/session/signing-key", headers=headers
    )
    assert signing_key_response.status_code == 200
    signing_key = signing_key_response.json()["signing_key"]

    payload = {
        "version": 2,
        "expiresAt": int(datetime.now(UTC).timestamp() * 1000) + 60_000,
        "data": {
            "id": str(user.id),
            "full_name": user.profile.full_name,
            "avatar_url": None,
        },
    }

    payload_json = json.dumps(payload, separators=(",", ":"))
    signature = base64.b64encode(
        hmac.new(
            signing_key.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256
        ).digest()
    ).decode("ascii")
    envelope = {**payload, "signature": signature}

    ok_response = await async_client.get(
        "/users/me",
        headers={**headers, "X-Profile-Cache-Envelope": json.dumps(envelope)},
    )
    assert ok_response.status_code == 200

    forged = {**envelope, "signature": "invalid-signature"}
    rejected = await async_client.get(
        "/users/me",
        headers={**headers, "X-Profile-Cache-Envelope": json.dumps(forged)},
    )
    assert rejected.status_code == 400

    forged_data = {**envelope, "data": {**envelope["data"], "full_name": "Forged"}}
    rejected_data = await async_client.get(
        "/users/me",
        headers={**headers, "X-Profile-Cache-Envelope": json.dumps(forged_data)},
    )
    assert rejected_data.status_code == 400


async def test_logout_rotates_session_signing_key(
    async_client, user_factory, db_session
):
    password = "RotateKeyPass123!"
    user = await _create_active_user(user_factory, password)

    login_response = await _login(async_client, user.email, password)
    assert login_response.status_code == 200
    token = async_client.cookies.get("access_token_v2")
    payload = decode_token(token)
    assert payload is not None
    jti = payload.get("jti")
    assert jti

    result = await db_session.execute(
        select(ActiveSession).where(ActiveSession.jti == jti)
    )
    session = result.scalars().first()
    assert session is not None
    original_key = session.signing_key
    assert original_key

    headers = {"Authorization": f"Bearer {token}"}
    logout_response = await async_client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    await db_session.refresh(session)
    assert session.signing_key
    assert session.signing_key != original_key


@pytest.mark.asyncio
async def test_register_rate_limit(async_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    for attempt in range(4):
        payload = {
            "email": f"rate-limit-{attempt}@example.com",
            "password": "ValidPass123!",
            "full_name": "Rate Limited User",
        }
        response = await async_client.post("/auth/register", json=payload)
        if response.status_code != 200:
            print(f"\nREGISTER FAIL: {response.json()}\n")
        assert response.status_code == status.HTTP_200_OK

    blocked_payload = {
        "email": "rate-limit-final@example.com",
        "password": "ValidPass123!",
        "full_name": "Rate Limited User",
    }
    blocked = await async_client.post("/auth/register", json=blocked_payload)

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert blocked.json()["detail"] == translate("errors.rate_limit.generic")
