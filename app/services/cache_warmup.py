from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

from fastapi.encoders import jsonable_encoder

from app.api.schedule import _SCHEDULE_CACHE_TTL_SECONDS
from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.deps.cache import BaseCache, CacheEntry, get_cache
from app.schemas import schemas
from app.services import stats_cache

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


def _is_entry_fresh(entry: CacheEntry) -> bool:
    max_age = settings.cache_warmup_max_age_seconds
    if max_age <= 0:
        return True
    return (time.time() - entry.stored_at) <= max_age


def _schedule_cache_key(group_id: uuid.UUID | str) -> str:
    return f"schedule:group:{group_id}"


async def _warm_schedule_group(
    cache: BaseCache, db: AsyncSession, group_id: uuid.UUID | str, *, ttl_seconds: int
) -> None:
    if not cache.enabled:
        return

    cache_key = _schedule_cache_key(group_id)
    cached = await cache.get(cache_key)
    if cached and _is_entry_fresh(cached):
        return

    from app.repositories.unit_of_work import uow_from_session
    from app.services.schedule_optimizer import ScheduleOptimizerService
    from app.services.schedule_service import ScheduleService

    uow = uow_from_session(db)
    optimizer = ScheduleOptimizerService()
    service = ScheduleService(uow, optimizer)

    rows = await service.get_schedule(group_id)
    if not rows:
        return

    models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)
    await cache.set(cache_key, payload, ttl=ttl_seconds)


async def _warm_schedule(cache: BaseCache, db: AsyncSession) -> None:
    if not settings.cache_warmup_group_ids:
        return
    ttl = (
        getattr(settings, "cache_default_ttl_seconds", _SCHEDULE_CACHE_TTL_SECONDS)
        or _SCHEDULE_CACHE_TTL_SECONDS
    )
    tasks = [
        _warm_schedule_group(cache, db, str(group_id), ttl_seconds=ttl)
        for group_id in settings.cache_warmup_group_ids
    ]
    # MOD-23-04 (audit 2026-03-25 Wave 23): return_exceptions=True — cache warmup
    # is best-effort; one group failure must not prevent others from warming.
    await asyncio.gather(*tasks, return_exceptions=True)


def _period_days_from_key(period_key: str) -> int | None:
    normalized = (period_key or "").lower().strip()
    if normalized.endswith("d"):
        try:
            return int(normalized[:-1])
        except ValueError:
            return None
    return None


async def _warm_stats_for_user(
    cache: BaseCache,
    db: AsyncSession,
    user_id: uuid.UUID | str,
    period_key: str,
    *,
    skip_cache: bool = False,
) -> None:
    resolved_period = stats_cache.resolve_period_key(
        period_key, _period_days_from_key(period_key)
    )
    cached = await stats_cache.get_cached_stats(
        cache=cache,
        kind="attendance",
        user_id=user_id,
        period_key=resolved_period,
        skip_cache=skip_cache,
    )
    if cached and _is_entry_fresh(cached):
        return

    days = _period_days_from_key(resolved_period) or 30
    from app.services.user.analytics_service import UserAnalyticsService

    service = UserAnalyticsService(db)

    tasks = [
        service.get_attendance_stats(
            user_id=user_id,
            period_days=days,
            period_key=resolved_period,
            cache=cache,
            skip_cache=skip_cache,
        ),
        service.get_grade_stats(
            user_id=user_id,
            period_days=days,
            cache=cache,
            period_key=resolved_period,
            skip_cache=skip_cache,
        ),
        service.get_participation_stats(
            user_id=user_id,
            period_days=days,
            cache=cache,
            period_key=resolved_period,
            skip_cache=skip_cache,
        ),
    ]
    # MOD-23-04 (audit 2026-03-25 Wave 23): return_exceptions=True — individual
    # stat warmup failure must not block sibling stats.
    await asyncio.gather(*tasks, return_exceptions=True)


