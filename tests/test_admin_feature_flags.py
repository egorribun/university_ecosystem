"""Admin feature-flag API contract tests."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash

# The production registry is empty; the API adapter is exercised with a
# snapshot for a test-only flag name.
TEST_FLAG = "test-flag"

# Common strong password for tests
TEST_PASSWORD = "StrongPass123!"  # NOSONAR


@pytest.mark.asyncio
async def test_list_feature_flags_admin(root_client: AsyncClient, user_factory):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    snapshot = {
        "name": TEST_FLAG,
        "enabled": True,
        "default": True,
        "description": "Test-only flag.",
        "provider": "flagd Provider",
        "evaluation_reason": "STATIC",
        "management": "gitops",
        "config_path": "k8s/flagd/flags.json",
    }
    with patch(
        "app.api.admin.feature_flags.list_feature_flag_snapshots",
        return_value=[snapshot],
    ):
        response = await root_client.get("/admin/feature-flags")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    test_flag = next(f for f in data if f["name"] == TEST_FLAG)
    assert test_flag == {
        "name": TEST_FLAG,
        "enabled": True,
        "default": True,
        "description": "Test-only flag.",
        "provider": "flagd Provider",
        "evaluation_reason": "STATIC",
        "management": "gitops",
        "config_path": "k8s/flagd/flags.json",
    }
    assert isinstance(test_flag["enabled"], bool)
    assert test_flag["provider"]
    assert test_flag["evaluation_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["student", "teacher"])
async def test_list_feature_flags_forbidden(
    root_client: AsyncClient, user_factory, role: str
):
    user = await user_factory(
        role=role, hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": TEST_PASSWORD}
    )

    response = await root_client.get("/admin/feature-flags")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["student", "teacher"])
async def test_update_feature_flag_denied_for_non_admin(
    root_client: AsyncClient, user_factory, role: str
):
    user = await user_factory(
        role=role, hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": TEST_PASSWORD}
    )

    response = await root_client.patch(
        f"/admin/feature-flags/{TEST_FLAG}", json={"enabled": True}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_feature_flag_is_explicitly_read_only(
    root_client: AsyncClient, user_factory
):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    response = await root_client.patch(
        f"/admin/feature-flags/{TEST_FLAG}",
        json={"enabled": True},
    )
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.json()["detail"] == (
        "Feature flags are read-only in this API. Update "
        "k8s/flagd/flags.json through the reviewed GitOps workflow."
    )


@pytest.mark.asyncio
async def test_update_unknown_feature_flag_is_still_read_only(
    root_client: AsyncClient, user_factory
):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    response = await root_client.patch(
        "/admin/feature-flags/non_existent_flag", json={"enabled": True}
    )
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_update_feature_flag_empty_input_is_not_treated_as_a_write(
    root_client: AsyncClient, user_factory
):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    response = await root_client.patch(f"/admin/feature-flags/{TEST_FLAG}", json={})
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_openapi_exposes_feature_flags_as_read_only(
    root_client: AsyncClient, user_factory
):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )

    response = await root_client.get("/api/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths["/admin/feature-flags"]) == {"get"}
    assert "/admin/feature-flags/{name}" not in paths
