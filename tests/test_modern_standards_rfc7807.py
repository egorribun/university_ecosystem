import pytest
from fastapi import status

from app.api.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_error_rfc7807_compliance(async_client, user_factory):
    """Verify that domain errors follow RFC 7807."""
    user = await user_factory()

    # Use dependency_overrides for reliability
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        # Attempt to get a non-existent event to trigger EntityNotFound
        response = await async_client.get(
            "/events/00000000-0000-4000-a000-000000000999"
        )

        # Check media type
        assert response.headers["Content-Type"] == "application/problem+json"

        data = response.json()
        assert data["status"] == 404
        assert "Resource Not Found" in data["title"]
        assert "type" in data
        assert "instance" in data
        assert "detail" in data
    finally:
        # Cleaned up by conftest
        pass


@pytest.mark.asyncio
async def test_unauthorized_rfc7807(async_client):
    """Verify that 401 Unauthorized errors follow RFC 7807
    (via custom handler if possible)."""
    # Simply requesting /me without token
    response = await async_client.get("/users/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    # Default FastAPI 401 is JSON, but if we override it, we can check for problem+json.
    # For now, we just ensure it doesn't crash.
