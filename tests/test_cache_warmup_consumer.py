"""Regression tests through the actual news and events HTTP consumers."""

import time
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models as models
from app.api.deps.etag import generate_cache_key
from app.auth.security import get_password_hash
from app.core.cache_versioning import news_cache_version
from app.core.tenant import (
    bypass_rls_ctx,
    set_bypass_rls,
    set_current_tenant,
    tenant_id_ctx,
)
from app.deps.cache import MemoryCache
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services import cache_warmup
from app.services.news_service import NewsService


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [20, 21])
@pytest.mark.parametrize("backend", ["redis", "memory"])
async def test_anonymous_news_request_consumes_complete_warmed_page(
    count, backend, async_client, db_session, fake_cache
):
    cache = fake_cache if backend == "redis" else MemoryCache()
    db_session.add_all(
        [
            models.News(
                title=f"Новость {index}",
                content="Содержание",
                title_en=f"News {index}",
                content_en="Content",
            )
            for index in range(count)
        ]
    )
    await db_session.commit()
    await news_cache_version.reset(cache)

    service = NewsService(uow_from_session(db_session), MagicMock())
    expected = {
        locale: jsonable_encoder(await service.list_news(limit=20, locale=locale))
        for locale in ("ru", "en")
    }
    assert expected["en"]["has_more"] is (count > 20)
    assert bool(expected["en"]["next_cursor"]) is (count > 20)

    await cache_warmup._warm_news(cache, db_session)

    original = NewsService.list_news
    calls = []

    async def tracked_list_news(self, **kwargs):
        calls.append(kwargs)
        return await original(self, **kwargs)

    with (
        patch("app.api.deps.etag.get_cache", return_value=cache),
        patch.object(NewsService, "list_news", tracked_list_news),
    ):
        for locale in ("ru", "en"):
            headers = {"Accept-Language": locale}
            response = await async_client.get("/news", headers=headers)
            assert response.status_code == 200
            assert response.json() == expected[locale]
            assert response.headers["Content-Language"] == locale
            assert response.headers["ETag"]
            conditional = await async_client.get(
                "/news?limit=20",
                headers={**headers, "If-None-Match": response.headers["ETag"]},
            )
            assert conditional.status_code == 304
        assert calls == []
        await news_cache_version.increment(cache)
        changed = await async_client.get("/news", headers={"Accept-Language": "en"})
        assert changed.status_code == 200
        assert changed.json() == expected["en"]
        assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("has_more", "cursor"), [(False, None), (True, "next-page")])
async def test_warm_news_preserves_service_pagination(has_more, cursor):
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None
    page = schemas.PaginatedNews(
        items=[
            schemas.NewsOut(
                id=uuid4(),
                title=f"News {index}",
                content="Content",
                created_at=datetime.now(UTC),
            )
            for index in range(20)
        ],
        has_more=has_more,
        next_cursor=cursor,
    )
    with (
        patch("app.api.news._get_news_list_version", AsyncMock(return_value="v1")),
        patch("app.repositories.unit_of_work.uow_from_session"),
        patch("app.services.vector_service.VectorService"),
        patch("app.services.news_service.NewsService") as service,
    ):
        service.return_value.list_news = AsyncMock(return_value=page)
        await cache_warmup._warm_news(cache, MagicMock())
    assert [call.args[1] for call in cache.set.await_args_list] == [
        jsonable_encoder(page),
        jsonable_encoder(page),
    ]


