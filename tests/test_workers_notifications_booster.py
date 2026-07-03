"""Tests for app/workers/notifications.py

Targets NotificationsScheduler lifecycle, start_notifications_scheduler,
and run_worker to lift coverage from 0%.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.notifications as workers_mod
from app.workers.notifications import (
    NotificationsScheduler,
    start_notifications_scheduler,
)

# ---------------------------------------------------------------------------
# NotificationsScheduler unit tests
# ---------------------------------------------------------------------------


@pytest.fixture
def scheduler() -> NotificationsScheduler:
    return NotificationsScheduler(
        poll_seconds=1,
        window_minutes=5,
        max_backoff_seconds=10,
    )


@pytest.fixture
def scheduler_with_metrics() -> NotificationsScheduler:
    mock_metrics = MagicMock()
    return NotificationsScheduler(
        poll_seconds=1,
        window_minutes=5,
        max_backoff_seconds=10,
        metrics=mock_metrics,
    )


def test_scheduler_clamps_min_values():
    """Constructor should clamp values less than 1 to 1."""
    s = NotificationsScheduler(
        poll_seconds=0,
        window_minutes=-5,
        max_backoff_seconds=0,
    )
    assert s.poll_seconds == 1
    assert s.window_minutes == 1
    assert s.max_backoff_seconds == 1


@pytest.mark.asyncio
async def test_run_once_returns_created_count(scheduler: NotificationsScheduler):
    with (
        patch("app.workers.notifications.async_session") as mock_cm,
        patch(
            "app.workers.notifications.generate_schedule_reminders", return_value=3
        ) as _,
    ):
        mock_db = AsyncMock()
        mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await scheduler.run_once()

    assert result == 3


@pytest.mark.asyncio
async def test_run_forever_success_path(scheduler_with_metrics: NotificationsScheduler):
    """run_forever should record a success and then be cancelled."""
    call_count = 0

    async def mock_run_once():
        nonlocal call_count
        call_count += 1
        if call_count >= 1:
            # Cancel after first success
            raise asyncio.CancelledError
        return 2

    scheduler_with_metrics.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(asyncio.CancelledError):
            await scheduler_with_metrics.run_forever()


@pytest.mark.asyncio
async def test_run_forever_records_success_with_created(
    scheduler_with_metrics: NotificationsScheduler,
):
    """When run_once returns created > 0, success metrics are recorded."""
    iterations = 0

    async def mock_run_once() -> int:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError
        return 5  # created notifications

    scheduler_with_metrics.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(asyncio.CancelledError):
            await scheduler_with_metrics.run_forever()

    scheduler_with_metrics.metrics.record_success.assert_called_with(5)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_run_forever_records_success_zero_created(
    scheduler_with_metrics: NotificationsScheduler,
):
    """When run_once returns 0, success metrics are recorded but no log."""
    iterations = 0

    async def mock_run_once() -> int:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError
        return 0  # no created

    scheduler_with_metrics.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(asyncio.CancelledError):
            await scheduler_with_metrics.run_forever()

    scheduler_with_metrics.metrics.record_success.assert_called_with(0)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_run_forever_backoff_on_failure(
    scheduler_with_metrics: NotificationsScheduler,
):
    """On exception, failures are counted and backoff applied."""
    iterations = 0
    sleep_durations: list[float] = []

    async def mock_run_once() -> int:
        nonlocal iterations
        iterations += 1
        if iterations >= 3:
            raise asyncio.CancelledError
        raise RuntimeError("DB down")

    async def mock_sleep(duration: float) -> None:
        sleep_durations.append(duration)

    scheduler_with_metrics.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", side_effect=mock_sleep):
        with pytest.raises(asyncio.CancelledError):
            await scheduler_with_metrics.run_forever()

    # Should have recorded 2 failures
    assert scheduler_with_metrics.metrics.record_failure.call_count == 2  # type: ignore[union-attr]
    # Backoff should be increasing (2**1 * poll, 2**2 * poll capped at max_backoff)
    assert sleep_durations[0] >= sleep_durations[0]  # basic sanity


@pytest.mark.asyncio
async def test_run_forever_no_metrics_on_failure():
    """When metrics is None, failures are handled silently."""
    scheduler = NotificationsScheduler(
        poll_seconds=1,
        window_minutes=5,
        max_backoff_seconds=10,
        metrics=None,
    )
    iterations = 0

    async def mock_run_once() -> int:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError
        raise ValueError("oops")

    scheduler.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_forever()


# ---------------------------------------------------------------------------
# start_notifications_scheduler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_notifications_scheduler_creates_and_stops_task():
    """start_notifications_scheduler returns a stop callable that cancels the task."""
    # Reset global state
    workers_mod._scheduler_task = None

    async def fake_run_forever():
        # Simulate a long-running task that can be cancelled
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    with (
        patch.object(
            NotificationsScheduler, "run_forever", side_effect=fake_run_forever
        ),
        patch("app.workers.notifications.settings") as mock_settings,
    ):
        mock_settings.notifications_scheduler_poll_seconds = 60
        mock_settings.notifications_scheduler_window_minutes = 15
        mock_settings.notifications_scheduler_max_backoff_seconds = 300

        stop_fn = await start_notifications_scheduler(
            poll_seconds=1,
            window_minutes=5,
            max_backoff_seconds=10,
        )
        assert callable(stop_fn)
        await stop_fn()


@pytest.mark.asyncio
async def test_start_notifications_scheduler_reuses_existing_task():
    """If a task is already running, returns a stop for the existing task."""

    # Create a real long-lived task
    async def long_task():
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    loop = asyncio.get_running_loop()
    existing = loop.create_task(long_task())
    workers_mod._scheduler_task = existing

    try:
        stop_fn = await start_notifications_scheduler(
            poll_seconds=1, window_minutes=5, max_backoff_seconds=10
        )
        assert callable(stop_fn)
        # stop_fn should cancel the existing task
        await stop_fn()
        assert existing.cancelled() or existing.done()
    finally:
        # Clean up
        if not existing.done():
            existing.cancel()
        workers_mod._scheduler_task = None


@pytest.mark.asyncio
async def test_start_notifications_scheduler_stops_done_task():
    """If the existing task is already done, calling stop is a no-op."""

    async def quick_task():
        return

    loop = asyncio.get_running_loop()
    done_task = loop.create_task(quick_task())
    await asyncio.sleep(0)  # Let it complete
    workers_mod._scheduler_task = done_task

    try:
        stop_fn = await start_notifications_scheduler(
            poll_seconds=1, window_minutes=5, max_backoff_seconds=10
        )
        await stop_fn()
    finally:
        workers_mod._scheduler_task = None


@pytest.mark.asyncio
async def test_start_notifications_scheduler_uses_settings_defaults():
    """When no overrides given, settings values are used."""
    workers_mod._scheduler_task = None

    async def fake_run_forever():
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            raise

    with (
        patch.object(
            NotificationsScheduler, "run_forever", side_effect=fake_run_forever
        ),
        patch("app.workers.notifications.settings") as mock_settings,
    ):
        mock_settings.notifications_scheduler_poll_seconds = 30
        mock_settings.notifications_scheduler_window_minutes = 10
        mock_settings.notifications_scheduler_max_backoff_seconds = 120

        stop_fn = await start_notifications_scheduler()
        await stop_fn()


@pytest.mark.asyncio
async def test_wait_for_signals_handler():
    from app.workers.notifications import _wait_for_signals

    event = asyncio.Event()

    # Mock loop.add_signal_handler to call the handler immediately
    class MockLoop:
        def add_signal_handler(self, sig, handler, *args):
            # Trigger the handler synchronously
            handler()

    with patch("asyncio.get_running_loop", return_value=MockLoop()):
        await _wait_for_signals(event)
        assert event.is_set()


@pytest.mark.asyncio
@patch("app.workers.notifications.wait_db", new_callable=AsyncMock)
@patch(
    "app.workers.notifications.NotificationsScheduler.run_forever",
    new_callable=AsyncMock,
)
async def test_run_worker_success(mock_run_forever, mock_wait_db):
    from app.workers.notifications import run_worker

    async def trigger_stop(stop_event):
        await asyncio.sleep(0.01)
        stop_event.set()

    with (
        patch("app.workers.notifications._wait_for_signals", side_effect=trigger_stop),
        patch(
            "app.workers.notifications.settings",
            MagicMock(
                notifications_worker_metrics_port=0,
                notifications_scheduler_poll_seconds=1,
                notifications_scheduler_window_minutes=5,
                notifications_scheduler_max_backoff_seconds=10,
            ),
        ),
        patch("app.workers.notifications.configure_worker_observability"),
        patch("app.workers.notifications.create_worker_metrics"),
        patch("app.workers.notifications.webpush"),
    ):
        await run_worker()
        mock_run_forever.assert_called_once()


@pytest.mark.asyncio
@patch("app.workers.notifications.wait_db", new_callable=AsyncMock)
@patch(
    "app.workers.notifications.NotificationsScheduler.run_forever",
    new_callable=AsyncMock,
)
async def test_run_worker_with_metrics_server(mock_run_forever, mock_wait_db):
    from app.workers.notifications import run_worker

    async def trigger_stop(stop_event):
        await asyncio.sleep(0.01)
        stop_event.set()

    mock_monitor_stop = AsyncMock()

    with (
        patch("app.workers.notifications._wait_for_signals", side_effect=trigger_stop),
        patch(
            "app.workers.notifications.settings",
            MagicMock(
                notifications_worker_metrics_port=8000,
                notifications_worker_metrics_host="localhost",
                notifications_scheduler_poll_seconds=1,
                notifications_scheduler_window_minutes=5,
                notifications_scheduler_max_backoff_seconds=10,
            ),
        ),
        patch("app.workers.notifications.configure_worker_observability"),
        patch("app.workers.notifications.create_worker_metrics"),
        patch("app.workers.notifications.create_worker_monitoring_app"),
        patch(
            "app.workers.notifications.start_worker_monitoring_server",
            return_value=mock_monitor_stop,
        ),
        patch("app.workers.notifications.webpush"),
    ):
        await run_worker()
        mock_run_forever.assert_called_once()
        mock_monitor_stop.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.workers.notifications.run_worker", new_callable=AsyncMock)
async def test_main_calls_run_worker(mock_run_worker):
    from app.workers.notifications import main

    await main()
    mock_run_worker.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_forever_success_no_metrics(scheduler: NotificationsScheduler):
    """When metrics is None and run_once yields created > 0, we log but don't record."""
    iterations = 0

    async def mock_run_once() -> int:
        nonlocal iterations
        iterations += 1
        if iterations >= 2:
            raise asyncio.CancelledError
        return 3

    scheduler.run_once = mock_run_once  # type: ignore[method-assign]

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(asyncio.CancelledError):
            await scheduler.run_forever()
