from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api import stats
from app.cqrs.queries import GetStatsHandler, GetStatsQuery, StatsFillFenceProtocol
from app.deps.cache import MemoryCache
from app.services import stats_cache
from app.services.stats_fill_fence import StatsFillFence
from app.services.user.analytics_service import UserAnalyticsService

KINDS = ("attendance", "grades", "participation")


class SnapshotRepository:
    """Deterministic source seam; barrier models statement snapshot boundaries."""

    def __init__(self):
        self.score = 3.0
        self.date = datetime.now(UTC) - timedelta(days=1)
        self.requested = []
        self.individual = []
        self.pause = None
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.fail_on_kind = None
        self.second_error = None

    def grade(self):
        return SimpleNamespace(
            created_at=self.date, subject="Synthetic", score=self.score
        )

    async def get_attendance_stats_raw(self, *_args):
        self.individual.append("attendance")
        return []

    async def get_grades(self, *_args):
        self.individual.append("grades")
        return [self.grade()]

    async def get_participation_stats_raw(self, *_args, **_kwargs):
        self.individual.append("participation")
        return []

    async def get_summary_rows(self, *_args, kinds, **_kwargs):
        self.requested.append(frozenset(kinds))
        if len(self.requested) == 2 and self.second_error is not None:
            raise self.second_error
        if self.fail_on_kind in kinds:
            raise RuntimeError("synthetic hot branch failure")
        if self.pause == "before" and len(self.requested) == 1:
            self.entered.set()
            await asyncio.wait_for(self.resume.wait(), 5)
        snap_grade = self.grade()
        if self.pause == "after" and len(self.requested) == 1:
            self.entered.set()
            await asyncio.wait_for(self.resume.wait(), 5)
        return SimpleNamespace(attendance=[], grades=[snap_grade], participation=[])


class ObservedFence:
    supported = True

    def __init__(self, cache):
        self.backend = StatsFillFence(cache)
        self.reserve_calls = []
        self.complete_calls = []
        self.reserve_result = True
        self.complete_result = True

    async def reserve(self, key, token, ttl):
        self.reserve_calls.append((key, token, ttl))
        if self.reserve_result is not True:
            return self.reserve_result
        return await self.backend.reserve(key, token, ttl)

    async def complete(self, key, token, payload, ttl):
        self.complete_calls.append((key, token, ttl))
        if self.complete_result is not True:
            return self.complete_result
        return await self.backend.complete(key, token, payload, ttl)


def query(user_id, kind):
    return GetStatsQuery(
        kind=kind,
        user_id=user_id,
        period_key="30d",
        period_days=30,
        locale="en",
        if_none_match=None,
        skip_cache=False,
    )


def components(monkeypatch):
    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = MemoryCache(default_ttl=300)
    repo = SnapshotRepository()
    analytics = UserAnalyticsService(None)
    analytics.stats_repo = repo
    fence = ObservedFence(cache)
    return (
        GetStatsHandler(None, cache, analytics, fill_fence=fence),
        cache,
        repo,
        fence,
        uuid4(),
    )


async def summary(handler, user_id, *, skip=False):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/stats/summary",
            "query_string": b"",
            "headers": [],
        }
    )

    class Container:
        async def get(self, *_args, **_kwargs):
            return handler

    request.state.dishka_container = Container()
    return await stats.stats_summary(
        request=request,
        response=Response(),
        period="30d",
        skip_cache=skip,
        if_none_match=None,
        user=SimpleNamespace(id=user_id),
    )


async def invalidate_grades(cache, user_id):
    await stats_cache.invalidate_user_stats_cache(
        user_ids=[user_id], kinds=("grades",), period_keys=("30d",), cache=cache
    )


def key(user_id, kind):
    return stats_cache.make_stats_cache_key(kind, user_id, "30d")


