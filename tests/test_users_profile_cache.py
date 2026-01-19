import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.localization import translate
from app.models.models import ActiveSession

PROFILE_CACHE_HEADER = "X-Profile-Cache-Envelope"


async def _login(async_client: AsyncClient, email: str, password: str) -> str:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_profile_cache_missing_signing_key_localized(
    async_client: AsyncClient, user_factory, db_session, locale: str
):
    password = "ProfileLocale123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    token = await _login(async_client, user.email, password)
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

    response = await async_client.get(
        f"/users/me?lang={locale}",
        headers={
            "Authorization": f"Bearer {token}",
            PROFILE_CACHE_HEADER: json.dumps(
                {"version": 1, "expiresAt": 0, "data": {}, "signature": "stub"}
            ),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == translate(
        "errors.sessions.signing_key_missing", locale=locale
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_profile_cache_invalid_envelope_localized(
    async_client: AsyncClient, user_factory, locale: str
):
    password = "ProfileInvalidEnvelope123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    token = await _login(async_client, user.email, password)
    response = await async_client.get(
        f"/users/me?lang={locale}",
        headers={
            "Authorization": f"Bearer {token}",
            PROFILE_CACHE_HEADER: "not-json",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == translate(
        "errors.profile_cache.invalid_envelope", locale=locale
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_profile_cache_invalid_signature_localized(
    async_client: AsyncClient, user_factory, locale: str
):
    password = "ProfileInvalidSignature123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    token = await _login(async_client, user.email, password)
    envelope = json.dumps(
        {
            "version": 1,
            "expiresAt": 0,
            "data": {},
            "signature": "",
        }
    )
    response = await async_client.get(
        f"/users/me?lang={locale}",
        headers={
            "Authorization": f"Bearer {token}",
            PROFILE_CACHE_HEADER: envelope,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == translate(
        "errors.profile_cache.invalid_signature", locale=locale
    )
