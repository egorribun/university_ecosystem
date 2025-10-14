import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.models import models


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_update_profile_email_normalizes(async_client, user_factory, db_session):
    password = "ChangeEmail123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        email="original@example.com",
        hashed_password=hashed,
        is_active=True,
    )

    headers = await _login(async_client, user.email, password)

    response = await async_client.put(
        "/users/me",
        json={"email": "New.Email@Example.com  "},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "new.email@example.com"

    await db_session.refresh(user)
    assert user.email == "new.email@example.com"


@pytest.mark.anyio
async def test_update_profile_email_duplicate(async_client, user_factory, db_session):
    password = "DuplicateEmail123!"
    hashed = get_password_hash(password)
    user = await user_factory(
        email="first-user@example.com",
        hashed_password=hashed,
        is_active=True,
    )
    await user_factory(email="existing@example.com", is_active=True)

    headers = await _login(async_client, user.email, password)

    headers_ru = {**headers, "Accept-Language": "ru"}

    response = await async_client.put(
        "/users/me",
        json={"email": "Existing@Example.com"},
        headers=headers_ru,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Указанный email уже используется"}

    await db_session.refresh(user)
    assert user.email == "first-user@example.com"
