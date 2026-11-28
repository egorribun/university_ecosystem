from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from authzed.api import v1

from app.auth import rbac


@pytest.mark.parametrize("cached_allow", [False, True])
async def test_spicedb_outage_logs_omit_permission_identifiers(
    cached_allow: bool,
) -> None:
    resource_id = str(uuid4())
    user_id = str(uuid4())
    cache = rbac._make_fresh_cache()
    cache_age = 2.0
    now = 100.0
    if cached_allow:
        cache[(user_id, "event", resource_id, "view", "", "")] = (
            True,
            now - cache_age,
        )

    stub = MagicMock(
        CheckPermission=AsyncMock(
            side_effect=ConnectionError("private transport diagnostic")
        )
    )
    checker = rbac.PermissionChecker(MagicMock())
    with (
        patch.object(v1, "PermissionsServiceStub", return_value=stub),
        patch.object(rbac, "_spicedb_breaker", AsyncMock()),
        patch.object(rbac, "_permission_cache", cache),
        patch.object(rbac, "time", SimpleNamespace(monotonic=lambda: now)),
        patch.object(rbac.logger, "error") as error,
        patch.object(rbac.logger, "warning") as warning,
    ):
        if cached_allow:
            assert await checker.check_permission("event", resource_id, "view", user_id)
        else:
            with pytest.raises(rbac.SpiceDBUnavailableError):
                await checker.check_permission("event", resource_id, "view", user_id)

    if cached_allow:
        warning.assert_called_once_with(
            "SpiceDB unavailable — serving cached permission result",
            resource_type="event",
            permission="view",
            cache_age_seconds=cache_age,
            allowed=True,
        )
    else:
        warning.assert_not_called()
    error.assert_called_once_with(
        "SpiceDB async permission check failed",
        resource_type="event",
        permission="view",
        error_type="ConnectionError",
    )
