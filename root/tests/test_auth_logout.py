import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash


@pytest.mark.anyio
async def test_logout_invalidates_token(
    async_client: AsyncClient, user_factory
) -> None:
    password = "StrongP@ssw0rd!"
    hashed_password = get_password_hash(password)
    user = await user_factory(hashed_password=hashed_password, is_active=True)

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = await async_client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 200
    assert logout_response.json() == {"status": "ok"}

    me_response = await async_client.get("/users/me", headers=headers)
    assert me_response.status_code == 401

    relogin_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert relogin_response.status_code == 200
    new_token = relogin_response.json()["access_token"]
    assert new_token != token

    refreshed_headers = {"Authorization": f"Bearer {new_token}"}
    me_after_relogin = await async_client.get("/users/me", headers=refreshed_headers)
    assert me_after_relogin.status_code == 200
    assert me_after_relogin.json()["id"] == user.id
