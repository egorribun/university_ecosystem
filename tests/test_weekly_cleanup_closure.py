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
async def test_subscription_cleanup_commits_each_orphan_batch_and_logs_total():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.fetchmany.side_effect = [["orphan-1", "orphan-2"], []]
    session.execute.return_value = result

    with patch.object(weekly_cleanup.logger, "info") as info:
        removed = await weekly_cleanup._delete_orphaned_subscriptions(session)

    assert removed == 2
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once_with()
    info.assert_called_once_with(
        "weekly_cleanup.deleted_orphaned_subscriptions", extra={"count": 2}
    )


@pytest.mark.asyncio
async def test_subscription_cleanup_commits_each_stale_batch_and_logs_total():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.fetchmany.side_effect = [["stale-1"], []]
    session.execute.return_value = result

    with patch.object(weekly_cleanup.logger, "info") as info:
        removed = await weekly_cleanup._delete_stale_subscriptions(session)

    assert removed == 1
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once_with()
    info.assert_called_once_with(
        "weekly_cleanup.deleted_stale_subscriptions", extra={"count": 1}
    )


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


@pytest.mark.asyncio
async def test_reindex_quotes_valid_database_identifier_and_executes_autocommit():
    connection = MagicMock()
    connection.dialect.identifier_preparer.quote.return_value = '"university_db"'
    connection.execution_options = AsyncMock(return_value=connection)
    connection.exec_driver_sql = AsyncMock()
    engine_context = MagicMock()
    engine_context.__aenter__ = AsyncMock(return_value=connection)
    engine_context.__aexit__ = AsyncMock(return_value=False)
    engine_stub = MagicMock()
    engine_stub.connect.return_value = engine_context

    with (
        patch.object(
            weekly_cleanup.settings,
            "database_url",
            "postgresql://user@localhost/university_db",
        ),
        patch.object(weekly_cleanup, "engine", engine_stub),
        patch.object(weekly_cleanup.logger, "info") as info,
    ):
        await weekly_cleanup._reindex_database()

    connection.dialect.identifier_preparer.quote.assert_called_once_with(
        "university_db"
    )
    connection.execution_options.assert_awaited_once_with(isolation_level="AUTOCOMMIT")
    connection.exec_driver_sql.assert_awaited_once_with(
        'REINDEX DATABASE "university_db"'
    )
    info.assert_called_once_with(
        "weekly_cleanup.reindex_completed", extra={"database": "university_db"}
    )


@pytest.mark.asyncio
async def test_run_weekly_cleanup_aggregates_deletions_and_reindexes():
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=MagicMock())
    session_context.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(weekly_cleanup, "async_session", return_value=session_context),
        patch.object(
            weekly_cleanup,
            "_delete_orphaned_subscriptions",
            new=AsyncMock(return_value=4),
        ) as orphaned,
        patch.object(
            weekly_cleanup,
            "_delete_stale_subscriptions",
            new=AsyncMock(return_value=6),
        ) as stale,
        patch.object(weekly_cleanup, "_reindex_database", new=AsyncMock()) as reindex,
        patch.object(weekly_cleanup.logger, "info") as info,
    ):
        stats = await weekly_cleanup.run_weekly_cleanup()

    orphaned.assert_awaited_once_with(session_context.__aenter__.return_value)
    stale.assert_awaited_once_with(session_context.__aenter__.return_value)
    reindex.assert_awaited_once_with()
    assert stats == {
        "subscriptions_removed": 10,
        "subscriptions_orphaned": 4,
        "subscriptions_stale": 6,
    }
    info.assert_called_once_with("weekly_cleanup.completed", extra=stats)
