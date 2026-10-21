"""Closure tests for successful completion and timeout shutdown paths."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.core.task_registry import TaskRegistry


def test_on_done_discards_successful_task_without_logging():
    registry = TaskRegistry()
    task = MagicMock()
    task.cancelled.return_value = False
    task.exception.return_value = None
    registry._tasks.add(task)

    registry._on_done(task)

    assert task not in registry._tasks


@pytest.mark.asyncio
async def test_create_task_tracks_and_removes_successful_task():
    registry = TaskRegistry()

    async def work() -> str:
        return "done"

    task = registry.create_task(work(), name="closure-success")
    assert await task == "done"
    await asyncio.sleep(0)

    assert task not in registry._tasks


@pytest.mark.asyncio
async def test_failed_task_is_logged_by_done_callback():
    registry = TaskRegistry()

    async def fail() -> None:
        raise RuntimeError("background failure")

    with patch("app.core.task_registry._logger.error") as error:
        task = registry.create_task(fail(), name="closure-failure")
        with pytest.raises(RuntimeError, match="background failure"):
            await task
        await asyncio.sleep(0)

    error.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_task_is_removed_without_error_logging():
    registry = TaskRegistry()
    gate = asyncio.Event()

    async def wait_forever() -> None:
        await gate.wait()

    with patch("app.core.task_registry._logger.error") as error:
        task = registry.create_task(wait_forever(), name="closure-cancel")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    error.assert_not_called()
    assert task not in registry._tasks


@pytest.mark.asyncio
async def test_shutdown_returns_immediately_for_empty_registry():
    await TaskRegistry().shutdown()


@pytest.mark.asyncio
async def test_shutdown_deadline_keeps_cancellation_resistant_task_tracked():
    registry = TaskRegistry()
    started = asyncio.Event()
    cancel_seen = asyncio.Event()
    release = asyncio.Event()
    callback_finished = asyncio.Event()

    async def cancellation_resistant() -> None:
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancel_seen.set()

    child = registry.create_task(cancellation_resistant(), name="deadline-resistant")
    # The registry callback was registered first; this signal follows its cleanup.
    child.add_done_callback(lambda _task: callback_finished.set())
    shutdown_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
        shutdown_task = asyncio.create_task(registry.shutdown(timeout=0.05))
        await asyncio.wait_for(cancel_seen.wait(), timeout=1.0)

        done, _ = await asyncio.wait({shutdown_task}, timeout=0.5)
        assert shutdown_task in done, "shutdown exceeded its configured deadline"
        await shutdown_task
        assert not child.done(), "the test task must still resist cancellation"
        assert child in registry._tasks, "pending tasks must remain tracked"
    finally:
        release.set()
        tasks = {child}
        if shutdown_task is not None:
            tasks.add(shutdown_task)
        _, pending = await asyncio.wait(tasks, timeout=1.0)
        if pending:
            for task in pending:
                task.cancel()
            _, pending = await asyncio.wait(pending, timeout=1.0)
        assert not pending, "test cleanup left a real task pending"
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.wait_for(callback_finished.wait(), timeout=1.0)
        assert child not in registry._tasks
