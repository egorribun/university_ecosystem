from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from app.services import partition_manager as manager


@pytest.mark.asyncio
async def test_scheduler_survives_database_error_waits_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first_sleep_started = asyncio.Event()
    second_sleep_started = asyncio.Event()
    release_first_sleep = asyncio.Event()
    release_second_sleep = asyncio.Event()
    sleep_events = (first_sleep_started, second_sleep_started)
    release_events = (release_first_sleep, release_second_sleep)
    delays: list[float] = []

    async def controlled_sleep(delay: float) -> None:
        index = len(delays)
        delays.append(delay)
        sleep_events[index].set()
        await release_events[index].wait()

    monkeypatch.setattr(
        manager,
        "asyncio",
        SimpleNamespace(CancelledError=asyncio.CancelledError, sleep=controlled_sleep),
    )

    attempts = 0
    recovered = asyncio.Event()

    async def ensure() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(
                "SELECT secret_connection_details",
                {},
                RuntimeError("synthetic-private-error-detail"),
            )
        recovered.set()

    monkeypatch.setattr(manager, "ensure_partitions_exist", ensure)
    caplog.set_level(logging.ERROR)

    stop = await manager.start_partition_management_scheduler(interval_seconds=7)
    try:
        await asyncio.wait_for(first_sleep_started.wait(), timeout=1)
        assert attempts == 1
        assert delays == [7]
        assert "OperationalError" in caplog.text
        assert "synthetic-private-error-detail" not in caplog.text
        assert "secret_connection_details" not in caplog.text

        release_first_sleep.set()
        await asyncio.wait_for(recovered.wait(), timeout=1)
        await asyncio.wait_for(second_sleep_started.wait(), timeout=1)
        assert attempts == 2
        assert delays == [7, 7]
    finally:
        await asyncio.wait_for(stop(), timeout=1)

    assert attempts == 2


@pytest.mark.asyncio
async def test_scheduler_stops_when_shutdown_cancels_partition_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_started = asyncio.Event()
    never_complete = asyncio.Event()

    async def blocked_ensure() -> None:
        work_started.set()
        await never_complete.wait()

    monkeypatch.setattr(manager, "ensure_partitions_exist", blocked_ensure)
    stop = await manager.start_partition_management_scheduler(interval_seconds=60)

    await asyncio.wait_for(work_started.wait(), timeout=1)
    await asyncio.wait_for(stop(), timeout=1)


@pytest.mark.asyncio
async def test_scheduler_keeps_missing_rust_extension_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_holder: dict[str, asyncio.Task[None]] = {}

    class CapturingRegistry:
        def create_task(
            self,
            coro: Coroutine[Any, Any, None],
            *,
            name: str,
        ) -> asyncio.Task[None]:
            task = asyncio.create_task(coro, name=name)
            task_holder["task"] = task
            return task

        async def shutdown(self, *, timeout: float = 30.0) -> None:
            task = task_holder.get("task")
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    monkeypatch.setattr("app.core.task_registry.TaskRegistry", CapturingRegistry)

    async def missing_extension() -> None:
        raise ImportError("rust_ext is unavailable")

    monkeypatch.setattr(manager, "ensure_partitions_exist", missing_extension)
    stop = await manager.start_partition_management_scheduler(interval_seconds=7)

    with pytest.raises(ImportError, match="rust_ext is unavailable"):
        await task_holder["task"]
    await stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("interval_seconds", [0, -1])
async def test_scheduler_rejects_nonpositive_interval(
    interval_seconds: int,
) -> None:
    with pytest.raises(ValueError, match="interval_seconds must be greater than zero"):
        await manager.start_partition_management_scheduler(interval_seconds)
