"""Branch closure tests for PermissionChecker convenience proxies."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.rbac import PermissionChecker


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
