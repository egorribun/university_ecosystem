"""Unit tests for the in-memory rate-limit cleanup loop (app/core/ratelimit/cleanup.py).

Hermetic — drives the background prune loop deterministically by monkeypatching
``asyncio.sleep`` (return once, then raise CancelledError to break the ``while True``)
and seeding the shared ``_memory_windows`` dict directly. Module-global ``_cleanup_task``
is reset around every test to avoid cross-test bleed.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

import pytest

from app.core.ratelimit import cleanup
from app.core.ratelimit.strategies import memory


@pytest.fixture(autouse=True)
def _reset_cleanup_state():
    memory._memory_windows.clear()
    cleanup._cleanup_task = None
    yield
    task = cleanup._cleanup_task
    if task is not None and not task.done():
        task.cancel()
    cleanup._cleanup_task = None
    memory._memory_windows.clear()


def _sleep_then_cancel(n_before_cancel: int = 1):
    """Return an async sleep stub that yields ``n`` times, then raises CancelledError."""
    calls = {"n": 0}

    async def _fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] > n_before_cancel:
            raise asyncio.CancelledError()

    return _fake_sleep


@pytest.mark.asyncio
async def test_cleanup_loop_prunes_old_keeps_recent_skips_empty(monkeypatch):
    now = time.time()
    memory._memory_windows["old"] = deque([now - 7200.0])  # < cutoff (now - 3600)
    memory._memory_windows["recent"] = deque([now - 5.0])  # within window
    memory._memory_windows["empty"] = deque()  # falsy → `if not window: continue`

    monkeypatch.setattr(cleanup.asyncio, "sleep", _sleep_then_cancel())

    await cleanup._memory_cleanup_loop(interval_seconds=1)

    assert "old" not in memory._memory_windows  # pruned to empty → popped
    assert "recent" in memory._memory_windows  # retained
    assert "empty" in memory._memory_windows  # continue branch left it untouched


@pytest.mark.asyncio
async def test_cleanup_loop_swallows_unexpected_errors(monkeypatch):
    """A raise inside the prune body is logged and the loop survives (handler-nak)."""
    memory._memory_windows["k"] = deque([time.time()])

    def _boom(_key):
        raise RuntimeError("shard lock failure")

    monkeypatch.setattr(cleanup, "_shard_lock", _boom)
    monkeypatch.setattr(cleanup.asyncio, "sleep", _sleep_then_cancel())

    # Must not propagate — `except Exception` logs and the loop continues to the
    # next sleep, which raises CancelledError and breaks cleanly.
    await cleanup._memory_cleanup_loop(interval_seconds=1)


@pytest.mark.asyncio
async def test_start_then_stop_cleanup_task():
    assert cleanup._cleanup_task is None

    cleanup.start_memory_cleanup_task(interval_seconds=300)
    task = cleanup._cleanup_task
    assert task is not None
    assert not task.done()

    # Idempotent: a second start returns the same (still-running) task.
    cleanup.start_memory_cleanup_task(interval_seconds=300)
    assert cleanup._cleanup_task is task

    await cleanup.stop_memory_cleanup_task()
    assert cleanup._cleanup_task is None


@pytest.mark.asyncio
async def test_stop_cleanup_task_when_none_is_noop():
    cleanup._cleanup_task = None
    await cleanup.stop_memory_cleanup_task()  # early return, no error
    assert cleanup._cleanup_task is None


@pytest.mark.asyncio
async def test_start_cleanup_task_without_running_loop_is_swallowed(monkeypatch):
    cleanup._cleanup_task = None

    def _no_loop():
        raise RuntimeError("no running event loop")

    monkeypatch.setattr(cleanup.asyncio, "get_running_loop", _no_loop)
    cleanup.start_memory_cleanup_task(interval_seconds=1)  # RuntimeError swallowed
    assert cleanup._cleanup_task is None
