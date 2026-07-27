"""Closure test for the MFA cleanup scheduler's network-error branch."""

import asyncio
from unittest.mock import patch

from app.services import mfa_challenge_cleanup
from app.services.mfa_challenge_cleanup import start_mfa_challenge_cleanup_scheduler


async def test_mfa_cleanup_scheduler_logs_os_error_and_continues():
    calls = 0

    async def cleanup(*, grace_period_seconds: int):
        del grace_period_seconds
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
            mfa_challenge_cleanup, "cleanup_stale_mfa_challenges", new=cleanup
        ),
        patch.object(mfa_challenge_cleanup.asyncio, "sleep", new=fast_sleep),
    ):
        stop = await start_mfa_challenge_cleanup_scheduler()
        await real_sleep(0.01)
        await stop()

    assert calls >= 2
