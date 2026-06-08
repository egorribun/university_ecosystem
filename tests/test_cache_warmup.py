import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deps.cache import CacheEntry
from app.schemas import schemas
from app.services import cache_warmup


@pytest.mark.asyncio
async def test_is_entry_fresh():
    entry = CacheEntry(payload={}, stored_at=time.time(), etag="123")

    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_max_age_seconds = 60
        assert cache_warmup._is_entry_fresh(entry)

        entry.stored_at = time.time() - 61
        assert not cache_warmup._is_entry_fresh(entry)

        mock_settings.cache_warmup_max_age_seconds = 0
        assert cache_warmup._is_entry_fresh(entry)


def test_schedule_cache_key():
    uid = str(uuid.uuid4())
    assert cache_warmup._schedule_cache_key(uid) == f"schedule:group:{uid}"


def test_period_days_from_key():
    assert cache_warmup._period_days_from_key("7d") == 7
    assert cache_warmup._period_days_from_key("30D") == 30
    assert cache_warmup._period_days_from_key("invalid") is None
    assert cache_warmup._period_days_from_key(None) is None


@pytest.mark.asyncio
async def test_warm_schedule_group():
    mock_cache = AsyncMock()
    mock_cache.enabled = True
    mock_cache.get.return_value = None
    mock_db = AsyncMock()

    with (
        patch("app.services.schedule_service.ScheduleService") as MockService,
        patch("app.repositories.schedule_repository.ScheduleRepository"),
        patch("app.repositories.schedule_repository.GroupRepository"),
        patch("app.services.schedule_optimizer.ScheduleOptimizerService"),
    ):
        mock_service_instance = MockService.return_value
        # Mock objects often behave like dicts if configured, but model_validate
        # expects obj or dict. If model_validate(obj), it tries getattr.
        # Let's return a Mock that has these attributes.

        mock_item = MagicMock()
        mock_item.id = uuid.uuid4()
        mock_item.group_id = uuid.uuid4()
        mock_item.subject = "Math"
        mock_item.teacher = "Doe"
        mock_item.room = "101"
        mock_item.weekday = "monday"
        mock_item.parity = "both"
        mock_item.lesson_type = "lecture"
        mock_item.lesson_type_display = "Lecture"
        mock_item.time_start = "10:00"
        mock_item.time_end = "11:30"

        mock_service_instance.get_schedule = AsyncMock(return_value=[mock_item])

        group_id = uuid.uuid4()
        await cache_warmup._warm_schedule_group(
            mock_cache, mock_db, group_id, ttl_seconds=60
        )

        mock_cache.set.assert_called_once()
        assert f"schedule:group:{group_id}" in mock_cache.set.call_args[0][0]


@pytest.mark.asyncio
async def test_warm_cache_disabled():
    with patch("app.services.cache_warmup.settings") as mock_settings:
        mock_settings.cache_warmup_enabled = False
        res = await cache_warmup.warm_cache()
        assert res is None


@pytest.mark.asyncio
async def test_warm_cache_enabled():
    with (
        patch("app.services.cache_warmup.settings") as mock_settings,
        patch("app.services.cache_warmup.get_cache") as mock_get_cache,
        patch("app.services.cache_warmup.async_session") as mock_session_cls,
        patch("app.services.cache_warmup._warm_schedule") as mock_warm_schedule,
        patch("app.services.cache_warmup._warm_stats") as mock_warm_stats,
        patch("app.services.cache_warmup._warm_news") as mock_warm_news,
        patch("app.services.cache_warmup._warm_events") as mock_warm_events,
    ):
        mock_settings.cache_warmup_enabled = True
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_get_cache.return_value = mock_cache

        mock_db = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_db

        await cache_warmup.warm_cache()

        mock_warm_schedule.assert_called_once()
        mock_warm_stats.assert_called_once()
        mock_warm_news.assert_called_once()
        mock_warm_events.assert_called_once()


