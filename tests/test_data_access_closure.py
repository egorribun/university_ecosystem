"""Closure test for owned-session access-log cleanup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.data_access import cleanup_access_logs


@pytest.mark.asyncio
async def test_cleanup_access_logs_opens_session_when_db_is_not_supplied():
    session = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    repository = MagicMock()
    repository.prune_logs = AsyncMock(return_value=4)

    with (
        patch("app.services.data_access.async_session", return_value=session_context),
        patch(
            "app.services.data_access.AuditRepository",
            return_value=repository,
        ),
    ):
        assert await cleanup_access_logs(db=None, retention_days=30) == 4

    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()
    repository.prune_logs.assert_awaited_once()
