import pytest
from sqlalchemy import select

from app.models import ActiveSession

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_logout_success_cookie(async_client, user_factory):
    # Setup: Create user and login to get cookie
    password = "LogoutPass123!"
    from app.auth.security import get_password_hash

    user = await user_factory(hashed_password=await get_password_hash(password))

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    assert "access_token_v2" in async_client.cookies

    # Execute: Logout
    response = await async_client.post("/auth/logout")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully"}
    assert "access_token_v2" not in async_client.cookies
    assert "Clear-Site-Data" in response.headers


async def test_logout_success_bearer(async_client, user_factory, db_session):
    # Setup: Create user and login to get token
    password = "LogoutBearer123!"
    from app.auth.security import get_password_hash

    user = await user_factory(hashed_password=await get_password_hash(password))

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    token = login_response.cookies.get("access_token_v2")

    from app.auth.security import decode_token

    payload = decode_token(token)
    jti = payload["jti"]

    # Verify session is active in DB
    result = await db_session.execute(
        select(ActiveSession).where(ActiveSession.jti == jti)
    )
    session = result.scalars().first()
    assert session is not None
    assert session.revoked_at is None

    # Execute: Logout using Bearer token
    if "access_token_v2" in async_client.cookies:
        async_client.cookies.delete("access_token_v2")
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.post("/auth/logout", headers=headers)

    # Assert
    assert response.status_code == 200
    await db_session.refresh(session)
    assert session.revoked_at is not None
    assert session.signing_key is not None

    # Execute: Logout without being logged in
    async_client.cookies.delete("access_token_v2")
    response = await async_client.post("/auth/logout")

    # Assert: Should still return 200 for idempotency/privacy
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully"}


async def test_logout_invalid_token(async_client):
    # Execute: Logout with invalid token
    headers = {"Authorization": "Bearer invalid-token-here"}
    response = await async_client.post("/auth/logout", headers=headers)

    # Assert: Should still return 200
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully"}
