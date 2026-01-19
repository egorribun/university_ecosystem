from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.localization import translate_lesson_type
from app.cqrs.base import Query, QueryHandler
from app.deps.cache import BaseCache, format_etag
from app.schemas import schemas


@dataclass
class GetScheduleQuery(Query):
    group_id: int
    locale: str | None
    if_none_match: str | None


@dataclass
class QueryResult:
    payload: Any
    etag: str | None = None
    not_modified: bool = False


class GetScheduleHandler(QueryHandler[GetScheduleQuery, QueryResult]):
    def __init__(self, db: AsyncSession, cache: BaseCache) -> None:
        self.db = db
        self.cache = cache

    def _schedule_cache_key(self, group_id: int) -> str:
        return f"schedule:group:{group_id}"

    def _localize_schedule_payload(
        self, payload: Sequence[Any], locale: str | None
    ) -> list[dict[str, Any]]:
        localized: list[dict[str, Any]] = []
        for item in payload:
            data = dict(item)
            raw_type = data.get("lesson_type")
            display = translate_lesson_type(raw_type, locale=locale)
            data["lesson_type_display"] = display
            localized.append(data)
        return localized

    async def handle(self, query: GetScheduleQuery) -> QueryResult:
        cache_key = self._schedule_cache_key(query.group_id)

        if self.cache.enabled:
            cached = await self.cache.get(cache_key)
            if cached:
                if query.if_none_match and cached.etag == query.if_none_match.strip(
                    '"'
                ):
                    return QueryResult(
                        payload=None, etag=format_etag(cached.etag), not_modified=True
                    )

                localized = self._localize_schedule_payload(
                    cached.payload, locale=query.locale
                )
                return QueryResult(payload=localized, etag=format_etag(cached.etag))

        # Fetch from DB
        rows = await crud.get_schedule_by_group(self.db, query.group_id)
        models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
        payload = jsonable_encoder(models_out)
        localized_payload = self._localize_schedule_payload(
            payload, locale=query.locale
        )

        etag = None
        if self.cache.enabled:
            entry = await self.cache.set(
                cache_key, payload, ttl=300
            )  # _SCHEDULE_CACHE_TTL_SECONDS
            etag = format_etag(entry.etag)

        return QueryResult(payload=localized_payload, etag=etag)


@dataclass
class GetStatsQuery(Query):
    kind: str
    user_id: int
    period_key: str
    period_days: int
    locale: str | None
    if_none_match: str | None
    skip_cache: bool


class GetStatsHandler(QueryHandler[GetStatsQuery, QueryResult]):
    def __init__(self, db: AsyncSession, cache: BaseCache) -> None:
        self.db = db
        self.cache = cache

    async def handle(self, query: GetStatsQuery) -> QueryResult:
        from app.services import stats_cache

        # 1. Try cache
        if not query.skip_cache and self.cache.enabled:
            cached = await stats_cache.get_cached_stats(
                cache=self.cache,
                kind=query.kind,
                user_id=query.user_id,
                period_key=query.period_key,
                skip_cache=query.skip_cache,
            )
            if cached:
                if query.if_none_match and cached.etag == query.if_none_match.strip(
                    '"'
                ):
                    return QueryResult(
                        payload=None, etag=format_etag(cached.etag), not_modified=True
                    )

                payload = self._enrich_stats(cached.payload, query)
                return QueryResult(payload=payload, etag=format_etag(cached.etag))

        # 2. Compute stats
        compute_map = {
            "attendance": crud.get_attendance_stats,
            "grades": crud.get_grade_stats,
            "participation": crud.get_participation_stats,
        }

        compute_fn = compute_map.get(query.kind)
        if not compute_fn:
            raise ValueError(f"Unknown stats kind: {query.kind}")

        # The crud functions have different signatures (some take period_days,
        # some just days?)
        # Let's check crud.py if possible, but based on stats.py:
        # attendance: db, user_id, period_days, period_key, cache, skip_cache
        # grades: db, user_id, period_days, cache, period_key, skip_cache
        # participation: db, user_id, period_days, cache, period_key, skip_cache

        if query.kind == "attendance":
            stats = await compute_fn(
                self.db,
                user_id=query.user_id,
                period_days=query.period_days,
                period_key=query.period_key,
                cache=self.cache,
                skip_cache=query.skip_cache,
            )
        else:
            stats = await compute_fn(
                self.db,
                user_id=query.user_id,
                period_days=query.period_days,
                cache=self.cache,
                period_key=query.period_key,
                skip_cache=query.skip_cache,
            )

        payload = self._enrich_stats(stats, query)
        etag = self._compute_etag(payload)

        # Handle race condition/consistency if needed, but for now just return
        return QueryResult(payload=payload, etag=format_etag(etag))

    def _enrich_stats(
        self, stats: dict[str, Any], query: GetStatsQuery
    ) -> dict[str, Any]:
        from app.core.localization import translate

        label = translate(
            f"stats.period.{query.period_key}",
            locale=query.locale,
            default=query.period_key,
            days=query.period_days,
        )
        payload = dict(stats)
        payload["period_key"] = stats.get("period_key") or query.period_key
        payload["period_label"] = label
        return payload

    def _compute_etag(self, payload: dict[str, Any]) -> str:
        import hashlib
        import json

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()