@pytest.mark.asyncio
async def test_warm_news_refreshes_only_stale_locale_in_the_supplied_cache():
    cache = MemoryCache()
    await news_cache_version.reset(cache)
    version = await news_cache_version.get_version(cache)
    with (
        patch.object(cache_warmup.settings, "cache_warmup_max_age_seconds", 60),
        patch("app.repositories.unit_of_work.uow_from_session"),
        patch("app.services.vector_service.VectorService"),
        patch("app.services.news_service.NewsService") as service,
    ):
        service.return_value.list_news = AsyncMock(
            return_value=schemas.PaginatedNews(items=[], has_more=False)
        )
        await cache_warmup._warm_news(cache, MagicMock())
        ru_key = generate_cache_key(
            cache_prefix=news_cache_version.prefix,
            version=version,
            locale="ru",
            params={"limit": 20, "cursor": None, "__tenant_id": ""},
        )
        ru_entry = await cache.get(ru_key)
        assert ru_entry is not None
        ru_entry.stored_at = time.time() - 61
        service.return_value.list_news.reset_mock()
        await cache_warmup._warm_news(cache, MagicMock())
        service.return_value.list_news.assert_awaited_once_with(
            limit=20, cursor=None, locale="ru"
        )
        refreshed = await cache.get(ru_key)
        assert refreshed is not None and refreshed.stored_at > ru_entry.stored_at


@pytest.mark.asyncio
@pytest.mark.parametrize(("tenant", "bypass"), [("tenant-a", False), ("", True)])
async def test_warm_news_does_not_publish_an_unsafe_database_context(tenant, bypass):
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None
    tenant_token = set_current_tenant(tenant)
    bypass_token = set_bypass_rls(bypass)
    try:
        with (
            patch("app.api.news._get_news_list_version", AsyncMock(return_value="v1")),
            patch("app.repositories.unit_of_work.uow_from_session"),
            patch("app.services.vector_service.VectorService"),
            patch("app.services.news_service.NewsService") as service,
        ):
            service.return_value.list_news = AsyncMock(
                return_value=schemas.PaginatedNews(items=[], has_more=False)
            )
            await cache_warmup._warm_news(cache, MagicMock())
        service.assert_not_called()
        cache.set.assert_not_awaited()
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


@pytest.mark.asyncio
async def test_warmed_anonymous_news_is_not_returned_to_a_signed_in_user(
    async_client, db_session, fake_cache, user_factory
):
    password = "TestNewsUser456!"
    user = await user_factory(hashed_password=await get_password_hash(password))
    news = models.News(title="Headline", content="Content")
    db_session.add(news)
    await db_session.flush()
    db_session.add(models.NewsLike(news_id=news.id, user_id=user.id))
    await db_session.commit()
    await news_cache_version.reset(fake_cache)
    await cache_warmup._warm_news(fake_cache, db_session)

    anonymous = await async_client.get("/news", headers={"Accept-Language": "en"})
    assert anonymous.status_code == 200
    assert anonymous.json()["items"][0]["is_liked"] is False

    login = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200
    token = login.cookies.get("access_token_v2")
    signed_in = await async_client.get(
        "/news",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
            "X-Query-Budget": "15",
        },
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["items"][0]["is_liked"] is True
    assert signed_in.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_startup_skips_system_event_warmup_for_auth_only_endpoint(
    async_client, fake_cache
):
    response = await async_client.get("/events")
    assert response.status_code == 401

    with (
        patch("app.services.cache_warmup.get_cache", return_value=fake_cache),
        patch("app.services.cache_warmup.async_session") as session_factory,
        patch("app.services.cache_warmup.settings") as settings,
        patch("app.services.cache_warmup._warm_schedule", new_callable=AsyncMock),
        patch("app.services.cache_warmup._warm_stats", new_callable=AsyncMock),
        patch("app.services.cache_warmup._warm_news", new_callable=AsyncMock),
        patch("app.services.event_service.EventService") as event_service,
        patch("app.services.vector_service.VectorService"),
        patch("app.repositories.unit_of_work.uow_from_session"),
    ):
        settings.cache_warmup_enabled = True
        session_factory.return_value.__aenter__.return_value = MagicMock()
        event_service.return_value.get_events = AsyncMock(
            return_value={"items": [], "has_more": False}
        )
        await cache_warmup.warm_cache()

    event_service.assert_not_called()


