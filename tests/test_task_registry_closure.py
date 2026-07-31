"""Closure tests for successful completion and timeout shutdown paths."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_shutdown_logs_and_clears_tasks_after_timeout():
    registry = TaskRegistry()
    task = MagicMock()
    registry._tasks.add(task)

    with (
        patch("app.core.task_registry.asyncio.gather", return_value=object()),
        patch(
            "app.core.task_registry.asyncio.wait_for",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ) as wait_for,
    ):
        await registry.shutdown(timeout=0.1)

    task.cancel.assert_called_once()
    wait_for.assert_awaited_once()
    assert not registry._tasks
