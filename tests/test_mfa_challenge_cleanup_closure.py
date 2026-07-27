"""Closure test for the MFA cleanup scheduler's network-error branch."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_mfa_cleanup_uses_default_clock_and_settings(monkeypatch):
    db = AsyncMock()
    purge = AsyncMock(return_value=4)
    monkeypatch.setattr(mfa_challenge_cleanup, "purge_expired_challenges", purge)

    deleted = await mfa_challenge_cleanup.cleanup_stale_mfa_challenges(db=db)

    assert deleted == 4
    purge.assert_awaited_once()
    assert purge.await_args.kwargs["grace_period_seconds"] >= 0
    assert isinstance(purge.await_args.kwargs["now"], datetime)
    assert purge.await_args.kwargs["now"].tzinfo is UTC
    db.commit.assert_awaited_once()


async def test_mfa_cleanup_opens_owned_session(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        mfa_challenge_cleanup, "purge_expired_challenges", AsyncMock(return_value=1)
    )
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=db)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch.object(mfa_challenge_cleanup, "async_session", session_factory):
        deleted = await mfa_challenge_cleanup.cleanup_stale_mfa_challenges(
            grace_period_seconds=10,
            now=datetime.now(UTC),
        )

    assert deleted == 1
    db.commit.assert_awaited_once()
