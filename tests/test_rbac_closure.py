"""Branch closure tests for PermissionChecker convenience proxies."""

import importlib.util
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.auth.rbac as rbac
from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError


@pytest.mark.asyncio
async def test_check_tenant_permission_delegates_with_tenant_scope():
    checker = PermissionChecker(MagicMock())
    checker.check_permission = AsyncMock(return_value=True)

    result = await checker.check_tenant_permission("tenant-1", "view", "user-1")

    assert result is True
    checker.check_permission.assert_awaited_once_with(
        resource_type="tenant",
        resource_id="tenant-1",
        permission="view",
        user_id="user-1",
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_check_campus_permission_delegates_with_optional_tenant_scope():
    checker = PermissionChecker(MagicMock())
    checker.check_permission = AsyncMock(return_value=False)

    result = await checker.check_campus_permission(
        "campus-1", "edit", "user-1", tenant_id="tenant-1"
    )

    assert result is False
    checker.check_permission.assert_awaited_once_with(
        resource_type="campus",
        resource_id="campus-1",
        permission="edit",
        user_id="user-1",
        tenant_id="tenant-1",
        campus_id="campus-1",
    )


class _AsyncBreaker:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_check_admin_and_campus_proxies_cover_optional_tenant():
    checker = PermissionChecker(MagicMock())
    checker.check_permission = AsyncMock(return_value=True)

    assert await checker.check_admin("user-1") is True
    await checker.check_campus_permission("campus-1", "view", "user-1")
    assert checker.check_permission.await_args_list[0].kwargs == {
        "resource_type": "semester",
        "resource_id": "current",
        "permission": "admin",
        "user_id": "user-1",
    }
    assert checker.check_permission.await_args_list[1].kwargs["tenant_id"] is None


@pytest.mark.asyncio
async def test_check_permission_allow_deny_and_lru_eviction():
    from authzed.api import v1

    rbac._permission_cache.clear()
    allowed = MagicMock(
        permissionship=v1.CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
    )
    denied = MagicMock(
        permissionship=v1.CheckPermissionResponse.PERMISSIONSHIP_NO_PERMISSION
    )
    stub = MagicMock()
    stub.CheckPermission = AsyncMock(side_effect=[allowed, denied])

    with (
        patch.object(v1, "PermissionsServiceStub", return_value=stub),
        patch.object(rbac, "_spicedb_breaker", _AsyncBreaker()),
        patch.object(rbac, "_PERMISSION_CACHE_MAX_SIZE", 1),
    ):
        checker = PermissionChecker(MagicMock())
        assert await checker.check_permission("doc", "1", "read", "u1") is True
        assert await checker.check_permission("doc", "2", "read", "u1") is False

    assert len(rbac._permission_cache) == 1


@pytest.mark.asyncio
async def test_check_permission_stale_positive_negative_and_uncached_errors():
    checker = PermissionChecker(MagicMock())

    async def unavailable(*_args, **_kwargs):
        raise ConnectionError("SpiceDB offline")

    stub = MagicMock(CheckPermission=AsyncMock(side_effect=unavailable))
    from authzed.api import v1

    with (
        patch.object(v1, "PermissionsServiceStub", return_value=stub),
        patch.object(rbac, "_spicedb_breaker", _AsyncBreaker()),
    ):
        positive_key = ("u", "doc", "1", "read", "", "")
        negative_key = ("u", "doc", "2", "read", "", "")
        rbac._permission_cache.clear()
        rbac._permission_cache[positive_key] = (True, time.monotonic())
        rbac._permission_cache[negative_key] = (False, time.monotonic())
        assert await checker.check_permission("doc", "1", "read", "u") is True
        assert await checker.check_permission("doc", "2", "read", "u") is False

        rbac._permission_cache[positive_key] = (
            True,
            time.monotonic() - rbac._PERMISSION_POSITIVE_TTL_SECONDS - 1,
        )
        with pytest.raises(SpiceDBUnavailableError):
            await checker.check_permission("doc", "1", "read", "u")

        rbac._permission_cache.clear()
        with pytest.raises(SpiceDBUnavailableError):
            await checker.check_permission("doc", "3", "read", "u")


@pytest.mark.asyncio
async def test_check_permission_import_error_fails_closed():
    checker = PermissionChecker(MagicMock())
    rbac._permission_cache.clear()
    with patch.dict(sys.modules, {"grpc": None}):
        with pytest.raises(SpiceDBUnavailableError, match="not installed"):
            await checker.check_permission("doc", "1", "read", "u")


def test_cache_reset_and_at_fork_registration_path():
    rbac._permission_cache["stale"] = (True, time.monotonic())  # type: ignore[index]
    rbac._reset_cache_after_fork()
    assert not rbac._permission_cache

    module_name = "app.auth.rbac_registration_coverage"
    spec = importlib.util.spec_from_file_location(module_name, rbac.__file__)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = loaded
    try:
        with (
            patch.object(os, "register_at_fork", create=True) as register,
            patch("prometheus_client.Counter", return_value=MagicMock()),
        ):
            spec.loader.exec_module(loaded)
        register.assert_called_once_with(after_in_child=loaded._reset_cache_after_fork)
    finally:
        sys.modules.pop(module_name, None)
