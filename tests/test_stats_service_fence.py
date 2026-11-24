from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import settings
from app.deps import cache as cache_module
from app.deps.cache import MemoryCache, NullCache
from app.services import cache_warmup, stats_cache
from app.services.user import analytics_service as analytics_module
from app.services.user.analytics_service import UserAnalyticsService


class SnapshotRepository:
    def __init__(self):
        self.score = 3.0
        self.date = datetime.now(UTC) - timedelta(days=1)
        self.calls = 0
        self.pause = False
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()

    async def get_grades(self, *_args):
        self.calls += 1
        snapshot = SimpleNamespace(
            created_at=self.date, subject="Synthetic", score=self.score
        )
        if self.pause and self.calls == 1:
            self.entered.set()
            await asyncio.wait_for(self.resume.wait(), 5)
        return [snapshot]

    async def get_attendance_stats_raw(self, *_args):
        return []

    async def get_participation_stats_raw(self, *_args, **_kwargs):
        return []


def components():
    cache = MemoryCache(default_ttl=300)
    repo = SnapshotRepository()
    service = UserAnalyticsService(None)
    service.stats_repo = repo
    return service, cache, repo, uuid4()


async def grade(service, cache, user_id, *, skip=False, period="30d"):
    return await service.get_grade_stats(
        user_id=user_id, period_days=30, period_key=period, cache=cache, skip_cache=skip
    )


def grade_key(user_id, period="30d"):
    return stats_cache.make_stats_cache_key("grades", user_id, period)


@pytest.mark.asyncio
async def test_single_section_fill_hit_ttl_and_bypass(monkeypatch):
    service, cache, repo, user_id = components()
    monkeypatch.setattr(settings, "stats_cache_ttl_seconds", 180)
    first = await grade(service, cache, user_id)
    entry = await cache.get(grade_key(user_id))
    assert first["average"] == 3.0 and entry.ttl_seconds == 180.0
    repo.score = 5.0
    assert (await grade(service, cache, user_id))["average"] == 3.0
    assert repo.calls == 1
    assert (await grade(service, cache, user_id, skip=True))["average"] == 5.0
    after = await cache.get(grade_key(user_id))
    assert (after.payload, after.stored_at) == (entry.payload, entry.stored_at)
    assert repo.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("peer", ["delete_only", "set_only", "delete_and_set"])
