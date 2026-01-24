from __future__ import annotations

import asyncio
import logging
import time

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.schedule import _SCHEDULE_CACHE_TTL_SECONDS
from app.core.config import settings
from app.core.database import async_session
from app.deps.cache import BaseCache, CacheEntry, get_cache
from app.schemas import schemas
from app.services import stats_cache

logger = logging.getLogger(__name__)


def _is_entry_fresh(entry: CacheEntry) -> bool:
    max_age = settings.cache_warmup_max_age_seconds
    if max_age <= 0:
        return True
    return (time.time() - entry.stored_at) <= max_age


def _schedule_cache_key(group_id: int) -> str:
    return f"schedule:group:{group_id}"


async def _warm_schedule_group(
    cache: BaseCache, db: AsyncSession, group_id: int, *, ttl_seconds: int
) -> None:
    if not cache.enabled:
        return

    cache_key = _schedule_cache_key(group_id)
    cached = await cache.get(cache_key)
    if cached and _is_entry_fresh(cached):
        return

    rows = await crud.get_schedule_by_group(db, group_id)
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
        _warm_schedule_group(cache, db, group_id, ttl_seconds=ttl)
        for group_id in settings.cache_warmup_group_ids
    ]
    await asyncio.gather(*tasks)


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
    user_id: int,
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
    tasks = [
        crud.get_attendance_stats(
            db,
            user_id=user_id,
            period_days=days,
            period_key=resolved_period,
            cache=cache,
            skip_cache=skip_cache,
        ),
        crud.get_grade_stats(
            db,
            user_id=user_id,
            period_days=days,
            cache=cache,
            period_key=resolved_period,
            skip_cache=skip_cache,
        ),
        crud.get_participation_stats(
            db,
            user_id=user_id,
            period_days=days,
            cache=cache,
            period_key=resolved_period,
            skip_cache=skip_cache,
        ),
    ]
    await asyncio.gather(*tasks)


async def _warm_stats(cache: BaseCache, db: AsyncSession) -> None:
    if not settings.cache_warmup_stats_user_ids:
        return
    tasks = []
    for user_id in settings.cache_warmup_stats_user_ids:
        for period_key in settings.cache_warmup_period_keys:
            tasks.append(
                _warm_stats_for_user(cache, db, user_id, period_key, skip_cache=False)
            )
    await asyncio.gather(*tasks)


async def _warm_news(cache: BaseCache, db: AsyncSession) -> None:
    if not cache.enabled:
        return
    # Warm up first page of news for default locales
    from app.api.news import (
        _get_news_list_version,
        _news_list_cache_key,
    )

    version = await _get_news_list_version()
    for locale in ["ru", "en"]:
        cache_key = _news_list_cache_key(locale, 20, None, version)
        cached = await cache.get(cache_key)
        if cached and _is_entry_fresh(cached):
            continue

        rows = await crud.get_news_list(db, limit=21, cursor=None)
        has_more = len(rows) > 20
        if has_more:
            rows = rows[:20]

        from app.api.news import _serialize_news

        items = [_serialize_news(item, locale) for item in rows]
        payload = {
            "items": items,
            "has_more": has_more,
            "next_cursor": None,  # Simplification for warmup
        }
        await cache.set(cache_key, jsonable_encoder(payload))


async def _warm_events(cache: BaseCache, db: AsyncSession) -> None:
    if not cache.enabled:
        return
    # Warm up first page of active events
    from app.api.events import _events_list_cache_key, _get_events_list_version

    version = await _get_events_list_version(cache)
    for locale in ["ru", "en"]:
        cache_key = _events_list_cache_key(
            locale=locale,
            search="",
            event_type="",
            location="",
            is_active=True,
            limit=20,
            cursor=None,
            version=version,
        )
        cached = await cache.get(cache_key)
        if cached and _is_entry_fresh(cached):
            continue

        payload = await crud.get_all_events(
            db,
            user_id=0,  # System-level warmup
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
        except Exception:
            logger.exception("Cache warmup failed")
