"""Coverage tests (testing session 10) for the session-cleanup scheduler loop
(app/services/session_cleanup.py:161-184) which the existing
tests/test_session_cleanup.py does not reach (it covers SessionCleanupConfig +
cleanup_expired_sessions with a patched delete fn, but not the
start_session_cleanup_scheduler background loop / _stop teardown).

Approach: patch cleanup_expired_sessions to a fast AsyncMock, start the
scheduler, let the immediate first tick run, then call the returned stop()
which cancels the loop (covers the CancelledError teardown 182-184 + _stop).
"""

from __future__ import annotations

import asyncio

import pytest

import app.services.session_cleanup as session_cleanup_module
from app.services.session_cleanup import (
    SessionCleanupConfig,
    start_session_cleanup_scheduler,
)


@pytest.mark.asyncio
async def test_scheduler_runs_first_tick_then_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = 0

    async def _fake_cleanup() -> int:
        nonlocal ticks
        ticks += 1
        return 3

    monkeypatch.setattr(
        session_cleanup_module, "cleanup_expired_sessions", _fake_cleanup
    )

    stop = await start_session_cleanup_scheduler(
        config=SessionCleanupConfig(interval_seconds=30)
    )
    # The first cleanup runs immediately, before the 30s sleep; yield to it.
    await asyncio.sleep(0.05)
    assert ticks >= 1, "scheduler should run an immediate first tick"

    # stop() cancels the loop task → CancelledError teardown path runs and is
    # suppressed inside _stop's cancel branch.
    await stop()


@pytest.mark.asyncio
async def test_scheduler_stop_before_first_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def _fake_cleanup() -> int:
        started.set()
        return 0

    monkeypatch.setattr(
        session_cleanup_module, "cleanup_expired_sessions", _fake_cleanup
    )

    stop = await start_session_cleanup_scheduler(config=SessionCleanupConfig())
    await asyncio.wait_for(started.wait(), timeout=2.0)
    await stop()