@pytest.mark.asyncio
@pytest.mark.parametrize(("phase", "expected"), [("before", 5.0), ("after", 5.0)])
async def test_initial_hot_delete_uses_one_later_read_without_rewrite(
    monkeypatch, phase, expected
):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    assert (await handler.handle(query(user_id, "grades"))).payload["average"] == 3.0
    repo.pause = phase
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        await invalidate_grades(cache, user_id)
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        assert result["grades"]["average"] == expected
        assert await cache.get(key(user_id, "grades")) is None
        assert repo.requested == [
            frozenset({"attendance", "participation"}),
            frozenset({"grades"}),
        ]
        assert {k for k, _, _ in fence.reserve_calls} == {
            key(user_id, "attendance"),
            key(user_id, "participation"),
        }
        assert {k for k, _, _ in fence.complete_calls} == {
            key(user_id, "attendance"),
            key(user_id, "participation"),
        }
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_hot_replacement_after_snapshot_is_not_overwritten(monkeypatch):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    await handler.handle(query(user_id, "grades"))
    repo.pause = "after"
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        await invalidate_grades(cache, user_id)
        assert (await handler.handle(query(user_id, "grades"))).payload[
            "average"
        ] == 5.0
        replacement = await cache.get(key(user_id, "grades"))
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        current = await cache.get(key(user_id, "grades"))
        assert result["grades"]["average"] == 5.0
        assert repo.requested == [frozenset({"attendance", "participation"})]
        assert (current.payload, current.stored_at) == (
            replacement.payload,
            replacement.stored_at,
        )
        assert key(user_id, "grades") not in {k for k, _, _ in fence.complete_calls}
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_first", [False, True])
async def test_cold_legacy_peer_displaces_reservation(monkeypatch, delete_first):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    repo.pause = "after"
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        if delete_first:
            await invalidate_grades(cache, user_id)
        # A rolling old worker still uses the original unconditional setter.
        payload = await handler.analytics_service.get_grade_stats(
            user_id=user_id,
            period_days=30,
            period_key="30d",
            cache=cache,
            skip_cache=True,
        )
        assert payload["average"] == 5.0
        await cache.set(
            stats_cache.make_stats_cache_key("grades", user_id, "30d"),
            payload,
        )
        peer = await cache.get(key(user_id, "grades"))
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        current = await cache.get(key(user_id, "grades"))
        assert result["grades"]["average"] == 5.0
        assert (current.payload, current.stored_at) == (peer.payload, peer.stored_at)
        assert key(user_id, "grades") in {k for k, _, _ in fence.reserve_calls}
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_guarded_peer_requires_invalidation_to_supersede_reservation(monkeypatch):
    handler, cache, repo, _fence, user_id = components(monkeypatch)
    repo.pause = "after"
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        peer = await handler.handle(query(user_id, "grades"))
        assert peer.payload["average"] == 5.0
        assert isinstance((await cache.get(key(user_id, "grades"))).payload, str)
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        assert result["grades"]["average"] == 3.0
        assert (await cache.get(key(user_id, "grades"))).payload["average"] == 3.0
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("mask", range(8))
async def test_eight_masks_only_reserve_and_select_initially_cold(monkeypatch, mask):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    hot = {kind for i, kind in enumerate(KINDS) if mask & (1 << i)}
    for kind in hot:
        await handler.handle(query(user_id, kind))
    before = {kind: await cache.get(key(user_id, kind)) for kind in hot}
    await summary(handler, user_id)
    assert repo.requested == ([] if mask == 7 else [frozenset(set(KINDS) - hot)])
    assert {k for k, _, _ in fence.reserve_calls} == {
        key(user_id, kind) for kind in set(KINDS) - hot
    }
    assert {k for k, _, _ in fence.complete_calls} == {
        key(user_id, kind) for kind in set(KINDS) - hot
    }
    for kind, entry in before.items():
        current = await cache.get(key(user_id, kind))
        assert (current.payload, current.stored_at) == (entry.payload, entry.stored_at)


@pytest.mark.asyncio
async def test_bypass_never_reserves_or_writes_cache(monkeypatch):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    repo.score = 5.0
    await handler.handle(query(user_id, "grades"))
    initial = await cache.get(key(user_id, "grades"))
    repo.score = 3.0
    result = await summary(handler, user_id, skip=True)
    assert result["grades"]["average"] == 3.0
    assert repo.requested == [frozenset(KINDS)]
    assert not fence.reserve_calls and not fence.complete_calls
    after = await cache.get(key(user_id, "grades"))
    assert (after.payload, after.stored_at) == (initial.payload, initial.stored_at)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["reserve", "complete"])
async def test_unknown_fence_never_unconditionally_fills(monkeypatch, fault):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    setattr(fence, f"{fault}_result", None)
    result = await summary(handler, user_id)
    assert result["grades"]["average"] == 3.0
    entry = await stats_cache.get_cached_stats(
        cache=cache, kind="grades", user_id=user_id, period_key="30d"
    )
    assert entry is None
    assert repo.requested == [frozenset(KINDS)]


