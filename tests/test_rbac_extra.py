import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _clear_rbac_metrics():
    from prometheus_client import REGISTRY

    for collector in list(REGISTRY._collector_to_names.keys()):
        names = REGISTRY._collector_to_names[collector]
        if any("spicedb_permission" in n for n in names):
            try:
                REGISTRY.unregister(collector)
            except KeyError:
                pass


@pytest.mark.asyncio
async def test_rbac_fork_registration_unix():
    """Test register_at_fork registration using Unix-like env patching."""
    # Patch os.register_at_fork to exist and inspect call
    with patch("os.register_at_fork", create=True) as mock_register:
        # Force reload app.auth.rbac to execute module-level setup again
        _clear_rbac_metrics()
        if "app.auth.rbac" in sys.modules:
            del sys.modules["app.auth.rbac"]

        import app.auth.rbac as rbac_mod

        # Verify it was registered
        mock_register.assert_called_once()

        # Trigger the child callback manually
        rbac_mod._permission_cache["dummy_key"] = (True, time.monotonic())
        rbac_mod._reset_cache_after_fork()
        assert len(rbac_mod._permission_cache) == 0


@pytest.mark.asyncio
async def test_rbac_spicedb_imports_absent():
    """Test ImportError handling when grpc/authzed is missing."""
    # Reload rbac module clean
    _clear_rbac_metrics()
    if "app.auth.rbac" in sys.modules:
        del sys.modules["app.auth.rbac"]
    import app.auth.rbac as rbac_mod

    # Patch sys.modules to raise ImportError for grpc.aio
    with patch.dict("sys.modules", {"grpc": None, "grpc.aio": None}):
        checker = rbac_mod.PermissionChecker(channel=MagicMock())
        with pytest.raises(rbac_mod.SpiceDBUnavailableError) as exc_info:
            await checker.check_permission("semester", "current", "admin", "user-123")
        assert "grpc is not installed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rbac_check_admin():
    """Test check_admin proxy method calling check_permission."""
    _clear_rbac_metrics()
    if "app.auth.rbac" in sys.modules:
        del sys.modules["app.auth.rbac"]
    import app.auth.rbac as rbac_mod

    checker = rbac_mod.PermissionChecker(channel=MagicMock())
    with patch.object(
        checker, "check_permission", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = True
        res = await checker.check_admin("user-123")
        assert res is True
        mock_check.assert_awaited_once_with(
            resource_type="semester",
            resource_id="current",
            permission="admin",
            user_id="user-123",
        )


@pytest.mark.asyncio
async def test_rbac_cache_eviction_and_fallback():
    """Test LRU eviction logic and fallback cache behaviour on SpiceDB failures."""
    _clear_rbac_metrics()
    if "app.auth.rbac" in sys.modules:
        del sys.modules["app.auth.rbac"]
    import app.auth.rbac as rbac_mod

    # Temporarily set max size to 2 for testing popitem
    with patch("app.auth.rbac._PERMISSION_CACHE_MAX_SIZE", 2):
        # Set up mock authzed modules
        mock_stub = MagicMock()
        mock_stub.CheckPermission = AsyncMock()

        # CheckPermissionResponse mock
        mock_resp_true = MagicMock()
        mock_resp_true.permissionship = 1  # HAS_PERMISSION

        mock_resp_false = MagicMock()
        mock_resp_false.permissionship = 0

        # Stub definitions
        MockRequest = MagicMock()
        MockResponse = MagicMock()
        MockResponse.PERMISSIONSHIP_HAS_PERMISSION = 1
        MockObjectRef = MagicMock()
        MockSubjectRef = MagicMock()

        authzed_v1 = MagicMock()
        authzed_v1.CheckPermissionRequest = MockRequest
        authzed_v1.CheckPermissionResponse = MockResponse
        authzed_v1.ObjectReference = MockObjectRef
        authzed_v1.SubjectReference = MockSubjectRef
        authzed_v1.PermissionsServiceStub = MagicMock(return_value=mock_stub)

        with patch.dict(
            "sys.modules",
            {
                "authzed": MagicMock(),
                "authzed.api": MagicMock(),
                "authzed.api.v1": authzed_v1,
            },
        ):
            checker = rbac_mod.PermissionChecker(channel=MagicMock())

            # Reset cache
            rbac_mod._permission_cache.clear()

            # 1. First check -> True (added to cache)
            mock_stub.CheckPermission.return_value = mock_resp_true
            res1 = await checker.check_permission("r", "1", "p", "u1")
            assert res1 is True

            # 2. Second check -> False (added to cache)
            mock_stub.CheckPermission.return_value = mock_resp_false
            res2 = await checker.check_permission("r", "2", "p", "u1")
            assert res2 is False

            # Cache length is now 2
            assert len(rbac_mod._permission_cache) == 2

            # 3. Third check -> True (triggers eviction of the first key "r:1")
            mock_stub.CheckPermission.return_value = mock_resp_true
            res3 = await checker.check_permission("r", "3", "p", "u1")
            assert res3 is True
            assert len(rbac_mod._permission_cache) == 2
            # Key 1 was evicted
            assert ("u1", "r", "1", "p") not in rbac_mod._permission_cache

            # 4. Outage fallback check (True/Positive cache key still valid)
            # Make CheckPermission raise error
            mock_stub.CheckPermission.side_effect = Exception("SpiceDB outage")
            # "r:3" is cached as True
            fallback_res = await checker.check_permission("r", "3", "p", "u1")
            assert fallback_res is True  # Serves from cache

            # 5. Outage fallback check (False/Negative cache key still valid)
            # "r:2" is cached as False
            fallback_res2 = await checker.check_permission("r", "2", "p", "u1")
            assert fallback_res2 is False  # Serves from cache

            # 6. Outage fallback check (Expired cache entries)
            # Manually expire "r:3" in cache by setting time to 1 hour ago
            rbac_mod._permission_cache[("u1", "r", "3", "p")] = (
                True,
                time.monotonic() - 3600,
            )
            with pytest.raises(rbac_mod.SpiceDBUnavailableError):
                await checker.check_permission("r", "3", "p", "u1")
