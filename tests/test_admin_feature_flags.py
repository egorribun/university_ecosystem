"""Admin feature-flag API contract tests."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.auth.rbac import SpiceDBUnavailableError
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
    assert set(paths["/api/v1/admin/feature-flags"]) == {"get"}
    assert "/api/v1/admin/feature-flags/{name}" not in paths
    assert set(paths["/admin/feature-flags"]) == {"get"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("admin", 200), ("teacher", 403), ("student", 403)],
)
async def test_versioned_feature_flag_route_matches_browser_contract(
    root_client: AsyncClient, user_factory, role: str, expected_status: int
):
    user = await user_factory(
        role=role, hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    login = await root_client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200

    response = await root_client.get("/api/v1/admin/feature-flags")

    assert response.status_code == expected_status
    if role == "admin":
        assert response.json() == []


@pytest.mark.asyncio
async def test_versioned_feature_flags_require_authentication(root_client: AsyncClient):
    response = await root_client.get("/api/v1/admin/feature-flags")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_versioned_feature_flags_keep_live_authorization_and_read_only_contract(
    root_client: AsyncClient, user_factory, mock_spicedb_permissions
):
    admin = await user_factory(
        role="admin", hashed_password=await get_password_hash(TEST_PASSWORD)
    )
    login = await root_client.post(
        "/api/v1/auth/login", data={"username": admin.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    response = await root_client.patch(
        f"/api/v1/admin/feature-flags/{TEST_FLAG}", json={"enabled": True}
    )
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"

    mock_spicedb_permissions.check_admin.side_effect = SpiceDBUnavailableError(
        "offline"
    )
    response = await root_client.get("/api/v1/admin/feature-flags")
    assert response.status_code == 503
    assert response.json()["code"] == "authz_unavailable"


def test_openapi_preserves_existing_admin_clients(app):
    paths = app.openapi()["paths"]
    expected_operations = {
        "/admin/audit": "list_audit_logs_admin_audit_get",
        "/admin/audit/time-travel": "get_time_travel_state_admin_audit_time_travel_get",
        "/admin/feature-flags": "list_feature_flags_admin_feature_flags_get",
    }
    for path, operation_id in expected_operations.items():
        assert path in paths
        assert paths[path]["get"]["operationId"] == operation_id
