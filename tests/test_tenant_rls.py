"""Unit and integration tests for Multi-Tenant RLS, TenantContextMiddleware, and SpiceDB ReBAC."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authzed.api.v1 import CheckPermissionResponse
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.rbac import PermissionChecker
from app.core.db.listeners import set_pg_tenant_context
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.tenant import (
    get_bypass_rls,
    get_current_tenant,
    set_bypass_rls,
    set_current_tenant,
)
from app.models.tenant import Tenant


def test_tenant_context_vars() -> None:
    """Test tenant_id_ctx and bypass_rls_ctx setting and getting."""
    token = set_current_tenant("tenant-123")
    assert get_current_tenant() == "tenant-123"

    b_token = set_bypass_rls(True)
    assert get_bypass_rls() is True

    set_bypass_rls(False)
    assert get_bypass_rls() is False

    set_current_tenant(None)


def test_tenant_context_middleware() -> None:
    """Test FastAPI TenantContextMiddleware header extraction, UUID validation, and response header echo."""
    app = FastAPI()
    app.add_middleware(TenantContextMiddleware)

    @app.get("/test-tenant")
    async def sample_endpoint(request: Request) -> dict[str, str]:
        return {
            "tenant_id": get_current_tenant(),
            "state_tenant_id": request.state.tenant_id,
        }

    client = TestClient(app)
    valid_uuid = str(uuid.uuid4())
    response = client.get("/test-tenant", headers={"X-Tenant-ID": valid_uuid})

    assert response.status_code == 200
    assert response.json()["tenant_id"] == valid_uuid
    assert response.json()["state_tenant_id"] == valid_uuid
    assert response.headers.get("x-tenant-id") == valid_uuid

    response_invalid = client.get(
        "/test-tenant", headers={"X-Tenant-ID": "non-uuid-tenant-slug"}
    )
    assert response_invalid.status_code == 200
    assert response_invalid.json()["tenant_id"] == ""
    assert response_invalid.json()["state_tenant_id"] == ""
    assert response_invalid.headers.get("x-tenant-id") is None


def test_pg_tenant_context_listener_sqlite() -> None:
    """Test set_pg_tenant_context listener skips non-PostgreSQL dialects safely."""
    mock_conn = MagicMock()
    mock_conn.dialect.name = "sqlite"

    # Should exit immediately without executing SQL for SQLite
    set_pg_tenant_context(None, None, mock_conn)
    mock_conn.execute.assert_not_called()


def test_pg_tenant_context_listener_postgresql() -> None:
    """Test set_pg_tenant_context listener executes valid PostgreSQL SQL statements."""
    mock_conn = MagicMock()
    mock_conn.dialect.name = "postgresql"

    # 1. Test default empty tenant context
    set_current_tenant(None)
    set_bypass_rls(False)
    set_pg_tenant_context(None, None, mock_conn)

    assert mock_conn.execute.call_count == 2
    executed_sqls = [str(call.args[0]) for call in mock_conn.execute.call_args_list]
    assert "SELECT set_config('app.current_tenant', '', true);" in executed_sqls
    assert "SELECT set_config('app.bypass_rls', '', true);" in executed_sqls
    for sql in executed_sqls:
        assert "RESET LOCAL" not in sql

    # 2. Test active tenant ID context
    mock_conn.reset_mock()
    token = set_current_tenant("tenant-guu-789")
    try:
        set_pg_tenant_context(None, None, mock_conn)
        assert mock_conn.execute.call_count == 1
        call_args = mock_conn.execute.call_args
        assert "SELECT set_config('app.current_tenant', :tenant_id, true);" in str(
            call_args[0][0]
        )
        assert call_args[0][1] == {"tenant_id": "tenant-guu-789"}
    finally:
        set_current_tenant(None)

    # 3. Test bypass RLS context
    mock_conn.reset_mock()
    b_token = set_bypass_rls(True)
    try:
        set_pg_tenant_context(None, None, mock_conn)
        assert mock_conn.execute.call_count == 1
        call_args = mock_conn.execute.call_args
        assert "SELECT set_config('app.bypass_rls', :bypass_rls, true);" in str(
            call_args[0][0]
        )
        assert call_args[0][1] == {"bypass_rls": "on"}
    finally:
        set_bypass_rls(False)


def test_tenant_model_creation() -> None:
    """Test Tenant model initialization."""
    tenant = Tenant(
        name="State University of Management",
        slug="guu",
        domain="guu.ru",
        is_active=True,
    )
    assert tenant.name == "State University of Management"
    assert tenant.slug == "guu"
    assert tenant.domain == "guu.ru"
    assert tenant.is_active is True


@pytest.mark.asyncio
async def test_spicedb_permission_checker_tenant_campus() -> None:
    """Test SpiceDB PermissionChecker check_tenant_permission and check_campus_permission with genuine mocks."""
    mock_channel = MagicMock()
    checker = PermissionChecker(mock_channel)

    user_id = str(uuid.uuid4())
    tenant_id = str(uuid.uuid4())
    campus_id = str(uuid.uuid4())

    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value
        # Case A: Permission Granted
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
        )

        has_tenant_perm = await checker.check_tenant_permission(
            tenant_id, "view", user_id
        )
        assert has_tenant_perm is True
        mock_stub.CheckPermission.assert_called_once()
        req = mock_stub.CheckPermission.call_args[0][0]
        assert req.resource.object_type == "tenant"
        assert req.resource.object_id == tenant_id
        assert req.permission == "view"
        assert req.subject.object.object_type == "user"
        assert req.subject.object.object_id == user_id

        mock_stub.CheckPermission.reset_mock()

        has_campus_perm = await checker.check_campus_permission(
            campus_id, "view", user_id, tenant_id=tenant_id
        )
        assert has_campus_perm is True
        mock_stub.CheckPermission.assert_called_once()
        req_campus = mock_stub.CheckPermission.call_args[0][0]
        assert req_campus.resource.object_type == "campus"
        assert req_campus.resource.object_id == campus_id
        assert req_campus.permission == "view"

        # Case B: Permission Denied
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
            )
        )

        has_tenant_perm_denied = await checker.check_tenant_permission(
            tenant_id, "edit", user_id
        )
        assert has_tenant_perm_denied is False

        has_campus_perm_denied = await checker.check_campus_permission(
            campus_id, "edit", user_id
        )
        assert has_campus_perm_denied is False
