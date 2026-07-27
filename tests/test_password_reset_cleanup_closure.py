"""Closure test for the password reset cleanup scheduler error branch."""

import asyncio
from unittest.mock import patch

from app.services import password_reset_cleanup
from app.services.password_reset_cleanup import start_password_reset_cleanup_scheduler


async def test_password_reset_cleanup_scheduler_logs_os_error_and_continues():
    calls = 0

    async def cleanup(*, retention_minutes: int):
        del retention_minutes
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("database unavailable")
        await asyncio.Event().wait()

    real_sleep = asyncio.sleep

    async def fast_sleep(_interval):
        await real_sleep(0)

    with (
        patch.object(
            password_reset_cleanup,
            "cleanup_stale_password_reset_tokens",
            new=cleanup,
        ),
        patch.object(password_reset_cleanup.asyncio, "sleep", new=fast_sleep),
    ):
        stop = await start_password_reset_cleanup_scheduler()
        await real_sleep(0.01)
        await stop()

    assert calls >= 2