@pytest.mark.asyncio
async def test_stable_hot_branch_is_not_read_or_failed(monkeypatch):
    handler, _cache, repo, _fence, user_id = components(monkeypatch)
    await handler.handle(query(user_id, "grades"))
    repo.fail_on_kind = "grades"
    result = await summary(handler, user_id)
    assert result["grades"]["average"] == 3.0
    assert repo.requested == [frozenset({"attendance", "participation"})]


@pytest.mark.asyncio
async def test_sqlite_summary_uses_one_then_zero_data_statements(
    db_session, monkeypatch
):
    from sqlalchemy import event

    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = MemoryCache(default_ttl=300)
    handler = GetStatsHandler(
        db_session,
        cache,
        UserAnalyticsService(db_session),
        fill_fence=StatsFillFence(cache),
    )
    engine = db_session.bind.sync_engine
    statements = 0

    def count_statement(*_args, **_kwargs):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        user_id = uuid4()
        cold = await summary(handler, user_id)
        assert statements == 1
        statements = 0
        assert await summary(handler, user_id) == cold
        assert statements == 0
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)


@pytest.mark.asyncio
async def test_two_disappeared_hot_sections_share_one_second_read(monkeypatch):
    handler, cache, repo, fence, user_id = components(monkeypatch)
    await handler.handle(query(user_id, "grades"))
    await handler.handle(query(user_id, "participation"))
    repo.pause = "after"
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        await stats_cache.invalidate_user_stats_cache(
            user_ids=[user_id],
            kinds=("grades", "participation"),
            period_keys=("30d",),
            cache=cache,
        )
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        assert result["grades"]["average"] == 5.0
        assert repo.requested == [
            frozenset({"attendance"}),
            frozenset({"grades", "participation"}),
        ]
        assert await cache.get(key(user_id, "grades")) is None
        assert await cache.get(key(user_id, "participation")) is None
        assert {k for k, _, _ in fence.complete_calls} == {key(user_id, "attendance")}
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_second_read_database_error_propagates_without_hot_write(
    monkeypatch,
):
    from sqlalchemy.exc import SQLAlchemyError

    handler, cache, repo, _fence, user_id = components(monkeypatch)
    await handler.handle(query(user_id, "grades"))
    repo.pause = "after"
    repo.second_error = SQLAlchemyError("synthetic second read failure")
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        await invalidate_grades(cache, user_id)
        repo.resume.set()
        with pytest.raises(SQLAlchemyError, match="synthetic second read failure"):
            await asyncio.wait_for(task, 2)
        assert repo.requested == [
            frozenset({"attendance", "participation"}),
            frozenset({"grades"}),
        ]
        assert await cache.get(key(user_id, "grades")) is None
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_sqlite_groups_disappeared_hots_into_one_second_data_statement(
    db_session, monkeypatch
):
    from sqlalchemy import event

    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = MemoryCache(default_ttl=300)
    analytics = UserAnalyticsService(db_session)
    handler = GetStatsHandler(
        db_session, cache, analytics, fill_fence=StatsFillFence(cache)
    )
    user_id = uuid4()
    await handler.handle(query(user_id, "grades"))
    await handler.handle(query(user_id, "participation"))

    class GateRepository:
        def __init__(self, inner):
            self.inner = inner
            self.requested = []
            self.entered = asyncio.Event()
            self.resume = asyncio.Event()

        async def get_summary_rows(self, *args, kinds, **kwargs):
            self.requested.append(frozenset(kinds))
            rows = await self.inner.get_summary_rows(*args, kinds=kinds, **kwargs)
            if len(self.requested) == 1:
                self.entered.set()
                await asyncio.wait_for(self.resume.wait(), 5)
            return rows

    gate = GateRepository(analytics.stats_repo)
    analytics.stats_repo = gate
    statements = 0

    def count_statement(*_args, **_kwargs):
        nonlocal statements
        statements += 1

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count_statement)
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(gate.entered.wait(), 2)
        await stats_cache.invalidate_user_stats_cache(
            user_ids=[user_id],
            kinds=("grades", "participation"),
            period_keys=("30d",),
            cache=cache,
        )
        gate.resume.set()
        await asyncio.wait_for(task, 2)
        assert statements == 2
        assert gate.requested == [
            frozenset({"attendance"}),
            frozenset({"grades", "participation"}),
        ]
        assert await cache.get(key(user_id, "grades")) is None
        assert await cache.get(key(user_id, "participation")) is None
    finally:
        gate.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)
        event.remove(engine, "before_cursor_execute", count_statement)


