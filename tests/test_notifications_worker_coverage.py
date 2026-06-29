import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.workers.notifications import (
    NotificationsScheduler,
    start_notifications_scheduler,
    _wait_for_signals,
    run_worker,
)
from app.core.observability import WorkerMetrics

@pytest.mark.anyio
async def test_scheduler_run_once():
    scheduler = NotificationsScheduler(
        poll_seconds=1,
        window_minutes=15,
        max_backoff_seconds=30,
        metrics=None
    )
    with patch("app.workers.notifications.generate_schedule_reminders", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 5
        res = await scheduler.run_once()
        assert res == 5
        mock_gen.assert_called_once()

@pytest.mark.anyio
async def test_scheduler_run_forever_success():
    mock_metrics = MagicMock(spec=WorkerMetrics)
    scheduler = NotificationsScheduler(
        poll_seconds=1,
        window_minutes=15,
        max_backoff_seconds=30,
        metrics=mock_metrics
    )
    
    async def mock_run_once():
        return 3

    scheduler.run_once = mock_run_once

    task = asyncio.create_task(scheduler.run_forever())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    mock_metrics.record_success.assert_called_with(3)

@pytest.mark.anyio
async def test_scheduler_run_forever_failure():
    mock_metrics = MagicMock(spec=WorkerMetrics)
    scheduler = NotificationsScheduler(
        poll_seconds=1,
        window_minutes=15,
        max_backoff_seconds=5,
        metrics=mock_metrics
    )
    
    async def mock_run_once():
        raise ValueError("database error")

    scheduler.run_once = mock_run_once

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        task = asyncio.create_task(scheduler.run_forever())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_metrics.record_failure.assert_called()

@pytest.mark.anyio
async def test_start_notifications_scheduler():
    mock_metrics = MagicMock(spec=WorkerMetrics)
    
    stop_fn = await start_notifications_scheduler(
        poll_seconds=5,
        window_minutes=10,
        max_backoff_seconds=15,
        metrics=mock_metrics
    )
    
    assert stop_fn is not None
    
    stop_fn2 = await start_notifications_scheduler(
        poll_seconds=5,
        window_minutes=10,
        max_backoff_seconds=15,
        metrics=mock_metrics
    )
    
    assert stop_fn2 is not None
    
    await stop_fn()
    await stop_fn2()

@pytest.mark.anyio
async def test_wait_for_signals():
    stop_event = asyncio.Event()
    
    async def trigger():
        await asyncio.sleep(0.01)
        stop_event.set()
        
    asyncio.create_task(trigger())
    await _wait_for_signals(stop_event)
    assert stop_event.is_set()

@pytest.mark.anyio
async def test_run_worker_flow():
    with patch("app.workers.notifications.configure_worker_observability") as mock_obs, \
         patch("app.workers.notifications.create_worker_metrics") as mock_metrics, \
         patch("app.workers.notifications.create_worker_monitoring_app") as mock_app, \
         patch("app.workers.notifications.start_worker_monitoring_server", new_callable=AsyncMock) as mock_server, \
         patch("app.workers.notifications.wait_db", new_callable=AsyncMock) as mock_wait_db, \
         patch("app.workers.notifications.NotificationsScheduler.run_forever", new_callable=AsyncMock) as mock_run_forever, \
         patch("app.workers.notifications._wait_for_signals", new_callable=AsyncMock) as mock_wait_signals, \
         patch("app.workers.notifications.webpush.cleanup") as mock_cleanup:

        mock_server.return_value = AsyncMock()

        async def trigger_signals(stop_event):
            stop_event.set()

        mock_wait_signals.side_effect = trigger_signals

        await run_worker()

        mock_obs.assert_called_once()
        mock_wait_db.assert_called_once()
        mock_cleanup.assert_called_once()
