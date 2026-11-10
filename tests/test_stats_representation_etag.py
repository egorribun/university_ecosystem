"""Stats validators describe the localized representation on every cache path."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.responses import JSONResponse, Response

from app.api.deps import get_current_user_from_dishka
from app.api.stats import _set_stats_headers
from app.cqrs.queries import GetStatsHandler, GetStatsQuery
from app.deps.cache import MemoryCache, NullCache
from app.services import stats_cache
from app.services.user.analytics_service import UserAnalyticsService
from tests.conftest import install_dishka_override


def _handler(cache):
    analytics = UserAnalyticsService(None)
    start = datetime.now(UTC) - timedelta(hours=2)
    analytics.stats_repo = SimpleNamespace(
        get_attendance_stats_raw=AsyncMock(return_value=[]),
        get_grades=AsyncMock(return_value=[]),
        get_participation_stats_raw=AsyncMock(
            return_value=[
                SimpleNamespace(
                    title="Synthetic seminar",
                    event_type="seminar",
                    starts_at=start,
                    ends_at=start + timedelta(hours=1),
                )
            ]
        ),
    )
    return GetStatsHandler(None, cache, analytics), analytics.stats_repo


def _query(user_id, kind="participation", *, locale="en", etag=None, skip=False):
    return GetStatsQuery(
        kind=kind,
        user_id=user_id,
        period_key="30d",
        period_days=30,
        locale=locale,
        if_none_match=etag,
        skip_cache=skip,
    )


@pytest.mark.parametrize("kind", ["attendance", "grades", "participation"])
async def test_stats_etag_is_stable_across_cold_warm_and_bypass(kind):
    handler, repo = _handler(MemoryCache(default_ttl=300))
    user_id = uuid4()
    cold = await handler.handle(_query(user_id, kind))
    warm = await handler.handle(_query(user_id, kind))
    bypass = await handler.handle(_query(user_id, kind, skip=True))
    assert JSONResponse(cold.payload).body == JSONResponse(warm.payload).body
    assert JSONResponse(cold.payload).body == JSONResponse(bypass.payload).body
    assert cold.etag == warm.etag == bypass.etag
    method = "get_grades" if kind == "grades" else f"get_{kind}_stats_raw"
    assert getattr(repo, method).await_count == 2


@pytest.mark.parametrize("mode", ["warm", "miss", "bypass", "disabled"])
async def test_stats_conditional_response_is_checked_after_final_representation(mode):
    cache = NullCache() if mode == "disabled" else MemoryCache(default_ttl=300)
    handler, _ = _handler(cache)
    user_id = uuid4()
    first = await handler.handle(_query(user_id))
    if mode == "miss":
        await stats_cache.invalidate_user_stats_cache(user_ids=user_id, cache=cache)
    response = await handler.handle(
        _query(user_id, etag=first.etag, skip=mode == "bypass")
    )
    assert response.not_modified is True
    assert response.payload is None
    assert response.etag == first.etag


@pytest.mark.parametrize("kind", ["attendance", "grades", "participation"])
async def test_stats_locale_switch_cannot_reuse_other_language_validator(kind):
    handler, repo = _handler(MemoryCache(default_ttl=300))
    user_id = uuid4()
    await handler.handle(_query(user_id, kind))
    english = await handler.handle(_query(user_id, kind))
    russian = await handler.handle(
        _query(user_id, kind, locale="ru", etag=english.etag)
    )
    assert russian.not_modified is False
    assert english.payload["period_label"] == "Last 30 days"
    assert russian.payload["period_label"] == "За последние 30 дней"
    assert russian.etag != english.etag
    again = await handler.handle(_query(user_id, kind, locale="ru", etag=russian.etag))
    assert again.not_modified is True
    method = "get_grades" if kind == "grades" else f"get_{kind}_stats_raw"
    getattr(repo, method).assert_awaited_once()


@pytest.mark.parametrize("path", ["participation", "summary"])
async def test_stats_http_locale_change_returns_new_body_and_preserves_vary(
    app, async_client, path
):
    handler, _ = _handler(MemoryCache(default_ttl=300))
    user = SimpleNamespace(id=uuid4(), preferred_language="en", role="student")
    app.dependency_overrides[get_current_user_from_dishka] = lambda: user
    install_dishka_override(app, GetStatsHandler=handler)
    url = f"/stats/{path}"
    cold = await async_client.get(url, headers={"Accept-Language": "en"})
    warm = await async_client.get(url, headers={"Accept-Language": "en"})
    assert cold.status_code == warm.status_code == 200
    assert cold.content == warm.content
    assert cold.headers["etag"] == warm.headers["etag"]
    user.preferred_language = "ru"
    switched = await async_client.get(
        url,
        headers={
            "Accept-Language": "en",
            "If-None-Match": warm.headers["etag"],
        },
    )
    assert switched.status_code == 200
    assert switched.headers["etag"] != warm.headers["etag"]
    payload = switched.json()
    data = payload["participation"] if path == "summary" else payload
    assert data["period_label"] == "За последние 30 дней"
    unchanged = await async_client.get(
        url,
        headers={
            "Accept-Language": "en",
            "If-None-Match": switched.headers["etag"],
        },
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    for response in (switched, unchanged):
        assert response.headers["content-language"] == "ru"
        assert "accept-language" in response.headers["vary"].lower()
        assert response.headers["cache-control"].startswith("private,")


@pytest.mark.parametrize("path", ["participation", "summary"])
@pytest.mark.parametrize("condition", ["weak", "list", "star", "miss"])
async def test_stats_http_if_none_match_uses_get_comparison(
    app, async_client, path, condition
):
    handler, _ = _handler(MemoryCache(default_ttl=300))
    user = SimpleNamespace(id=uuid4(), preferred_language="en", role="student")
    app.dependency_overrides[get_current_user_from_dishka] = lambda: user
    install_dishka_override(app, GetStatsHandler=handler)
    url = f"/stats/{path}"
    await async_client.get(url)
    warm = await async_client.get(url)
    assert warm.status_code == 200, warm.text
    tag = warm.headers["etag"]
    value = {
        "weak": f"W/{tag}",
        "list": f'"other", W/{tag}',
        "star": "*",
        "miss": '"other"',
    }[condition]
    response = await async_client.get(url, headers={"If-None-Match": value})
    assert response.status_code == (200 if condition == "miss" else 304)
    assert response.headers["etag"] == tag
    if condition != "miss":
        assert response.content == b""


async def test_stats_cached_data_change_invalidates_old_representation_tag():
    cache = MemoryCache(default_ttl=300)
    handler, _ = _handler(cache)
    user_id = uuid4()
    original = await handler.handle(_query(user_id))
    cached = await stats_cache.get_cached_stats(
        cache=cache, kind="participation", user_id=user_id, period_key="30d"
    )
    assert "period_label" not in cached.payload
    changed = {**cached.payload, "events": cached.payload["events"] + 1}
    await stats_cache.set_cached_stats(
        cache=cache,
        kind="participation",
        user_id=user_id,
        period_key="30d",
        payload=changed,
    )
    result = await handler.handle(_query(user_id, etag=original.etag))
    assert result.not_modified is False
    assert result.payload["events"] == changed["events"]
    assert result.etag != original.etag
    after = await stats_cache.get_cached_stats(
        cache=cache, kind="participation", user_id=user_id, period_key="30d"
    )
    assert after.payload == changed
    assert "period_label" not in after.payload


def test_stats_vary_keeps_existing_dimensions():
    response = Response(headers={"Vary": "Origin"})
    _set_stats_headers(response, locale="ru", etag="synthetic-tag")
    assert {part.strip().lower() for part in response.headers["vary"].split(",")} == {
        "origin",
        "accept-language",
    }
