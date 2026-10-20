from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.lifespan import _start_quarantine_retention_worker


@pytest.mark.asyncio
async def test_quarantine_worker_is_owned_by_lifespan_and_cancellable() -> None:
    started = asyncio.Event()
    never_finish = asyncio.Event()

    class Service:
        async def sweep_once(self, *, limit: int = 100) -> int:
            del limit
            started.set()
            await never_finish.wait()
            return 0

    app = SimpleNamespace(state=SimpleNamespace(background_tasks=set()))
    task = _start_quarantine_retention_worker(
        app, service=Service(), interval_seconds=30
    )
    assert task in app.state.background_tasks
    await asyncio.wait_for(started.wait(), timeout=2)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.done()


@pytest.mark.asyncio
async def test_quarantine_worker_retries_after_a_bounded_sweep_failure() -> None:
    second_attempt = asyncio.Event()
    never_finish = asyncio.Event()

    class Service:
        attempts = 0

        async def sweep_once(self, *, limit: int = 100) -> int:
            del limit
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("synthetic storage outage")
            second_attempt.set()
            await never_finish.wait()
            return 0

    app = SimpleNamespace(state=SimpleNamespace(background_tasks=set()))
    service = Service()
    task = _start_quarantine_retention_worker(
        app, service=service, interval_seconds=0.001
    )
    try:
        await asyncio.wait_for(second_attempt.wait(), timeout=2)
        assert service.attempts == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert task.done()
