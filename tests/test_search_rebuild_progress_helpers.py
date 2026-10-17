"""The progress observer completes and drains its tasks on every outcome."""

import asyncio

import pytest

from tests.helpers.search_rebuild import RebuildProgress


@pytest.mark.asyncio
async def test_rebuild_progress_returns_early_success_without_waiting_for_duplicate():
    before = asyncio.all_tasks()
    progress = RebuildProgress()

    async def empty_rebuild():
        return {"news": 0, "events": 0}

    assert await progress.complete(empty_rebuild()) == {"news": 0, "events": 0}
    assert not (asyncio.all_tasks() - before)


@pytest.mark.asyncio
async def test_rebuild_progress_propagates_worker_error_and_drains_waiter():
    before = asyncio.all_tasks()
    progress = RebuildProgress()

    async def failed_rebuild():
        raise ValueError("search transport failed")

    with pytest.raises(ValueError, match="search transport failed"):
        await progress.complete(failed_rebuild())
    assert not (asyncio.all_tasks() - before)


@pytest.mark.asyncio
async def test_rebuild_progress_rejects_duplicate_and_finishes_worker_cleanup():
    before = asyncio.all_tasks()
    progress = RebuildProgress()
    closed = asyncio.Event()

    async def repeated_rebuild():
        try:
            await progress.record("news-rebuild", [{"id": "first"}])
            await progress.record("news-rebuild", [{"id": "first"}])
        finally:
            closed.set()

    with pytest.raises(AssertionError, match="delivered a document more than once"):
        await progress.complete(repeated_rebuild())
    assert closed.is_set()
    assert not (asyncio.all_tasks() - before)


@pytest.mark.asyncio
async def test_cancelled_rebuild_progress_drains_worker_and_event_waiter():
    before = asyncio.all_tasks()
    progress = RebuildProgress()
    entered = asyncio.Event()
    release = asyncio.Event()
    closed = asyncio.Event()

    async def blocked_rebuild():
        try:
            entered.set()
            await release.wait()
        finally:
            closed.set()

    async with asyncio.TaskGroup() as tasks:
        observing = tasks.create_task(progress.complete(blocked_rebuild()))
        await entered.wait()
        observing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await observing
    assert closed.is_set()
    assert not (asyncio.all_tasks() - before)


@pytest.mark.asyncio
async def test_rebuild_progress_accepts_same_id_in_different_indices():
    before = asyncio.all_tasks()
    progress = RebuildProgress()

    async def rebuild():
        await progress.record("news-rebuild", [{"id": "shared"}])
        await progress.record("events-rebuild", [{"id": "shared"}])
        return {"news": 1, "events": 1}

    assert await progress.complete(rebuild()) == {"news": 1, "events": 1}
    assert progress.deliveries == {
        "news-rebuild": ["shared"],
        "events-rebuild": ["shared"],
    }
    assert not (asyncio.all_tasks() - before)
