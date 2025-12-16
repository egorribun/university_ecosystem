import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.workers.notifications import (
    NotificationsScheduler,
    start_notifications_scheduler,
)


@pytest.mark.anyio
async def test_scheduler_init():
    # Test valid init
    scheduler = NotificationsScheduler(
        poll_seconds=10, window_minutes=5, max_backoff_seconds=100
    )
    assert scheduler.poll_seconds == 10
    assert scheduler.window_minutes == 5
    assert scheduler.max_backoff_seconds == 100

    # Test clamping
    scheduler = NotificationsScheduler(
        poll_seconds=0, window_minutes=-1, max_backoff_seconds=0
    )
    assert scheduler.poll_seconds == 1
    assert scheduler.window_minutes == 1
    assert scheduler.max_backoff_seconds == 1


@pytest.mark.anyio
async def test_scheduler_run_once(db_session):
    # Mock generate_schedule_reminders
    with patch(
        "app.workers.notifications.generate_schedule_reminders", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = 5

        # We need to mock async_session context manager if not using valid DB
        # But here we pass db_session in test, code uses `async with async_session() as db`.
        # So we must mock app.core.database.async_session

        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__.return_value = "db_session_mock"

        with patch("app.workers.notifications.async_session", return_value=mock_db_ctx):
            scheduler = NotificationsScheduler(
                poll_seconds=1, window_minutes=1, max_backoff_seconds=1
            )
            count = await scheduler.run_once()

            assert count == 5
            mock_gen.assert_called_once_with("db_session_mock", window_minutes=1)


@pytest.mark.anyio
async def test_scheduler_run_forever_logic():
    # Test that run_forever loops and handles errors/backoff
    # We will cancel it after a few iterations

    scheduler = NotificationsScheduler(
        poll_seconds=1, window_minutes=1, max_backoff_seconds=10
    )

    with patch.object(scheduler, "run_once", SideEffect=AsyncMock) as mock_run:
        # 1. Success
        # 2. Error (trigger backoff)
        # 3. Success (reset backoff)
        # 4. Cancel

        outputs = [10, Exception("Boom"), 5, asyncio.CancelledError()]

        async def side_effect(*args, **kwargs):
            if not outputs:
                raise asyncio.CancelledError()
            val = outputs.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

        mock_run.side_effect = side_effect

        # Mock sleep to run fast
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                await scheduler.run_forever()

            assert mock_run.call_count >= 4
            assert mock_sleep.call_count >= 2


@pytest.mark.anyio
async def test_start_stop_scheduler():
    # Test wrapper
    stop = await start_notifications_scheduler(poll_seconds=10)
    assert stop
    await stop()
