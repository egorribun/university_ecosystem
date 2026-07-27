"""Closure test for the scheduler's narrowed database-error handler."""

import asyncio
from unittest.mock import patch

from app.services import email_change_cleanup
from app.services.email_change_cleanup import start_email_change_cleanup_scheduler


async def test_email_change_cleanup_scheduler_logs_os_error_and_continues():
    calls = 0

    async def cleanup(*, retention_minutes: int):
        del retention_minutes
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("database unavailable")
        raise asyncio.CancelledError

    real_sleep = asyncio.sleep

    async def fast_sleep(_interval):
        await real_sleep(0)

    with (
        patch.object(
            email_change_cleanup,
            "cleanup_stale_email_change_tokens",
            new=cleanup,
        ),
        patch.object(email_change_cleanup.asyncio, "sleep", new=fast_sleep),
    ):
        stop = await start_email_change_cleanup_scheduler()
        await real_sleep(0.01)
        await stop()

    assert calls >= 2