@pytest.mark.asyncio
async def test_direct_handler_builds_fence_and_reuses_populated_cache(monkeypatch):
    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = MemoryCache(default_ttl=300)
    repo = SnapshotRepository()
    analytics = UserAnalyticsService(None)
    analytics.stats_repo = repo
    handler = GetStatsHandler(None, cache, analytics)
    assert isinstance(handler.fill_fence, StatsFillFence)
    assert handler.fill_fence.cache is cache
    user_id = uuid4()
    first = await summary(handler, user_id)
    assert await summary(handler, user_id) == first
    assert repo.requested == [frozenset(KINDS)]


def test_cqrs_provider_constructs_fence_on_same_cache():
    from app.core.di.cqrs import CQRSProvider

    cache = MemoryCache(default_ttl=300)
    handler = CQRSProvider().get_stats_handler(None, cache, object())
    assert isinstance(handler.fill_fence, StatsFillFence)
    assert handler.fill_fence.cache is cache


@pytest.mark.asyncio
async def test_sqlite_second_statement_error_propagates_without_savepoint(
    db_session, monkeypatch
):
    from sqlalchemy import event, func, select
    from sqlalchemy.exc import SQLAlchemyError

    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = MemoryCache(default_ttl=300)
    analytics = UserAnalyticsService(db_session)
    handler = GetStatsHandler(db_session, cache, analytics)
    user_id = uuid4()
    await handler.handle(query(user_id, "grades"))

    class FailingSecondRepository:
        def __init__(self, inner):
            self.inner = inner
            self.calls = 0
            self.entered = asyncio.Event()
            self.resume = asyncio.Event()

        async def get_summary_rows(self, *args, kinds, **kwargs):
            self.calls += 1
            if self.calls == 1:
                rows = await self.inner.get_summary_rows(*args, kinds=kinds, **kwargs)
                self.entered.set()
                await asyncio.wait_for(self.resume.wait(), 5)
                return rows
            await db_session.execute(select(func.r40_synthetic_missing_function()))
            raise AssertionError("expected database error")

    gate = FailingSecondRepository(analytics.stats_repo)
    analytics.stats_repo = gate
    statements = 0

    def count_statement(*_args, **_kwargs):
        nonlocal statements
        statements += 1

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count_statement)
    task = asyncio.create_task(summary(handler, user_id))
    try:
        await asyncio.wait_for(gate.entered.wait(), 2)
        await invalidate_grades(cache, user_id)
        gate.resume.set()
        with pytest.raises(SQLAlchemyError):
            await asyncio.wait_for(task, 2)
        assert statements == 2
        assert await cache.get(key(user_id, "grades")) is None
    finally:
        gate.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)
        event.remove(engine, "before_cursor_execute", count_statement)
        await db_session.rollback()


@pytest.mark.asyncio
async def test_unsupported_adapter_remains_explicitly_unfilled(monkeypatch):
    class UnsupportedMemoryCache(MemoryCache):
        pass

    monkeypatch.setattr(stats, "resolve_locale", lambda **_kwargs: "en")
    cache = UnsupportedMemoryCache(default_ttl=300)
    repo = SnapshotRepository()
    analytics = UserAnalyticsService(None)
    analytics.stats_repo = repo
    handler = GetStatsHandler(None, cache, analytics)
    user_id = uuid4()
    # An entry the fence could not have written is never served either.
    await cache.set(key(user_id, "grades"), {"stale": True})
    assert await summary(handler, user_id) == await summary(handler, user_id)
    assert repo.requested == [frozenset(KINDS), frozenset(KINDS)]
    assert await cache.get(key(user_id, "grades")) is not None
    entries = [await cache.get(key(user_id, kind)) for kind in KINDS[::2]]
    assert all(entry is None for entry in entries)


