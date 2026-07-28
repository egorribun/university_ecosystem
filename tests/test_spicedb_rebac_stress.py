"""Empirical stress test suite for SpiceDB ReBAC permission checks, circuit breaker, two-tier cache, and tenant/campus isolation."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authzed.api.v1 import CheckPermissionResponse

from app.auth.rbac import (
    PermissionChecker,
    SpiceDBUnavailableError,
    _permission_cache,
    _spicedb_breaker,
)
from app.core.circuit_breaker import CircuitBreakerState


@pytest.fixture(autouse=True)
def reset_spicedb_state():
    """Reset global permission cache and circuit breaker before each test."""
    _permission_cache.clear()
    _spicedb_breaker._internal_state.state = CircuitBreakerState.CLOSED
    _spicedb_breaker._internal_state.failure_count = 0
    _spicedb_breaker._internal_state.success_count = 0
    _spicedb_breaker._internal_state.last_state_change_time = time.monotonic()
    yield
    _permission_cache.clear()


@pytest.mark.asyncio
async def test_spicedb_cache_key_tenant_and_campus_isolation():
    """Verify distinct tenant_id or campus_id produce distinct cache keys (no cross-tenant pollution)."""
    mock_channel = MagicMock()
    checker = PermissionChecker(mock_channel)
    user_id = str(uuid.uuid4())
    campus_id = "campus-shared-id"
    tenant1 = "tenant-alpha"
    tenant2 = "tenant-beta"

    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value

        # Tenant 1 has permission
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
        )
        res1 = await checker.check_campus_permission(
            campus_id, "view", user_id, tenant_id=tenant1
        )
        assert res1 is True

        # Tenant 2 denied permission
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
            )
        )
        res2 = await checker.check_campus_permission(
            campus_id, "view", user_id, tenant_id=tenant2
        )
        assert res2 is False

        # Verify cache has two distinct entries
        assert len(_permission_cache) == 2
        key1 = (user_id, "campus", campus_id, "view", tenant1, campus_id)
        key2 = (user_id, "campus", campus_id, "view", tenant2, campus_id)
        assert _permission_cache[key1][0] is True
        assert _permission_cache[key2][0] is False


@pytest.mark.asyncio
async def test_spicedb_two_tier_grace_period_cache():
    """Test two-tier grace period cache TTL: 45s for ALLOW, 60s for DENY."""
    mock_channel = MagicMock()
    checker = PermissionChecker(mock_channel)
    user_id = str(uuid.uuid4())
    res_id = str(uuid.uuid4())

    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value

        # 1. Populate ALLOW result
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
        )
        assert (
            await checker.check_permission("document", res_id, "read", user_id) is True
        )

        # Now simulate SpiceDB outage
        mock_stub.CheckPermission = AsyncMock(
            side_effect=Exception("gRPC Connection Refused")
        )

        # Case A: Within 45s positive TTL -> served from grace cache
        with patch("time.monotonic") as mock_time:
            # Assume 10 seconds elapsed since cache population
            cached_entry = list(_permission_cache.values())[0]
            mock_time.return_value = cached_entry[1] + 10.0
            stale_res = await checker.check_permission(
                "document", res_id, "read", user_id
            )
            assert stale_res is True

        # Case B: Exceeds 45s positive TTL (e.g. 50s elapsed) -> raises SpiceDBUnavailableError (fail closed)
        with patch("time.monotonic") as mock_time:
            cached_entry = list(_permission_cache.values())[0]
            mock_time.return_value = cached_entry[1] + 50.0
            with pytest.raises(SpiceDBUnavailableError):
                await checker.check_permission("document", res_id, "read", user_id)

    # 2. Populate DENY result
    _permission_cache.clear()
    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
            )
        )
        assert (
            await checker.check_permission("document", res_id, "write", user_id)
            is False
        )

        mock_stub.CheckPermission = AsyncMock(side_effect=Exception("gRPC Timeout"))

        # Within 60s DENY TTL (e.g. 55s elapsed) -> served stale DENY
        with patch("time.monotonic") as mock_time:
            cached_entry = list(_permission_cache.values())[0]
            mock_time.return_value = cached_entry[1] + 55.0
            stale_deny = await checker.check_permission(
                "document", res_id, "write", user_id
            )
            assert stale_deny is False

        # Exceeds 60s DENY TTL (e.g. 65s elapsed) -> raises SpiceDBUnavailableError
        with patch("time.monotonic") as mock_time:
            cached_entry = list(_permission_cache.values())[0]
            mock_time.return_value = cached_entry[1] + 65.0
            with pytest.raises(SpiceDBUnavailableError):
                await checker.check_permission("document", res_id, "write", user_id)


@pytest.mark.asyncio
async def test_spicedb_circuit_breaker_tripping():
    """Test circuit breaker trips after 3 consecutive failures."""
    mock_channel = MagicMock()
    checker = PermissionChecker(mock_channel)

    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value
        mock_stub.CheckPermission = AsyncMock(side_effect=Exception("gRPC Error"))

        # First 3 calls fail and hit uncached exception -> raise SpiceDBUnavailableError
        for _ in range(3):
            with pytest.raises(SpiceDBUnavailableError):
                await checker.check_permission("resource", "id1", "view", "user1")

        # Circuit breaker should now be open
        assert _spicedb_breaker.state == CircuitBreakerState.OPEN


@pytest.mark.asyncio
async def test_spicedb_lru_cache_max_capacity():
    """Test LRU eviction when cache exceeds max capacity."""
    mock_channel = MagicMock()
    checker = PermissionChecker(mock_channel)

    with patch("authzed.api.v1.PermissionsServiceStub") as mock_stub_cls:
        mock_stub = mock_stub_cls.return_value
        mock_stub.CheckPermission = AsyncMock(
            return_value=CheckPermissionResponse(
                permissionship=CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
        )

        with patch("app.auth.rbac._PERMISSION_CACHE_MAX_SIZE", 5):
            for i in range(10):
                await checker.check_permission("res", f"id-{i}", "view", "user1")

            assert len(_permission_cache) == 5
            # First 5 items (0..4) should have been evicted
            first_key = ("user1", "res", "id-0", "view", "", "")
            last_key = ("user1", "res", "id-9", "view", "", "")
            assert first_key not in _permission_cache
            assert last_key in _permission_cache
