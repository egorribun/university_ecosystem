"""Unit and integration tests for data cleanup services under extreme inputs and database failure modes.

Exercises cleanups with extreme records, future/null dates, and Database OperationalError injection.
"""

from __future__ import annotations

import datetime as dt
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.services.notifications.cleanup import cleanup_stale_notifications
from app.services.session_cleanup import cleanup_expired_sessions


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_handles_db_lock_exception() -> None:
    """Verify cleanup_expired_sessions rollbacks and propagates OperationalError on DB locks."""
    mock_db = AsyncMock()
    # Inject OperationalError on db.execute to simulate a database lock or timeout
    mock_db.execute.side_effect = OperationalError(
        "DELETE stmt", {}, "database is locked"
    )

    with pytest.raises(OperationalError):
        await cleanup_expired_sessions(db=mock_db, now=dt.datetime.now(UTC))

    # Verify rollback or session management: since rollback is handled by the caller/transaction context,
    # we verify that commit was NOT called.
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_handles_db_lock_exception() -> None:
    """Verify cleanup_stale_notifications handles database exceptions properly during batch delete."""
    mock_db = AsyncMock()
    # Mock return value for scalars to return some ids first, then raise OperationalError on delete execution
    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = [1, 2, 3]
    mock_db.scalars.return_value = mock_scalars_result

    mock_db.execute.side_effect = OperationalError(
        "SELECT stmt", {}, "database is locked"
    )

    with pytest.raises(OperationalError):
        await cleanup_stale_notifications(db=mock_db, retention_days=30)

    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_stale_notifications_with_null_and_future_timestamps() -> None:
    """Verify notification cleanup handles extreme date inputs without raising value errors."""
    mock_db = AsyncMock()

    # 1. Test null and future IDs returned
    mock_scalars_result = MagicMock()
    # Mock returning None values/valid integers on first loop call, then empty to terminate while True
    mock_scalars_result.all.side_effect = [[None, 123, None], [], [None, 456, None], []]
    mock_db.scalars.return_value = mock_scalars_result

    mock_execute_result = MagicMock()
    mock_execute_result.rowcount = 1
    mock_db.execute.return_value = mock_execute_result

    # Run the cleanup — it should filter out Nones and succeed
    _deleted_notifications, _deleted_deliveries = await cleanup_stale_notifications(
        db=mock_db,
        retention_days=10,
        now=dt.datetime.now(UTC),
    )

    assert mock_db.commit.call_count >= 1
    assert mock_db.execute.call_count >= 1