def scoped_queries(user_id, period_key):
    return tuple(
        GetStatsQuery(
            kind=kind,
            user_id=user_id,
            period_key=period_key,
            period_days=30,
            locale="en",
            if_none_match=None,
            skip_cache=False,
        )
        for kind in KINDS
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("period_key", ["", "   "])
async def test_hot_resolved_period_hit_is_rechecked_on_same_key(
    monkeypatch, period_key
):
    handler, _cache, repo, _fence, user_id = components(monkeypatch)
    await handler.handle(query(user_id, "grades"))
    result = await handler.handle_summary(scoped_queries(user_id, period_key))
    assert result[1].payload["average"] == 3.0
    assert repo.requested == [frozenset({"attendance", "participation"})]


@pytest.mark.asyncio
async def test_outer_default_period_hit_is_not_replaced_by_resolved_hit(monkeypatch):
    handler, cache, repo, _fence, user_id = components(monkeypatch)
    await cache.set(
        stats_cache.make_stats_cache_key("grades", user_id, "default"),
        {"average": 3.0},
    )
    await cache.set(
        stats_cache.make_stats_cache_key("grades", user_id, "30d"),
        {"average": 5.0},
    )
    result = await handler.handle_summary(scoped_queries(user_id, ""))
    assert result[1].payload["average"] == 3.0
    assert repo.requested == [frozenset({"attendance", "participation"})]


@pytest.mark.asyncio
async def test_failed_cold_publish_rereads_reserved_resolved_key(monkeypatch):
    handler, cache, repo, _fence, user_id = components(monkeypatch)
    repo.pause = "after"
    task = asyncio.create_task(handler.handle_summary(scoped_queries(user_id, "")))
    try:
        await asyncio.wait_for(repo.entered.wait(), 2)
        repo.score = 5.0
        payload = await handler.analytics_service.get_grade_stats(
            user_id=user_id,
            period_days=30,
            period_key="30d",
            cache=cache,
            skip_cache=True,
        )
        assert payload["average"] == 5.0
        await cache.set(
            stats_cache.make_stats_cache_key("grades", user_id, "30d"),
            payload,
        )
        repo.resume.set()
        result = await asyncio.wait_for(task, 2)
        assert result[1].payload["average"] == 5.0
        assert repo.requested == [frozenset(KINDS)]
    finally:
        repo.resume.set()
        if not task.done():
            await asyncio.wait_for(task, 2)


def test_public_stats_key_helper_keeps_existing_wire_format():
    user_id = uuid4()
    for period in ("", " 30D ", "7d"):
        assert stats_cache.make_stats_cache_key(" Grades ", user_id, period) == (
            stats_cache.make_stats_cache_key(" Grades ", user_id, period)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_method", ["reserve", "complete"])
async def test_incomplete_fence_cannot_publish_without_confirmation(
    monkeypatch, missing_method
):
    handler, cache, _repo, _fence, user_id = components(monkeypatch)
    actual = StatsFillFence(cache)

    class MissingReserve(StatsFillFenceProtocol):
        async def complete(self, *_args):
            raise AssertionError("unreserved work must not be completed")

    class MissingComplete(StatsFillFenceProtocol):
        async def reserve(self, key, token, ttl):
            return await actual.reserve(key, token, ttl)

    handler.fill_fence = (
        MissingReserve() if missing_method == "reserve" else MissingComplete()
    )
    result = await summary(handler, user_id)
    assert result["grades"]["average"] == 3.0
    for kind in KINDS:
        entry = await cache.get(key(user_id, kind))
        assert entry is None or not isinstance(entry.payload, dict)


@pytest.mark.asyncio
async def test_unexpected_fence_error_propagates(monkeypatch):
    handler, _cache, _repo, _fence, user_id = components(monkeypatch)

    class BrokenFence:
        supported = True

        async def reserve(self, *_args):
            raise RuntimeError("unexpected fence error")

    handler.fill_fence = BrokenFence()
    with pytest.raises(RuntimeError, match="unexpected fence error"):
        await summary(handler, user_id)


@pytest.mark.asyncio
async def test_read_component_uses_fence_bound_to_shared_cache():
    from app.core.di.read_replica import READ_COMPONENT
    from app.core.di_provider import create_dishka_container
    from app.deps.cache import BaseCache

    container = create_dishka_container()
    try:
        cache = await container.get(BaseCache)
        async with container() as request_container:
            handler = await request_container.get(
                GetStatsHandler, component=READ_COMPONENT
            )
            assert handler.cache is cache
            assert isinstance(handler.fill_fence, StatsFillFence)
            assert handler.fill_fence.cache is cache
    finally:
        await container.close()
