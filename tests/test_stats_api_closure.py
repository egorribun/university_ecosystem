from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request
from starlette.responses import Response


def _install_lightweight_imports() -> None:
    deps = ModuleType("app.api.deps")
    deps.get_current_user = lambda: None
    sys.modules.setdefault("app.api.deps", deps)

    container = ModuleType("app.core.container")
    container.get_read_stats_handler = lambda: None
    sys.modules.setdefault("app.core.container", container)

    middleware = ModuleType("app.core.middleware")

    def ensure_vary_header(response, value: str) -> None:
        response.headers["Vary"] = value

    middleware._ensure_vary_header = ensure_vary_header
    sys.modules.setdefault("app.core.middleware", middleware)

    ratelimit = ModuleType("app.core.ratelimit")
    ratelimit.sensitive_route_limit = lambda: (lambda: None)
    sys.modules.setdefault("app.core.ratelimit", ratelimit)

    queries = ModuleType("app.cqrs.queries")

    @dataclass
    class StatsQuery:
        kind: str
        user_id: object
        period_key: str
        period_days: int
        locale: str
        if_none_match: str | None
        skip_cache: bool

    class StatsHandler:
        async def handle(self, query):  # pragma: no cover - supplied by tests
            raise NotImplementedError

    queries.GetStatsQuery = StatsQuery
    queries.GetStatsHandler = StatsHandler
    sys.modules.setdefault("app.cqrs.queries", queries)


_install_lightweight_imports()

from app.api import stats


class _Handler:
    def __init__(self, results):
        self.results = list(results)
        self.queries = []

    async def handle(self, query):
        self.queries.append(query)
        return self.results.pop(0)


def _request(*, locale: str | None = None) -> Request:
    headers = [(b"accept-language", locale.encode())] if locale else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/stats",
            "query_string": b"",
            "headers": headers,
        }
    )


def _user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _result(payload=None, *, etag=None, not_modified=False):
    return SimpleNamespace(payload=payload or {}, etag=etag, not_modified=not_modified)


def test_set_headers_and_period_resolution(monkeypatch):
    monkeypatch.setattr(stats.settings, "stats_cache_ttl_seconds", 42)
    monkeypatch.setattr(stats, "format_etag", lambda value: f"formatted:{value}")
    response = Response()
    stats._set_stats_headers(response, locale="ru", etag="abc")
    assert response.headers["Vary"] == "Accept-Language"
    assert response.headers["Content-Language"] == "ru"
    assert response.headers["Cache-Control"] == "private, max-age=42"
    assert response.headers["ETag"] == "formatted:abc"

    no_etag = Response()
    stats._set_stats_headers(no_etag, locale="en")
    assert "ETag" not in no_etag.headers

    assert stats._resolve_period(None) == ("30d", 30)
    assert stats._resolve_period(" ") == ("30d", 30)
    assert stats._resolve_period("90D") == ("90d", 90)
    assert stats._resolve_period("180d") == ("180d", 180)
    assert stats._resolve_period("7d") == ("30d", 30)


@pytest.mark.asyncio
async def test_handle_stats_query_valid_invalid_and_not_modified(monkeypatch):
    monkeypatch.setattr(stats, "resolve_locale", lambda **kwargs: "ru")
    handler = _Handler(
        [_result({"value": 1}, etag="v1"), _result(etag="v2", not_modified=True)]
    )
    response = Response()

    payload = await stats._handle_stats_query(
        "grades",
        "90D",
        True,
        "old",
        _request(),
        response,
        _user(),
        handler,
    )
    assert payload == {"value": 1}
    assert response.headers["Content-Language"] == "ru"
    assert handler.queries[0].kind == "grades"
    assert handler.queries[0].period_days == 90
    assert handler.queries[0].skip_cache is True

    not_modified = await stats._handle_stats_query(
        "unknown",
        "7d",
        False,
        "etag",
        _request(),
        Response(),
        _user(),
        handler,
    )
    assert isinstance(not_modified, Response)
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED
    assert handler.queries[1].kind == "attendance"
    assert handler.queries[1].period_days == 30


@pytest.mark.asyncio
async def test_individual_stats_routes_delegate_to_expected_kind():
    request = _request(locale="en")
    user = _user()
    for endpoint, kind in (
        (stats.attendance_summary, "attendance"),
        (stats.grade_summary, "grades"),
        (stats.participation_summary, "participation"),
    ):
        handler = _Handler([_result({"kind": kind}, etag=kind)])
        response = Response()
        result = await endpoint(
            request,
            response,
            period="30d",
            skip_cache=False,
            if_none_match=None,
            user=user,
            handler=handler,
        )
        assert result == {"kind": kind}
        assert handler.queries[0].kind == kind


@pytest.mark.asyncio
async def test_stats_summary_combines_subqueries_and_handles_304(monkeypatch):
    monkeypatch.setattr(stats, "resolve_locale", lambda **kwargs: "en")
    handler = _Handler(
        [
            _result({"a": 1}, etag="a"),
            _result({"g": 2}, etag=None),
            _result({"p": 3}, etag="p"),
        ]
    )
    response = Response()
    result = await stats.stats_summary(
        _request(),
        response,
        period="180d",
        skip_cache=True,
        if_none_match=None,
        user=_user(),
        handler=handler,
    )
    assert result == {
        "attendance": {"a": 1},
        "grades": {"g": 2},
        "participation": {"p": 3},
    }
    assert [query.kind for query in handler.queries] == [
        "attendance",
        "grades",
        "participation",
    ]
    assert all(query.period_days == 180 for query in handler.queries)
    combined = response.headers["ETag"]

    not_modified_handler = _Handler(
        [
            _result(etag="a"),
            _result(etag=None),
            _result(etag="p"),
        ]
    )
    not_modified = await stats.stats_summary(
        _request(),
        Response(),
        period="180d",
        skip_cache=False,
        if_none_match=combined,
        user=_user(),
        handler=not_modified_handler,
    )
    assert isinstance(not_modified, Response)
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_creation_analytics_is_explicitly_not_implemented():
    with pytest.raises(HTTPException) as exc_info:
        await stats.creation_analytics(
            _request(), object_type="events", period="30d", user=_user()
        )
    assert exc_info.value.status_code == status.HTTP_501_NOT_IMPLEMENTED