async def test_single_section_cannot_overwrite_peer_after_snapshot(peer):
    service, cache, repo, user_id = components()
    repo.pause = True
    task = asyncio.create_task(grade(service, cache, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        marker = await cache.get(grade_key(user_id))
        assert isinstance(marker.payload, str) and marker.payload.startswith(
            "~stats-fill-v1:"
        )
        repo.score = 5.0
        if peer != "set_only":
            await stats_cache.invalidate_user_stats_cache(
                user_ids=[user_id], kinds=("grades",), period_keys=("30d",), cache=cache
            )
        if peer != "delete_only":
            await stats_cache.set_cached_stats(
                cache=cache,
                kind="grades",
                user_id=user_id,
                period_key="30d",
                payload={"average": 5.0},
            )
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        entry = await cache.get(grade_key(user_id))
        if peer == "delete_only":
            assert result["average"] == 3.0 and entry is None
            assert (await grade(service, cache, user_id))["average"] == 5.0
        else:
            assert result["average"] == 5.0 and entry.payload["average"] == 5.0
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_warmup_uses_guarded_service_and_preserves_peer(monkeypatch):
    _service, cache, repo, user_id = components()
    repo.pause = True
    monkeypatch.setattr(analytics_module, "UserStatsRepository", lambda _db: repo)
    task = asyncio.create_task(
        cache_warmup._warm_stats_for_user(cache, None, user_id, "30d")
    )
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        marker = await cache.get(grade_key(user_id))
        assert isinstance(marker.payload, str) and marker.payload.startswith(
            "~stats-fill-v1:"
        )
        repo.score = 5.0
        await stats_cache.invalidate_user_stats_cache(
            user_ids=[user_id], kinds=("grades",), period_keys=("30d",), cache=cache
        )
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="grades",
            user_id=user_id,
            period_key="30d",
            payload={"average": 5.0},
        )
        repo.resume.set()
        await asyncio.wait_for(task, 2)
        assert (await cache.get(grade_key(user_id))).payload["average"] == 5.0
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_reservation_expiry_does_not_publish_snapshot(monkeypatch):
    service, cache, repo, user_id = components()
    clock = [1_000_000.0]
    monkeypatch.setattr(cache_module.time_module, "time", lambda: clock[0])
    repo.pause = True
    task = asyncio.create_task(grade(service, cache, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        assert isinstance((await cache.get(grade_key(user_id))).payload, str)
        clock[0] += 31
        repo.resume.set()
        assert (await asyncio.wait_for(task, 2))["average"] == 3.0
        assert await cache.get(grade_key(user_id)) is None
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved", [None, False])
async def test_unavailable_reservation_never_falls_back_to_unconditional_set(
    monkeypatch, reserved
):
    service, cache, repo, user_id = components()

    class UnknownFence:
        def __init__(self, _cache):
            pass

        async def reserve(self, *_args):
            return reserved

        async def complete(self, *_args):
            raise AssertionError("no ownership")

    monkeypatch.setattr(analytics_module, "StatsFillFence", UnknownFence, raising=False)
    assert (await grade(service, cache, user_id))["average"] == 3.0
    assert repo.calls == 1
    assert await cache.get(grade_key(user_id)) is None


@pytest.mark.asyncio
async def test_peer_completes_between_failed_reserve_and_cache_recheck(monkeypatch):
    from app.services.stats_fill_fence import StatsFillFence

    service, cache, repo, user_id = components()
    fence = StatsFillFence(cache)
    key = grade_key(user_id)
    peer_token = "b" * 32
    assert await fence.reserve(key, peer_token, 10) is True

    class PeerCompletes:
        async def reserve(self, key, token, ttl):
            assert await fence.reserve(key, token, ttl) is False
            assert await fence.complete(key, peer_token, {"average": 5.0}, 60) is True
            return False

        async def complete(self, *_args):
            raise AssertionError("reader did not acquire ownership")

    monkeypatch.setattr(
        analytics_module, "StatsFillFence", lambda _cache: PeerCompletes()
    )
    assert (await grade(service, cache, user_id))["average"] == 5.0
    assert repo.calls == 0
    assert (await cache.get(key)).payload == {"average": 5.0}


@pytest.mark.asyncio
async def test_skip_and_disabled_cache_do_not_create_fence(monkeypatch):
    service, cache, _repo, user_id = components()

    def forbidden(_cache):
        raise AssertionError("fence should not be constructed")

    monkeypatch.setattr(analytics_module, "StatsFillFence", forbidden, raising=False)
    assert (await grade(service, cache, user_id, skip=True))["average"] == 3.0
    assert (await grade(service, NullCache(), user_id))["average"] == 3.0

    def forbidden_global():
        raise AssertionError("bypass should not resolve the global cache")

    monkeypatch.setattr(analytics_module, "get_cache", forbidden_global)
    monkeypatch.setattr(stats_cache, "get_cache", lambda: cache)
    assert (await grade(service, None, user_id, skip=True))["average"] == 3.0


@pytest.mark.asyncio
async def test_none_cache_uses_same_global_backend(monkeypatch):
    service, cache, repo, user_id = components()
    monkeypatch.setattr(stats_cache, "get_cache", lambda: cache)
    monkeypatch.setattr(analytics_module, "get_cache", lambda: cache)
    assert (await grade(service, None, user_id))["average"] == 3.0
    assert (await grade(service, None, user_id))["average"] == 3.0
    assert repo.calls == 1
    assert (await cache.get(grade_key(user_id))).payload["average"] == 3.0
