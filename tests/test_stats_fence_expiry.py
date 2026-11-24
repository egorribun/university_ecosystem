from __future__ import annotations

import asyncio

import pytest

from app.deps import cache as cache_module
from app.services import stats_cache
from tests.test_stats_summary_fence import KINDS, components, summary


@pytest.mark.asyncio
async def test_expired_reservations_never_publish_late_snapshot(monkeypatch):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    clock = [1_000_000.0]
    monkeypatch.setattr(cache_module.time_module, "time", lambda: clock[0])
    repo.pause = "after"
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        assert len(fence.reserve_calls) == 3
        assert all(ttl <= 30 for _, _, ttl in fence.reserve_calls)
        clock[0] += 31
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        assert result["grades"]["average"] == 3.0
        assert len(fence.complete_calls) == 3
        entries = [
            await stats_cache.get_cached_stats(
                cache=cache, kind=kind, user_id=user_id, period_key="30d"
            )
            for kind in KINDS
        ]
        assert all(entry is None for entry in entries)
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)
