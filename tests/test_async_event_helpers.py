"""Lifecycle contracts for task-aware readiness waits."""

import asyncio

import pytest

from tests.helpers.async_events import wait_for_task_event


@pytest.mark.asyncio
async def test_event_wait_rejects_success_before_signal_without_leaking_tasks() -> None:
    before = asyncio.all_tasks()

    async def finish() -> None:
        return None

    task = asyncio.create_task(finish())
    try:
        with pytest.raises(
            AssertionError, match="operation finished before signalling its event"
        ):
            await wait_for_task_event(task, asyncio.Event())
    finally:
        await asyncio.gather(task, return_exceptions=True)

    assert asyncio.all_tasks() - before == set()


@pytest.mark.asyncio
async def test_event_wait_propagates_failure_before_signal_without_leaking_tasks() -> (
    None
):
    before = asyncio.all_tasks()

    async def fail() -> None:
        raise ValueError("operation failed")

    task = asyncio.create_task(fail())
    try:
        with pytest.raises(ValueError, match="operation failed"):
            await wait_for_task_event(task, asyncio.Event())
    finally:
        await asyncio.gather(task, return_exceptions=True)

    assert asyncio.all_tasks() - before == set()


@pytest.mark.asyncio
async def test_event_wait_returns_before_operation_finishes_without_leaking_tasks() -> (
    None
):
    before = asyncio.all_tasks()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def operation() -> str:
        entered.set()
        await release.wait()
        return "finished"

    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(operation())
        try:
            await wait_for_task_event(task, entered)
            assert not task.done()
        finally:
            release.set()

    assert task.result() == "finished"
    assert asyncio.all_tasks() - before == set()


@pytest.mark.asyncio
async def test_cancelling_event_wait_cleans_waiter_without_cancelling_operation() -> (
    None
):
    before = asyncio.all_tasks()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def operation() -> None:
        entered.set()
        await release.wait()

    async with asyncio.TaskGroup() as tasks:
        task = tasks.create_task(operation())
        waiter = tasks.create_task(wait_for_task_event(task, asyncio.Event()))
        try:
            await wait_for_task_event(task, entered)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert not task.done()
            assert asyncio.all_tasks() - before == {task}
        finally:
            release.set()

    assert asyncio.all_tasks() - before == set()
