import pytest
from fastapi import status
from sqlalchemy import select

from app.auth.security import decode_token, get_password_hash
from app.models.models import ActiveSession
from app.localization import translate

pytestmark = pytest.mark.anyio("asyncio")


async def _create_active_user(user_factory, password: str):
    hashed = get_password_hash(password)
    return await user_factory(hashed_password=hashed, is_active=True)


async def _login(async_client, email: str, password: str):
    return await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


async def test_login_issues_secure_cookie(async_client, user_factory):
    password = "StrongPass123!"
    user = await _create_active_user(user_factory, password)

    response = await _login(async_client, user.email, password)

    assert response.status_code == 200

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.lower().startswith("access_token=")
        and "httponly" in header.lower()
        and "secure" in header.lower()
        and "samesite=strict" in header.lower()
        for header in set_cookie_headers
    )

    stored_cookie = async_client.cookies.get("access_token")
    assert stored_cookie is not None and stored_cookie != ""

    profile_response = await async_client.get(
        "/users/me",
        headers={"Cookie": f"access_token={stored_cookie}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == user.email


async def test_logout_clears_cookie(async_client, user_factory):
    password = "AnotherPass456!"
    user = await _create_active_user(user_factory, password)

    login_response = await _login(async_client, user.email, password)
    assert login_response.status_code == 200
    assert async_client.cookies.get("access_token")

    logout_response = await async_client.post("/auth/logout")
    assert logout_response.status_code == 200

    logout_cookies = logout_response.headers.get_list("set-cookie")
    assert any(
        header.lower().startswith("access_token=") and "max-age=0" in header.lower()
        for header in logout_cookies
    )

    assert async_client.cookies.get("access_token") is None

    profile_response = await async_client.get("/users/me")
    assert profile_response.status_code == 401


async def test_token_reuse_after_logout_rejected(
    async_client, user_factory, db_session
):
    password = "ReusePass789!"
    user = await _create_active_user(user_factory, password)

    login_response = await _login(async_client, user.email, password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

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


@pytest.mark.anyio
async def test_register_rate_limit(async_client):
    for attempt in range(4):
        payload = {
            "email": f"rate-limit-{attempt}@example.com",
            "password": "ValidPass123!",
            "full_name": "Rate Limited User",
        }
        response = await async_client.post("/auth/register", json=payload)
        assert response.status_code == status.HTTP_200_OK

    blocked_payload = {
        "email": "rate-limit-final@example.com",
        "password": "ValidPass123!",
        "full_name": "Rate Limited User",
    }
    blocked = await async_client.post("/auth/register", json=blocked_payload)

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert blocked.json()["detail"] == translate("errors.rate_limit.generic")
