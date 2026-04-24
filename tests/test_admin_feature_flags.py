"""Admin feature flag API tests.

NOTE: FeatureFlag/FlagStatus classes were removed during the OpenFeature migration.
Tests have been rewritten against the new app.core.feature_flags API.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.core.feature_flags import FLAG_PUSH_BATCHING, feature_flags

# Common strong password for tests
TEST_PASSWORD = "StrongPass123!"  # NOSONAR


@pytest.fixture(autouse=True)
def mock_feature_flags_redis():
    """Mock Redis connection for feature flags to avoid persistence errors in tests."""
    with patch.object(feature_flags, "_redis", new_callable=AsyncMock) as mock:
        yield mock


@pytest.mark.asyncio
async def test_list_feature_flags_admin(root_client: AsyncClient, user_factory):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    # Auth is under /api/v1
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    # Admin is NOT under /api/v1 (it's /admin)
    response = await root_client.get("/admin/feature-flags")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Verify we see real flags from the new system
    assert any(f["name"] == FLAG_PUSH_BATCHING for f in data)


@pytest.mark.asyncio
async def test_list_feature_flags_forbidden(root_client: AsyncClient, user_factory):
    user = await user_factory(
        role="student", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": TEST_PASSWORD}
    )

    response = await root_client.get("/admin/feature-flags")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_feature_flag_success(root_client: AsyncClient, user_factory):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    flag_name = FLAG_PUSH_BATCHING

    # In the new system, we don't 'register' during test, we update the existing one
    # The API uses schemas.FeatureFlagUpdateIn
    response = await root_client.patch(
        f"/admin/feature-flags/{flag_name}",
        json={"enabled": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == flag_name
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_update_feature_flag_not_found(root_client: AsyncClient, user_factory):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    response = await root_client.patch(
        "/admin/feature-flags/non_existent_flag", json={"enabled": True}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_feature_flag_empty_input(root_client: AsyncClient, user_factory):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    flag_name = FLAG_PUSH_BATCHING
    response = await root_client.patch(f"/admin/feature-flags/{flag_name}", json={})
    assert response.status_code == 400
