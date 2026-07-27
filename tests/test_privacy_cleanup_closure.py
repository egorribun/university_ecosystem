"""Closure tests for privacy scheduler cancellation and error handling."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.privacy_cleanup import (
    PrivacyCleanupConfig,
    start_privacy_cleanup_scheduler,
)


@pytest.mark.asyncio
async def test_privacy_cleanup_stop_suppresses_finished_cancelled_task():
    finished_task = MagicMock()
    finished_task.done.return_value = True
    finished_task.result.side_effect = asyncio.CancelledError
    loop = MagicMock()

    def create_task(coro):
        coro.close()
        return finished_task

    loop.create_task.side_effect = create_task
    with patch(
        "app.services.privacy_cleanup.asyncio.get_running_loop", return_value=loop
    ):
        stop = await start_privacy_cleanup_scheduler(
            config=PrivacyCleanupConfig(interval_seconds=60)
        )
        await stop()

    finished_task.result.assert_called_once_with()


@pytest.mark.asyncio
async def test_privacy_cleanup_scheduler_handles_cancellation_from_cleanup():
    async def cancelled_cleanup(**kwargs):
        raise asyncio.CancelledError

    with patch(
        "app.services.privacy_cleanup.cleanup_privacy_artifacts",
        new=cancelled_cleanup,
    ):
        stop = await start_privacy_cleanup_scheduler(
            config=PrivacyCleanupConfig(interval_seconds=60)
        )
        await asyncio.sleep(0.01)
        await stop()
