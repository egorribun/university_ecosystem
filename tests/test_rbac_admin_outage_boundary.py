"""The real admin checker must reject cached allows during a SpiceDB outage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import grpc
import pytest
from authzed.api import v1
from fastapi import HTTPException, Request

from app.api.deps.auth import ensure_admin
from app.auth import rbac
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


@pytest.fixture
async def live_checker(monkeypatch):
    # Keep the real checker, cache and circuit breaker. Only the gRPC boundary is fake.
    monkeypatch.setattr(rbac, "_permission_cache", rbac._make_fresh_cache())
    monkeypatch.setattr(
        rbac,
        "_spicedb_breaker",
        CircuitBreaker(
            "admin-outage-test",
            config=CircuitBreakerConfig(
                failure_threshold=1, recovery_timeout_seconds=60.0, success_threshold=1
            ),
        ),
    )
    stub = SimpleNamespace(CheckPermission=AsyncMock())
    monkeypatch.setattr(v1, "PermissionsServiceStub", lambda channel: stub)
    return rbac.PermissionChecker(MagicMock()), stub


def response(allowed):
    return v1.CheckPermissionResponse(
        permissionship=v1.CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
        if allowed
        else v1.CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
    )


def request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin",
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("SpiceDB unavailable"),
        TimeoutError("SpiceDB timed out"),
        grpc.aio.AioRpcError(grpc.StatusCode.UNAVAILABLE, details="offline"),
    ],
)
async def test_ensure_admin_rejects_warmed_allow_on_outage_and_open_breaker(
    live_checker, failure
):
    checker, stub = live_checker
    user = SimpleNamespace(id=uuid4(), role="admin")
    stub.CheckPermission.return_value = response(True)
    await ensure_admin(checker, user, request())
    assert next(iter(rbac._permission_cache.values()))[0] is True
    stub.CheckPermission.side_effect = failure
    for _ in range(2):
        with pytest.raises(HTTPException) as exc:
            await ensure_admin(checker, user, request())
        assert exc.value.status_code == 503
        assert exc.value.detail["error"] == "authz_unavailable"
    # The second outage check is rejected by the actual open circuit.
    assert stub.CheckPermission.await_count == 2


@pytest.mark.parametrize("resource", ["semester", "tenant", "campus"])
async def test_direct_admin_checks_cannot_bypass_strict_outage_policy(
    live_checker, resource
):
    checker, stub = live_checker
    stub.CheckPermission.return_value = response(True)
    assert await checker.check_permission(resource, "current", "admin", "user") is True
    stub.CheckPermission.side_effect = ConnectionError("offline")
    with pytest.raises(rbac.SpiceDBUnavailableError):
        await checker.check_permission(resource, "current", "admin", "user")


async def test_cached_admin_denial_remains_fail_closed(live_checker):
    checker, stub = live_checker
    user = SimpleNamespace(id=uuid4(), role="admin")
    stub.CheckPermission.return_value = response(False)
    with pytest.raises(HTTPException) as exc:
        await ensure_admin(checker, user, request())
    assert exc.value.status_code == 403
    stub.CheckPermission.side_effect = ConnectionError("offline")
    with pytest.raises(HTTPException) as exc:
        await ensure_admin(checker, user, request())
    assert exc.value.status_code == 403


async def test_ordinary_read_keeps_existing_positive_grace(live_checker):
    checker, stub = live_checker
    stub.CheckPermission.return_value = response(True)
    assert await checker.check_permission("document", "one", "read", "user") is True
    stub.CheckPermission.side_effect = ConnectionError("offline")
    assert await checker.check_permission("document", "one", "read", "user") is True


async def test_live_admin_revocation_overwrites_cached_allow(live_checker):
    checker, stub = live_checker
    user = SimpleNamespace(id=uuid4(), role="admin")
    stub.CheckPermission.return_value = response(True)
    await ensure_admin(checker, user, request())
    stub.CheckPermission.return_value = response(False)
    with pytest.raises(HTTPException) as exc:
        await ensure_admin(checker, user, request())
    assert exc.value.status_code == 403
    assert next(iter(rbac._permission_cache.values()))[0] is False