@pytest.mark.asyncio
async def test_startup_warmers_can_query_shared_session_without_overlap():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cache = MemoryCache()
    errors = []
    results = []

    async def query(_cache, db):
        try:
            result = await db.execute(text("SELECT 1"))
            results.append(result.scalar_one())
        except InvalidRequestError as exc:
            errors.append(str(exc))

    try:
        with (
            patch("app.services.cache_warmup.settings") as settings,
            patch("app.services.cache_warmup.get_cache", return_value=cache),
            patch("app.services.cache_warmup.async_session", sessions),
            patch("app.services.cache_warmup._warm_schedule", query),
            patch("app.services.cache_warmup._warm_stats", query),
            patch("app.services.cache_warmup._warm_news", query),
        ):
            settings.cache_warmup_enabled = True
            await cache_warmup.warm_cache()
    finally:
        await engine.dispose()

    assert errors == []
    assert results == [1, 1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["schedule", "stats", "user_stats"])
async def test_warmup_fanout_can_query_shared_session_without_overlap(scope):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cache = MemoryCache()
    errors = []
    results = []

    async def query(_cache, db, *_args, **_kwargs):
        try:
            result = await db.execute(text("SELECT 1"))
            results.append(result.scalar_one())
        except InvalidRequestError as exc:
            errors.append(str(exc))

    try:
        async with sessions() as db:

            async def query_stat(**_kwargs):
                await query(cache, db)

            with (
                patch("app.services.cache_warmup.settings") as settings,
                patch("app.services.cache_warmup._warm_schedule_group", query),
                patch("app.services.cache_warmup._warm_stats_for_user", query)
                if scope == "stats"
                else nullcontext(),
                patch(
                    "app.services.cache_warmup.stats_cache.get_cached_stats",
                    AsyncMock(return_value=None),
                ),
                patch(
                    "app.services.user.analytics_service.UserAnalyticsService"
                ) as svc,
            ):
                settings.cache_warmup_group_ids = ("one", "two")
                settings.cache_default_ttl_seconds = 60
                settings.cache_warmup_stats_user_ids = ("user",)
                settings.cache_warmup_period_keys = ("30d", "90d")
                svc.return_value.get_attendance_stats = AsyncMock(
                    side_effect=query_stat
                )
                svc.return_value.get_grade_stats = AsyncMock(side_effect=query_stat)
                svc.return_value.get_participation_stats = AsyncMock(
                    side_effect=query_stat
                )
                if scope == "schedule":
                    await cache_warmup._warm_schedule(cache, db)
                elif scope == "stats":
                    await cache_warmup._warm_stats(cache, db)
                else:
                    await cache_warmup._warm_stats_for_user(cache, db, "user", "30d")
    finally:
        await engine.dispose()

    assert errors == []
    assert results == [1] * (3 if scope == "user_stats" else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["schedule", "stats", "user_stats"])
async def test_warmup_fanout_continues_after_one_item_fails(scope):
    cache = MemoryCache()
    worker = AsyncMock(side_effect=[ValueError("first failed"), None])
    with (
        patch("app.services.cache_warmup.settings") as settings,
        patch("app.services.cache_warmup._warm_schedule_group", worker),
        patch("app.services.cache_warmup._warm_stats_for_user", worker)
        if scope == "stats"
        else nullcontext(),
        patch(
            "app.services.cache_warmup.stats_cache.get_cached_stats",
            AsyncMock(return_value=None),
        ),
        patch("app.services.user.analytics_service.UserAnalyticsService") as svc,
    ):
        settings.cache_warmup_group_ids = ("one", "two")
        settings.cache_default_ttl_seconds = 60
        settings.cache_warmup_stats_user_ids = ("user",)
        settings.cache_warmup_period_keys = ("30d", "90d")
        svc.return_value.get_attendance_stats = AsyncMock(
            side_effect=ValueError("first failed")
        )
        svc.return_value.get_grade_stats = AsyncMock()
        svc.return_value.get_participation_stats = AsyncMock()
        if scope == "schedule":
            await cache_warmup._warm_schedule(cache, MagicMock())
            assert worker.await_count == 2
        elif scope == "stats":
            await cache_warmup._warm_stats(cache, MagicMock())
            assert worker.await_count == 2
        else:
            await cache_warmup._warm_stats_for_user(cache, MagicMock(), "user", "30d")
            svc.return_value.get_attendance_stats.assert_awaited_once()
            svc.return_value.get_grade_stats.assert_awaited_once()
            svc.return_value.get_participation_stats.assert_awaited_once()
