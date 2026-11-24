from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api import stats
from app.core.config import settings
from app.cqrs.queries import GetStatsHandler, GetStatsQuery
from app.deps.cache import MemoryCache, NullCache
from app.services import stats_cache
from app.services.user.analytics_service import UserAnalyticsService

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
KINDS = ("attendance", "grades", "participation")


@dataclass(frozen=True)
class SummaryRows:
    attendance: list
    grades: list
    participation: list


class RepositoryStub:
    def __init__(self) -> None:
        start = NOW - timedelta(days=2)
        self.rows = SummaryRows(
            attendance=[
                SimpleNamespace(
                    starts_at=start,
                    title="Synthetic lecture",
                    registered_at=start - timedelta(hours=1),
                    is_registered=True,
                )
            ],
            grades=[
                SimpleNamespace(created_at=start, subject="Synthetic course", score=4.0)
            ],
            participation=[
                SimpleNamespace(
                    title="Synthetic lecture",
                    event_type="lecture",
                    starts_at=start,
                    ends_at=start + timedelta(hours=2),
                )
            ],
        )
        self.batch_calls: list[tuple[UUID | str, frozenset[str]]] = []
        self.individual_calls: list[str] = []
        self.failure = False

    async def get_summary_rows(
        self, user_id, window_start, previous_start, now, *, kinds: Collection[str]
    ):
        self.batch_calls.append((user_id, frozenset(kinds)))
        if self.failure:
            raise RuntimeError("batch failed")
        assert (now, window_start, previous_start) == (
            NOW,
            NOW - timedelta(days=30),
            NOW - timedelta(days=60),
        )
        return self.rows

    async def get_attendance_stats_raw(
        self, user_id, window_start, previous_start, now
    ):
        self.individual_calls.append("attendance")
        return self.rows.attendance

    async def get_grades(self, user_id, start, end):
        self.individual_calls.append("grades")
        return self.rows.grades

    async def get_participation_stats_raw(self, user_id, window_start, now):
        self.individual_calls.append("participation")
        return self.rows.participation


@pytest.fixture
def fixed_clock(monkeypatch):
    monkeypatch.setattr(settings, "campus_timezone", "UTC")
    monkeypatch.setattr(
        UserAnalyticsService,
        "_windows",
        staticmethod(
            lambda days: (
                NOW,
                NOW - timedelta(days=days),
                NOW - timedelta(days=days * 2),
            )
        ),
    )
    monkeypatch.setattr(
        stats,
        "resolve_locale",
        lambda *, request, user: request.headers.get("accept-language", "en"),
    )


def make_handler(cache):
    analytics = UserAnalyticsService(None)
    repo = RepositoryStub()
    analytics.stats_repo = repo
    return GetStatsHandler(None, cache, analytics), repo


def query(user_id, kind):
    return GetStatsQuery(
        kind=kind,
        user_id=user_id,
        period_key="30d",
        period_days=30,
        locale="en",
        if_none_match=None,
        skip_cache=True,
    )


async def call_summary(handler, user_id, *, language="en", etag=None, skip=False):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/stats/summary",
            "query_string": b"",
            "headers": [(b"accept-language", language.encode())],
        }
    )
    response = Response()

    class Container:
        async def get(self, *_args, **_kwargs):
            return handler

    request.state.dishka_container = Container()
    payload = await stats.stats_summary(
        request=request,
        response=response,
        period="30d",
        skip_cache=skip,
        if_none_match=etag,
        user=SimpleNamespace(id=user_id),
    )
    return payload, response


