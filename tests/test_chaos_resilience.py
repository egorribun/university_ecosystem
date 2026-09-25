from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.api.deps import get_current_admin_user
from app.auth import rbac
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.cache import MultiLayerCache


@pytest.fixture(autouse=True)
async def reset_spicedb_state() -> AsyncIterator[None]:
    """Keep the process-global SpiceDB breaker isolated between chaos tests.

    These tests intentionally exercise consecutive failures.  Resetting the
    breaker and permission cache around each case prevents an OPEN state from
    short-circuiting a later test before its transport mock is reached.
    """
    await rbac._spicedb_breaker.reset()
    rbac._permission_cache.clear()
    try:
        yield
    finally:
        await rbac._spicedb_breaker.reset()
        rbac._permission_cache.clear()


@pytest.mark.asyncio
class TestRedisChaos:
    """Tests for Redis (L2 Cache) failure resilience."""

    async def test_redis_get_failure_returns_none(self):
        """When Redis get fails, MultiLayerCache should return None (fail-soft)."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("Redis connection lost")

        cache = MultiLayerCache(redis_client=mock_redis)
        result = await cache.get("test-key")

        assert result is None
        mock_redis.get.assert_called_once_with("test-key")

    async def test_redis_set_failure_does_not_raise(self):
        """When Redis set fails, MultiLayerCache should not raise (fail-soft)."""
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = ConnectionError("Redis write failure")

        cache = MultiLayerCache(redis_client=mock_redis)
        # Should not raise
        await cache.set("test-key", "test-value")

        mock_redis.setex.assert_called_once()

    async def test_redis_invalidate_failure_does_not_raise(self):
        """When Redis scan/delete fails, MultiLayerCache should not raise."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = ConnectionError("Redis scan failed")

        cache = MultiLayerCache(redis_client=mock_redis)
        # Should not raise
        await cache.invalidate_prefix("test-prefix")

        mock_redis.scan.assert_called_once()


@pytest.mark.asyncio
class TestSpiceDBChaos:
    """Tests for SpiceDB (Authz) failure resilience."""

    async def test_spicedb_check_failure_raises_unavailable_error(self):
        """When SpiceDB CheckPermission fails, PermissionChecker should raise SpiceDBUnavailableError."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_stub = MagicMock()
        mock_stub.CheckPermission = AsyncMock(
            side_effect=Exception("gRPC connection failed")
        )

        # Define mock classes for the imports in rbac.py
        MockRequest = MagicMock()
        MockResponse = MagicMock()
        MockResponse.PERMISSIONSHIP_HAS_PERMISSION = 1
        MockObjectRef = MagicMock()
        MockSubjectRef = MagicMock()

        # Create a mock module for authzed.api.v1
        authzed_v1 = MagicMock()
        authzed_v1.CheckPermissionRequest = MockRequest
        authzed_v1.CheckPermissionResponse = MockResponse
        authzed_v1.ObjectReference = MockObjectRef
        authzed_v1.SubjectReference = MockSubjectRef
        authzed_v1.PermissionsServiceStub = MagicMock(return_value=mock_stub)

        # Create a mock module for the gRPC service
        authzed_grpc = MagicMock()
        authzed_grpc.PermissionsServiceStub = MagicMock(return_value=mock_stub)

        # Patch sys.modules to simulate installed library
        with patch.dict(
            "sys.modules",
            {
                "authzed": MagicMock(),
                "authzed.api": MagicMock(),
                "authzed.api.v1": authzed_v1,
                "authzed.api.v1.permission_service_grpc": authzed_grpc,
                "grpclib": MagicMock(),
                "grpclib.client": MagicMock(),
            },
        ):
            checker = PermissionChecker(channel=MagicMock())

            with pytest.raises(SpiceDBUnavailableError) as exc_info:
                await checker.check_permission(
                    "semester", "current", "admin", "user-123"
                )

            assert "SpiceDB unreachable" in str(exc_info.value)

        mock_stub.CheckPermission.assert_called_once()

    async def test_admin_dependency_returns_503_on_spicedb_failure(self):
        """When SpiceDB is unreachable, get_current_admin_user should return 503 (fail-closed)."""
        mock_checker = AsyncMock()
        mock_checker.check_admin.side_effect = SpiceDBUnavailableError("Outage")

        mock_request = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 123

        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(mock_request, mock_user, mock_checker)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc_info.value.detail["error"] == "authz_unavailable"
