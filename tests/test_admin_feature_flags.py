"""Admin feature-flag API contract tests."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.core.feature_flags import FLAG_PUSH_BATCHING

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
        "name": FLAG_PUSH_BATCHING,
        "enabled": True,
        "default": True,
        "description": "Batch push notifications before delivery.",
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
    push_batching = next(f for f in data if f["name"] == FLAG_PUSH_BATCHING)
    assert push_batching == {
        "name": FLAG_PUSH_BATCHING,
        "enabled": True,
        "default": True,
        "description": "Batch push notifications before delivery.",
        "provider": "flagd Provider",
        "evaluation_reason": "STATIC",
        "management": "gitops",
        "config_path": "k8s/flagd/flags.json",
    }
    assert isinstance(push_batching["enabled"], bool)
    assert push_batching["provider"]
    assert push_batching["evaluation_reason"]


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
        f"/admin/feature-flags/{FLAG_PUSH_BATCHING}",
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

    response = await root_client.patch(
        f"/admin/feature-flags/{FLAG_PUSH_BATCHING}", json={}
    )
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