async def _warm_stats(cache: BaseCache, db: AsyncSession) -> None:
    if not settings.cache_warmup_stats_user_ids:
        return
    tasks = []
    for u_id in settings.cache_warmup_stats_user_ids:
        for period_key in settings.cache_warmup_period_keys:
            tasks.append(
                _warm_stats_for_user(cache, db, str(u_id), period_key, skip_cache=False)
            )
    # MOD-23-04 (audit 2026-03-25 Wave 23): return_exceptions=True — individual
    # user/period warmup failure must not block remaining warmups.
    await asyncio.gather(*tasks, return_exceptions=True)


async def _warm_news(cache: BaseCache, db: AsyncSession) -> None:
    if not cache.enabled:
        return
    # Warm up first page of news for default locales
    from app.api.deps.etag import generate_cache_key
    from app.api.news import _get_news_list_version

    version = await _get_news_list_version()

    from app.core.container import get_vector_service
    from app.repositories.unit_of_work import uow_from_session
    from app.services.news_service import NewsService

    uow = uow_from_session(db)
    # We need vector service for NewsService init
    vector_service = get_vector_service(db)
    service = NewsService(uow, vector_service)

    for locale in ["ru", "en"]:
        cache_key = generate_cache_key(
            cache_prefix="ue:news:list",
            version=version,
            locale=locale,
            params={"limit": 20, "cursor": None},
        )
        cached = await cache.get(cache_key)
        if cached and _is_entry_fresh(cached):
            continue

        items = await service.list_news(limit=20, cursor=None, locale=locale)
        items_list = items.items
        has_more = len(items_list) >= 20

        payload = {
            "items": items_list,
            "has_more": has_more,
            "next_cursor": None,  # Simplification for warmup
        }
        await cache.set(cache_key, jsonable_encoder(payload))


async def _warm_events(cache: BaseCache, db: AsyncSession) -> None:
    if not cache.enabled:
        return
    # Warm up first page of active events
    from app.api.deps.etag import generate_cache_key
    from app.api.events import _get_events_list_version

    version = await _get_events_list_version(cache)
    for locale in ["ru", "en"]:
        cache_key = generate_cache_key(
            cache_prefix="ue:events:list",
            version=version,
            locale=locale,
            params={
                "search": "",
                "type": "",
                "location": "",
                "is_active": True,
                "limit": 20,
                "cursor": None,
            },
        )
        cached = await cache.get(cache_key)
        if cached and _is_entry_fresh(cached):
            continue

        # HIGH-W19: imports moved inside loop so service/vector construction happens
        # per-iteration; previously these lines were outside the loop causing only
        # the last locale's cache_key to be populated.
        from app.repositories.unit_of_work import uow_from_session
        from app.services.event_service import EventService
        from app.services.vector_service import VectorService

        uow = uow_from_session(db)
        # We need a vector service instance, but for warmup of *list* we probably don't
        # need actual embeddings if the search query is empty. However, EventService
        # requires it. We can rely on DI container or construct it manually.
        # Since this is a background task, manual construction is safer/easier.
        # VectorService needs settings.

        vector_service = VectorService(db)
        service = EventService(uow, vector_service)

        payload = await service.get_events(
            user_id=None,  # System-level warmup
            search="",
            type="",
            location="",
            is_active=True,
            locale=locale,
            limit=20,
            cursor=None,
        )
        await cache.set(cache_key, jsonable_encoder(payload))


async def warm_cache() -> None:
    if not settings.cache_warmup_enabled:
        logger.info("Cache warmup disabled, skipping")
        return

    cache = get_cache()
    if not cache.enabled:
        logger.info("Cache warmup requested but cache backend is disabled")
        return

    async with async_session() as db:
        try:
            await asyncio.gather(
                _warm_schedule(cache, db),
                _warm_stats(cache, db),
                _warm_news(cache, db),
                _warm_events(cache, db),
            )
        except (ConnectionError, TimeoutError, OSError):# RZ-28-01 + PERF-25-02
            # RZ-20-04: Narrowed — cache warmup is best-effort.
            logger.exception("Cache warmup failed")
