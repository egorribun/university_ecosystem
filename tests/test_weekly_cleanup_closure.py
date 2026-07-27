"""Closure tests for empty cleanup batches and safe reindex guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.management import weekly_cleanup


@pytest.mark.asyncio
async def test_subscription_cleanup_returns_zero_without_commits_for_empty_batches():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.fetchmany.return_value = []
    session.execute.return_value = result

    assert await weekly_cleanup._delete_orphaned_subscriptions(session) == 0
    assert await weekly_cleanup._delete_stale_subscriptions(session) == 0
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reindex_skips_missing_database_name():
    with (
        patch.object(
            weekly_cleanup.settings, "database_url", "postgresql://user@localhost/"
        ),
        patch.object(weekly_cleanup.logger, "warning") as warning,
    ):
        await weekly_cleanup._reindex_database()

    warning.assert_called_once_with("Skipping database reindex: database name is empty")


@pytest.mark.asyncio
async def test_reindex_skips_unsafe_database_identifier():
    with (
        patch.object(
            weekly_cleanup.settings,
            "database_url",
            "postgresql://user@localhost/bad-name",
        ),
        patch.object(weekly_cleanup.logger, "error") as error,
    ):
        await weekly_cleanup._reindex_database()

    error.assert_called_once()
    assert "failed identifier validation" in error.call_args.args[0]
