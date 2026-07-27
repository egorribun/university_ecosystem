"""Closure tests for successful completion and timeout shutdown paths."""

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