@pytest.mark.asyncio
async def test_warm_stats_for_user():
    mock_cache = AsyncMock()
    mock_cache.enabled = True
    mock_cache.get.return_value = None
    mock_db = AsyncMock()

    with (
        patch(
            "app.services.cache_warmup.stats_cache.get_cached_stats", return_value=None
        ),
        patch(
            "app.services.user.analytics_service.UserAnalyticsService"
        ) as MockAnalyticsService,
        patch("app.repositories.user_repository.UserRepository"),
        patch("app.services.notification_service.NotificationService"),
    ):
        mock_service = MockAnalyticsService.return_value
        mock_service.get_attendance_stats = AsyncMock()
        mock_service.get_grade_stats = AsyncMock()
        mock_service.get_participation_stats = AsyncMock()

        user_id = uuid.uuid4()
        await cache_warmup._warm_stats_for_user(mock_cache, mock_db, user_id, "7d")

        mock_service.get_attendance_stats.assert_called_once()
        mock_service.get_grade_stats.assert_called_once()
        mock_service.get_participation_stats.assert_called_once()


@pytest.mark.asyncio
async def test_warm_news():
    mock_cache = AsyncMock()
    mock_cache.enabled = True
    mock_cache.get.return_value = None
    mock_db = AsyncMock()

    with (
        patch(
            "app.api.news._get_news_list_version",
            AsyncMock(return_value="v1"),
        ),
        patch("app.core.container.get_vector_service"),
        patch("app.repositories.news_repository.NewsRepository"),
        patch("app.services.news_service.NewsService") as MockNewsService,
    ):
        mock_service = MockNewsService.return_value
        # results: list of (news_obj, l_count, c_count, liked)
        mock_news = MagicMock()
        mock_news.id = uuid.uuid4()
        mock_news.title = "Test News"
        mock_news.content = "Test Content"
        mock_news.title_en = "Test News EN"
        mock_news.content_en = "Test Content EN"
        mock_news.image_url = "http://example.com/image.jpg"
        mock_news.category = "general"
        mock_news.created_at = time.time()
        mock_news.published_at = time.time()
        mock_news.author_id = uuid.uuid4()
        mock_news.is_published = True
        mock_news.tags = []
        mock_news.image_url_optimized = None
        mock_service.list_news = AsyncMock(
            return_value=schemas.PaginatedNews(
                items=[mock_news], has_more=False, next_cursor=None
            )
        )
        mock_service.serialize_news = MagicMock(return_value={})

        await cache_warmup._warm_news(mock_cache, mock_db)

        assert mock_cache.set.call_count >= 1


# --------------------------------------------------------------------------- #
# Track C (session 6) additions — early-return guards + _warm_events +         #
# _warm_schedule / _warm_stats wrappers + warm_cache backend-disabled/error.   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_warm_schedule_group_skips_when_cache_disabled():
    cache = AsyncMock()
    cache.enabled = False
    await cache_warmup._warm_schedule_group(
        cache, AsyncMock(), uuid.uuid4(), ttl_seconds=60
    )
    cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_warm_schedule_group_skips_when_cached_fresh():
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = CacheEntry(payload={}, stored_at=time.time(), etag="x")
    await cache_warmup._warm_schedule_group(
        cache, AsyncMock(), uuid.uuid4(), ttl_seconds=60
    )
    cache.set.assert_not_called()  # fresh entry → no recompute


@pytest.mark.asyncio
async def test_warm_schedule_group_skips_when_no_rows():
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None
    with (
        patch("app.services.schedule_service.ScheduleService") as mock_service,
        patch("app.services.schedule_optimizer.ScheduleOptimizerService"),
    ):
        mock_service.return_value.get_schedule = AsyncMock(return_value=[])
        await cache_warmup._warm_schedule_group(
            cache, AsyncMock(), uuid.uuid4(), ttl_seconds=60
        )
    cache.set.assert_not_called()  # empty schedule → nothing cached


@pytest.mark.asyncio
async def test_warm_schedule_skips_without_group_ids():
    with patch("app.services.cache_warmup.settings") as ms:
        ms.cache_warmup_group_ids = []
        await cache_warmup._warm_schedule(AsyncMock(), AsyncMock())  # early return


