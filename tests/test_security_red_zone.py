import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash


@pytest.mark.asyncio
async def test_login_response_does_not_contain_access_token_body(
    async_client: AsyncClient, user_factory
):
    """
    Red Zone Fix Verification:
    Ensure the access_token is strictly sent via HttpOnly cookie and NEVER
    leaked in the JSON response body.
    """
    password = "SecureLogin123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200

    payload = response.json()

    # 1. Assert 'access_token' is NOT in the body
    assert "access_token" not in payload, (
        "CRITICAL: access_token leaked in response body!"
    )

    # 2. Assert 'access_token_v2' cookie IS present
    assert "access_token_v2" in response.cookies, "access_token_v2 cookie missing"

    # 3. Assert user profile is present (structure check)
    assert "user" in payload
    assert payload["user"]["id"] == str(user.id)
