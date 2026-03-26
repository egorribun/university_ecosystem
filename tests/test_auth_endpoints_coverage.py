import pytest
from httpx import AsyncClient

import app.models as models
from app.auth.security import get_password_hash

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_register_endpoint(async_client: AsyncClient, db_session):
    # Success
    payload = {
        "email": "newuser@example.com",
        "password": "StrongPassword123!",
        "full_name": "New User",
    }
    response = await async_client.post("/auth/register", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify in DB
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stmt = (
        select(models.User)
        .where(models.User.email == "newuser@example.com")
        .options(selectinload(models.User.profile))
    )
    user = (await db_session.execute(stmt)).scalar_one()
    assert user.profile.full_name == "New User"

    # Duplicate email
    response = await async_client.post("/auth/register", json=payload)
    assert response.status_code == 400


async def test_login_json_endpoint(async_client: AsyncClient, user_factory):
    password = "StrongPass1!"
    user = await user_factory(hashed_password=await get_password_hash(password))

    payload = {"email": user.email, "password": password, "trust_device": False}
    response = await async_client.post("/auth/login/json", json=payload)
    assert response.status_code == 200
    assert "access_token_v2" in response.cookies
    data = response.json()
    assert "access_token_v2" not in data
    assert data["user"]["email"] == user.email

    # Wrong password
    payload["password"] = "wrong"
    response = await async_client.post("/auth/login/json", json=payload)
    assert response.status_code == 401


async def test_login_form_endpoint(async_client: AsyncClient, user_factory):
    password = "StrongPass1!"
    user = await user_factory(hashed_password=await get_password_hash(password))

    data = {"username": user.email, "password": password}
    response = await async_client.post("/auth/login", data=data)
    assert response.status_code == 200
    assert "access_token_v2" in response.cookies
    assert "access_token_v2" not in response.json()
