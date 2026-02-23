from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.api.deps import get_current_admin_user
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.cache import MultiLayerCache


@pytest.mark.asyncio
class TestRedisChaos:
    """Tests for Redis (L2 Cache) failure resilience."""

    async def test_redis_get_failure_returns_none(self):
        """When Redis get fails, MultiLayerCache should return None (fail-soft)."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection lost")

        cache = MultiLayerCache(redis_client=mock_redis)
        result = await cache.get("test-key")

        assert result is None
        mock_redis.get.assert_called_once_with("test-key")

    async def test_redis_set_failure_does_not_raise(self):
        """When Redis set fails, MultiLayerCache should not raise (fail-soft)."""
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = Exception("Redis write failure")

        cache = MultiLayerCache(redis_client=mock_redis)
        # Should not raise
        await cache.set("test-key", "test-value")

        mock_redis.setex.assert_called_once()

    async def test_redis_invalidate_failure_does_not_raise(self):
        """When Redis scan/delete fails, MultiLayerCache should not raise."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = Exception("Redis scan failed")

        cache = MultiLayerCache(redis_client=mock_redis)
        # Should not raise
        await cache.invalidate_prefix("test-prefix")

        mock_redis.scan.assert_called_once()


@pytest.mark.asyncio
class TestSpiceDBChaos:
    """Tests for SpiceDB (Authz) failure resilience."""

    async def test_spicedb_check_failure_raises_unavailable_error(self):
        """When SpiceDB CheckPermission fails, PermissionChecker should raise SpiceDBUnavailableError."""
        mock_client = MagicMock()
        mock_client.CheckPermission.side_effect = Exception("gRPC connection failed")

        checker = PermissionChecker(client=mock_client)

        with pytest.raises(SpiceDBUnavailableError):
            await checker.check_permission("semester", "current", "admin", "user-123")

        mock_client.CheckPermission.assert_called_once()

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
