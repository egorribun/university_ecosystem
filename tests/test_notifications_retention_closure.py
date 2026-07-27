"""Closure tests for scheduler success and completed-task shutdown paths."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.notifications_retention import (
    NotificationsRetentionConfig,
    start_notifications_retention_scheduler,
)


@pytest.mark.asyncio
async def test_retention_scheduler_observes_successful_cleanup_then_stops():
    calls = 0

    async def cleanup(*, retention_days: int) -> tuple[int, int]:
        nonlocal calls
        calls += 1
        return retention_days, 2

    with patch(
        "app.services.notifications_retention.cleanup_stale_notifications",
        side_effect=cleanup,
    ):
        stop = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(retention_days=7, interval_seconds=300)
        )
        await asyncio.sleep(0)
        await stop()

    assert calls == 1


@pytest.mark.asyncio
async def test_retention_stop_handles_already_finished_task_error():
    finished_task = MagicMock()
    finished_task.done.return_value = True
    finished_task.result.side_effect = RuntimeError("finished with error")
    loop = MagicMock()

    def create_task(coro):
        coro.close()
        return finished_task

    loop.create_task.side_effect = create_task

    with patch(
        "app.services.notifications_retention.asyncio.get_running_loop",
        return_value=loop,
    ):
        stop = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(retention_days=7)
        )
        await stop()

    finished_task.result.assert_called_once_with()


@pytest.mark.asyncio
async def test_retention_cleanup_cancellation_is_safe_to_stop():
    async def cancelled_cleanup(*, retention_days: int) -> tuple[int, int]:
        raise asyncio.CancelledError

    with patch(
        "app.services.notifications_retention.cleanup_stale_notifications",
        new=cancelled_cleanup,
    ):
        stop = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(retention_days=7, interval_seconds=300)
        )
        await asyncio.sleep(0.01)
        await stop()
