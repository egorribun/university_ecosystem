"""Closure tests for the scheduler's successful and cancellation paths."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.story_cleanup import StoryCleanupConfig, start_story_cleanup_scheduler


async def test_story_cleanup_scheduler_observes_deletions_and_reraises_cancelled():
    cleanup = AsyncMock(side_effect=[2, asyncio.CancelledError()])
    real_sleep = asyncio.sleep

    async def instant_sleep(_interval):
        await real_sleep(0)

    with (
        patch("app.services.story_cleanup.cleanup_expired_stories", new=cleanup),
        patch("app.services.story_cleanup.asyncio.sleep", new=instant_sleep),
    ):
        stop = await start_story_cleanup_scheduler(
            config=StoryCleanupConfig(interval_seconds=60)
        )
        await real_sleep(0.01)
        await stop()

    assert cleanup.await_count >= 2
