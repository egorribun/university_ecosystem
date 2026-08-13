from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.lifespan import _SCHEDULER_STOP, _periodic_scheduler_loop


@pytest.mark.asyncio
async def test_periodic_scheduler_loop_runs_a_cleanup_cycle() -> None:
    """Keep the scheduler mapped in mutmut's hermetic test population."""

    _SCHEDULER_STOP.clear()
    cleanup = SimpleNamespace()

    async def kick() -> None:
        _SCHEDULER_STOP.set()

    cleanup.kick = kick
    wait_calls = 0

    async def wait_for(awaitable: object, timeout: float) -> bool:
        nonlocal wait_calls
        wait_calls += 1
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        if wait_calls == 1:
            raise TimeoutError
        return True

    with (
        patch("app.core.lifespan.random.uniform", return_value=0.0),
        patch("app.core.lifespan.asyncio.wait_for", side_effect=wait_for),
        patch("app.tasks.cleanups.cleanup_stories_task", cleanup),
        patch("app.tasks.cleanups.cleanup_password_reset_tokens_task", cleanup),
        patch("app.tasks.cleanups.cleanup_email_change_tokens_task", cleanup),
        patch("app.tasks.cleanups.cleanup_mfa_challenges_task", cleanup),
        patch("app.tasks.cleanups.cleanup_sessions_task", cleanup),
        patch("app.tasks.cleanups.cleanup_notifications_task", cleanup),
        patch("app.tasks.cleanups.cleanup_dead_letter_jobs_task", cleanup),
        patch("app.tasks.cleanups.cleanup_privacy_artifacts_task", cleanup),
        patch("app.tasks.cleanups.manage_partitions_task", cleanup),
    ):
        await _periodic_scheduler_loop()

    assert wait_calls == 2
