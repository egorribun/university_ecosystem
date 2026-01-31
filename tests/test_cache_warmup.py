import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.deps.cache import CacheEntry
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
    assert cache_warmup._schedule_cache_key(123) == "schedule:group:123"


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
        mock_item.subject = "Math"
        mock_item.teacher = "Doe"
        mock_item.room = "101"
        mock_item.weekday = "monday"
        mock_item.parity = "even"
        mock_item.lesson_type = "lecture"
        mock_item.lesson_type_display = "Lecture"
        mock_item.time_start = "10:00"
        mock_item.time_end = "11:30"

        mock_service_instance.get_schedule = AsyncMock(return_value=[mock_item])

        await cache_warmup._warm_schedule_group(mock_cache, mock_db, 1, ttl_seconds=60)

        mock_cache.set.assert_called_once()
        assert "schedule:group:1" in mock_cache.set.call_args[0][0]


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
