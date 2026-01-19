"""Tests for notifications worker module.

Coverage targets:
- NotificationsScheduler: run_once, run_forever (error handling)
- start_notifications_scheduler: task management
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.notifications import (
    NotificationsScheduler,
    start_notifications_scheduler,
)


@pytest.fixture
def mock_metrics():
    """Create mock WorkerMetrics."""
    metrics = MagicMock()
    metrics.record_success = MagicMock()
    metrics.record_failure = MagicMock()
    return metrics


# ============================================================
# NotificationsScheduler tests
# ============================================================


@pytest.mark.asyncio
async def test_scheduler_init_normalization():
    """Test parameter normalization in constructor."""
    scheduler = NotificationsScheduler(
        poll_seconds=0, window_minutes=-5, max_backoff_seconds=10
    )
    assert scheduler.poll_seconds == 1
    assert scheduler.window_minutes == 1
    assert scheduler.max_backoff_seconds == 10


@pytest.mark.asyncio
async def test_scheduler_run_once():
    """Test run_once execution."""
    scheduler = NotificationsScheduler(
        poll_seconds=60, window_minutes=30, max_backoff_seconds=3600
    )

    with patch("app.workers.notifications.generate_schedule_reminders", return_value=5):
        with patch("app.workers.notifications.async_session") as mock_session_factory:
            mock_session_factory.return_value.__aenter__.return_value = AsyncMock()
            result = await scheduler.run_once()

    assert result == 5


@pytest.mark.asyncio
async def test_scheduler_run_forever_success(mock_metrics):
    """Test successful iteration in run_forever."""
    scheduler = NotificationsScheduler(
        poll_seconds=0.1, window_minutes=30, max_backoff_seconds=1, metrics=mock_metrics
    )

    call_count = 0

    async def mock_run_once():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()
        return 3

    with patch.object(scheduler, "run_once", side_effect=mock_run_once):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_forever()

    assert call_count >= 2
    mock_metrics.record_success.assert_called_with(3)


@pytest.mark.asyncio
async def test_scheduler_run_forever_failure(mock_metrics):
    """Test error handling and backoff in run_forever."""
    scheduler = NotificationsScheduler(
        poll_seconds=0.1, window_minutes=30, max_backoff_seconds=1, metrics=mock_metrics
    )

    call_count = 0

    async def mock_run_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Test error")
        raise asyncio.CancelledError()

    with patch.object(scheduler, "run_once", side_effect=mock_run_once):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_forever()

    mock_metrics.record_failure.assert_called_once()


# ============================================================
# start_notifications_scheduler tests
# ============================================================


@pytest.mark.asyncio
async def test_start_notifications_scheduler_lifecycle():
    """Test starting and stopping the scheduler."""
    with patch(
        "app.workers.notifications.NotificationsScheduler"
    ) as mock_scheduler_cls:
        mock_scheduler = mock_scheduler_cls.return_value
        mock_scheduler.run_forever = AsyncMock()

        stop_fn = await start_notifications_scheduler(
            poll_seconds=60, window_minutes=30, max_backoff_seconds=3600
        )

        assert callable(stop_fn)
        await stop_fn()