@pytest.mark.asyncio
async def test_cold_summary_uses_one_batch_and_warm_summary_preserves_results(
    fixed_clock,
):
    user_id = uuid4()
    reference, reference_repo = make_handler(NullCache())
    expected = [await reference.handle(query(user_id, kind)) for kind in KINDS]
    assert reference_repo.individual_calls == list(KINDS)
    cache = MemoryCache(default_ttl=300)
    handler, repo = make_handler(cache)
    cold, cold_response = await call_summary(handler, user_id)
    assert cold == {
        kind: result.payload for kind, result in zip(KINDS, expected, strict=True)
    }
    expected_etag = hashlib.sha256(
        "".join(r.etag or "" for r in expected).encode()
    ).hexdigest()[:16]
    assert cold_response.headers["etag"] == f'"{expected_etag}"'
    assert repo.batch_calls == [(user_id, frozenset(KINDS))]
    assert repo.individual_calls == []
    warm, warm_response = await call_summary(handler, user_id)
    assert warm == cold
    assert warm_response.headers["etag"] == cold_response.headers["etag"]
    assert len(repo.batch_calls) == 1
    not_modified, _ = await call_summary(
        handler, user_id, etag=cold_response.headers["etag"]
    )
    assert isinstance(not_modified, Response) and not_modified.status_code == 304
    assert len(repo.batch_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_kind", KINDS)
async def test_mixed_cache_batches_only_missing_and_bypass_leaves_cache_untouched(
    fixed_clock, cached_kind
):
    user_id = uuid4()
    cache = MemoryCache(default_ttl=300)
    handler, repo = make_handler(cache)
    cached = await handler.handle(
        GetStatsQuery(
            kind=cached_kind,
            user_id=user_id,
            period_key="30d",
            period_days=30,
            locale="en",
            if_none_match=None,
            skip_cache=False,
        )
    )
    repo.individual_calls.clear()
    result, _ = await call_summary(handler, user_id)
    assert result[cached_kind] == cached.payload
    assert repo.batch_calls == [(user_id, frozenset(set(KINDS) - {cached_kind}))]
    assert repo.individual_calls == []
    before = [
        await stats_cache.get_cached_stats(
            cache=cache, kind=kind, user_id=user_id, period_key="30d"
        )
        for kind in KINDS
    ]
    await call_summary(handler, user_id, skip=True)
    after = [
        await stats_cache.get_cached_stats(
            cache=cache, kind=kind, user_id=user_id, period_key="30d"
        )
        for kind in KINDS
    ]
    assert repo.batch_calls[-1] == (user_id, frozenset(KINDS))
    assert [x.payload for x in before] == [x.payload for x in after]


@pytest.mark.asyncio
async def test_summary_locale_changes_representation_and_isolation_is_per_user(
    fixed_clock,
):
    cache = MemoryCache(default_ttl=300)
    handler, repo = make_handler(cache)
    first_user, second_user = uuid4(), uuid4()
    first, en_response = await call_summary(handler, first_user)
    translated, ru_response = await call_summary(
        handler, first_user, language="ru", etag=en_response.headers["etag"]
    )
    assert (
        translated["attendance"]["period_label"] != first["attendance"]["period_label"]
    )
    assert ru_response.headers["etag"] != en_response.headers["etag"]
    assert len(repo.batch_calls) == 1
    await call_summary(handler, second_user)
    assert repo.batch_calls[-1] == (second_user, frozenset(KINDS))


@pytest.mark.asyncio
async def test_summary_batch_error_propagates_without_populating_cache(fixed_clock):
    user_id = uuid4()
    cache = MemoryCache(default_ttl=300)
    handler, repo = make_handler(cache)
    repo.failure = True
    with pytest.raises(RuntimeError, match="batch failed"):
        await call_summary(handler, user_id)
    for kind in KINDS:
        assert (
            await stats_cache.get_cached_stats(
                cache=cache, kind=kind, user_id=user_id, period_key="30d"
            )
            is None
        )


@pytest.mark.asyncio
async def test_real_sqlite_cold_and_warm_summary_query_counts(db_session, fixed_clock):
    from sqlalchemy import event

    engine = db_session.bind.sync_engine
    statements = 0

    def count_statement(*_args, **_kwargs):
        nonlocal statements
        statements += 1

    handler = GetStatsHandler(
        db_session, MemoryCache(default_ttl=300), UserAnalyticsService(db_session)
    )
    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        user_id = uuid4()
        cold, cold_response = await call_summary(handler, user_id)
        assert statements == 1
        statements = 0
        warm, warm_response = await call_summary(handler, user_id)
        assert statements == 0
        assert warm == cold
        assert warm_response.headers["etag"] == cold_response.headers["etag"]
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)


@pytest.mark.asyncio
async def test_summary_service_rejects_unknown_kind_and_skips_empty_request():
    handler, repo = make_handler(MemoryCache(default_ttl=300))
    args = {"user_id": uuid4(), "period_days": 30, "period_key": "30d"}
    assert await handler.analytics_service.get_summary_stats(**args, kinds=[]) == {}
    with pytest.raises(ValueError, match="Unknown summary kind"):
        await handler.analytics_service.get_summary_stats(**args, kinds=["unknown"])
    assert repo.batch_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["user_id", "period_key", "period_days", "locale", "skip_cache"]
)
async def test_summary_handler_rejects_different_scope_before_database_access(field):
    handler, repo = make_handler(MemoryCache(default_ttl=300))
    user_id = uuid4()
    attendance, grades, participation = (query(user_id, kind) for kind in KINDS)
    changes = {
        "user_id": uuid4(),
        "period_key": "90d",
        "period_days": 90,
        "locale": "ru",
        "skip_cache": False,
    }
    with pytest.raises(ValueError, match="must share user and representation scope"):
        await handler.handle_summary(
            (attendance, replace(grades, **{field: changes[field]}), participation)
        )
    assert repo.batch_calls == []


@pytest.mark.asyncio
async def test_summary_handler_rejects_wrong_kind_order_before_database_access():
    handler, repo = make_handler(MemoryCache(default_ttl=300))
    user_id = uuid4()
    attendance, grades, participation = (query(user_id, kind) for kind in KINDS)
    with pytest.raises(ValueError, match="Invalid summary kinds"):
        await handler.handle_summary((grades, attendance, participation))
    assert repo.batch_calls == []