@pytest.mark.asyncio
async def test_warm_schedule_fans_out_per_group():
    with (
        patch("app.services.cache_warmup.settings") as ms,
        patch("app.services.cache_warmup._warm_schedule_group", AsyncMock()) as mwsg,
    ):
        ms.cache_warmup_group_ids = ("g1", "g2")
        ms.cache_default_ttl_seconds = 300
        await cache_warmup._warm_schedule(AsyncMock(), AsyncMock())
    assert mwsg.await_count == 2


@pytest.mark.asyncio
async def test_warm_stats_skips_without_user_ids():
    with patch("app.services.cache_warmup.settings") as ms:
        ms.cache_warmup_stats_user_ids = []
        await cache_warmup._warm_stats(AsyncMock(), AsyncMock())  # early return


@pytest.mark.asyncio
async def test_warm_stats_fans_out_per_user_period():
    with (
        patch("app.services.cache_warmup.settings") as ms,
        patch("app.services.cache_warmup._warm_stats_for_user", AsyncMock()) as mwsfu,
    ):
        ms.cache_warmup_stats_user_ids = ("u1",)
        ms.cache_warmup_period_keys = ("30d", "90d")
        await cache_warmup._warm_stats(AsyncMock(), AsyncMock())
    assert mwsfu.await_count == 2  # 1 user x 2 periods


@pytest.mark.asyncio
async def test_warm_stats_for_user_skips_when_cached_fresh():
    cache = AsyncMock()
    cache.enabled = True
    fresh = CacheEntry(payload={}, stored_at=time.time(), etag="x")
    with patch(
        "app.services.cache_warmup.stats_cache.get_cached_stats",
        AsyncMock(return_value=fresh),
    ):
        await cache_warmup._warm_stats_for_user(cache, AsyncMock(), uuid.uuid4(), "30d")
    # returned before constructing UserAnalyticsService → no recompute


@pytest.mark.asyncio
async def test_warm_news_skips_when_cache_disabled():
    cache = AsyncMock()
    cache.enabled = False
    await cache_warmup._warm_news(cache, AsyncMock())
    cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_warm_events_skips_when_cache_disabled():
    cache = AsyncMock()
    cache.enabled = False
    await cache_warmup._warm_events(cache, AsyncMock())
    cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_warm_events_populates_both_locales():
    cache = AsyncMock()
    cache.enabled = True
    cache.get.return_value = None
    with (
        patch("app.api.events._get_events_list_version", AsyncMock(return_value="v1")),
        patch("app.repositories.unit_of_work.uow_from_session"),
        patch("app.services.vector_service.VectorService"),
        patch("app.services.event_service.EventService") as mock_event_service,
    ):
        mock_event_service.return_value.get_events = AsyncMock(
            return_value={"items": [], "has_more": False, "next_cursor": None}
        )
        await cache_warmup._warm_events(cache, AsyncMock())
    assert cache.set.call_count == 2  # ru + en


@pytest.mark.asyncio
async def test_warm_cache_skips_when_backend_disabled():
    with (
        patch("app.services.cache_warmup.settings") as ms,
        patch("app.services.cache_warmup.get_cache") as mgc,
    ):
        ms.cache_warmup_enabled = True
        backend = MagicMock()
        backend.enabled = False
        mgc.return_value = backend
        await cache_warmup.warm_cache()  # backend disabled → returns before gather


@pytest.mark.asyncio
async def test_warm_cache_swallows_connection_errors():
    with (
        patch("app.services.cache_warmup.settings") as ms,
        patch("app.services.cache_warmup.get_cache") as mgc,
        patch("app.services.cache_warmup.async_session") as msess,
        patch(
            "app.services.cache_warmup._warm_schedule",
            AsyncMock(side_effect=ConnectionError("boom")),
        ),
        patch("app.services.cache_warmup._warm_stats", AsyncMock()),
        patch("app.services.cache_warmup._warm_news", AsyncMock()),
        patch("app.services.cache_warmup._warm_events", AsyncMock()),
    ):
        ms.cache_warmup_enabled = True
        backend = MagicMock()
        backend.enabled = True
        mgc.return_value = backend
        msess.return_value.__aenter__.return_value = AsyncMock()
        # Must not raise — the except (ConnectionError, ...) handler swallows it.
        await cache_warmup.warm_cache()
