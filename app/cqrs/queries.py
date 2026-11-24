import hashlib
import json
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.localization import (  # LOW-W19: moved from deferred inline import
    translate,
    translate_lesson_type,
)
from app.cqrs.base import Query, QueryHandler
from app.deps.cache import BaseCache, etag_matches, format_etag
from app.repositories.schedule_repository import (
    ScheduleRepository,  # LOW-W19: moved from deferred inline import
)
from app.schemas import schemas
from app.services import stats_cache  # LOW-W19: moved from deferred inline import
from app.services.stats_fill_fence import StatsFillFence, reservation_ttl


@dataclass
class GetScheduleQuery(Query):
    group_id: uuid.UUID | str
    locale: str | None
    if_none_match: str | None


@dataclass
class QueryResult:
    payload: Any
    etag: str | None = None
    not_modified: bool = False


class GetScheduleHandler(QueryHandler[GetScheduleQuery, QueryResult]):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
        # Group-keyed server caches cannot carry tenant scope, so the schedule is
        # always read through this session's RLS before a validator is evaluated.
        repo = ScheduleRepository(self.db)

        rows = await repo.get_by_group(
            uuid.UUID(str(query.group_id))
            if isinstance(query.group_id, str)
            else query.group_id
        )

        models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
        payload = jsonable_encoder(models_out)
        localized_payload = self._localize_schedule_payload(
            payload, locale=query.locale
        )

        # The ETag is the digest of exactly the localized representation served.
        digest = hashlib.sha256(
            json.dumps(
                localized_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        etag = format_etag(digest)
        if etag_matches(digest, query.if_none_match):
            return QueryResult(payload=None, etag=etag, not_modified=True)
        return QueryResult(payload=localized_payload, etag=etag)


@dataclass
class GetStatsQuery(Query):
    kind: Literal[
        "attendance", "grades", "participation"
    ]  # LOW-W19: constrained from bare str
    user_id: uuid.UUID | str
    period_key: str
    period_days: int
    locale: str | None
    if_none_match: str | None
    skip_cache: bool


class StatsFillFenceProtocol(Protocol):
    @property
    def supported(self) -> bool:
        """Return whether stats for this cache backend may be cached at all."""
        ...

    async def reserve(self, key: str, token: str, ttl: int) -> bool | None:
        """Return True if acquired, False on conflict, or None if unknown or unsupported."""
        ...

    async def complete(
        self, key: str, token: str, payload: object, ttl: int
    ) -> bool | None:
        """Return True if published, False on conflict, or None if unknown or unsupported."""
        ...


class GetStatsHandler(QueryHandler[GetStatsQuery, QueryResult]):
    def __init__(
        self,
        db: AsyncSession,
        cache: BaseCache,
        analytics_service: Any,
        *,
        fill_fence: StatsFillFenceProtocol | None = None,
    ) -> None:
        self.db = db
        self.cache = cache
        self.analytics_service = analytics_service
        self.fill_fence = (
            fill_fence if fill_fence is not None else StatsFillFence(cache)
        )

    def _caches(self, query: GetStatsQuery) -> bool:
        return not query.skip_cache and self.cache.enabled and self.fill_fence.supported

    async def handle(self, query: GetStatsQuery) -> QueryResult:
        stats = None
        if self._caches(query):
            cached = await stats_cache.get_cached_stats(
                cache=self.cache,
                kind=query.kind,
                user_id=query.user_id,
                period_key=query.period_key,
                skip_cache=query.skip_cache,
            )
            if cached is not None:
                stats = cached.payload

        if stats is None:
            compute_map = {
                "attendance": self.analytics_service.get_attendance_stats,
                "grades": self.analytics_service.get_grade_stats,
                "participation": self.analytics_service.get_participation_stats,
            }
            compute_fn = compute_map.get(query.kind)
            if not compute_fn:
                raise HTTPException(
                    status_code=400, detail=f"Unknown stats kind: {query.kind}"
                )
            stats = await compute_fn(
                user_id=query.user_id,
                period_days=query.period_days,
                period_key=query.period_key,
                cache=self.cache,
                skip_cache=query.skip_cache,
            )

        return self._stats_result(stats, query)

    async def handle_summary(
        self, queries: tuple[GetStatsQuery, GetStatsQuery, GetStatsQuery]
    ) -> tuple[QueryResult, QueryResult, QueryResult]:
        """Read uncached summary sections together while retaining per-kind caches."""
        if tuple(query.kind for query in queries) != (
            "attendance",
            "grades",
            "participation",
        ):
            raise ValueError("Invalid summary kinds")
        first = queries[0]
        if any(
            (q.user_id, q.period_key, q.period_days, q.locale, q.skip_cache)
            != (
                first.user_id,
                first.period_key,
                first.period_days,
                first.locale,
                first.skip_cache,
            )
            for q in queries[1:]
        ):
            raise ValueError("Summary queries must share user and representation scope")

        raw: dict[str, dict[str, Any]] = {}
        hot_period_keys: dict[str, str] = {}
        missing: list[str] = []
        for query in queries:
            cached = None
            lookup_period_key = query.period_key
            if self._caches(query):
                cached = await stats_cache.get_cached_stats(
                    cache=self.cache,
                    kind=query.kind,
                    user_id=query.user_id,
                    period_key=query.period_key,
                )
                if cached is None:
                    # Match the service's own cache lookup before calculating a miss.
                    lookup_period_key = stats_cache.resolve_period_key(
                        query.period_key, query.period_days
                    )
                    cached = await stats_cache.get_cached_stats(
                        cache=self.cache,
                        kind=query.kind,
                        user_id=query.user_id,
                        period_key=lookup_period_key,
                    )
            if cached is None:
                missing.append(query.kind)
            else:
                raw[query.kind] = cached.payload
                hot_period_keys[query.kind] = lookup_period_key

        if missing:
            reservations: dict[str, tuple[str, str]] = {}
            if self._caches(first):
                for query in queries:
                    if query.kind not in missing:
                        continue
                    period_key = stats_cache.resolve_period_key(
                        query.period_key, query.period_days
                    )
                    cache_key = stats_cache.make_stats_cache_key(
                        query.kind, query.user_id, period_key
                    )
                    token = secrets.token_hex(16)
                    reserved = await self.fill_fence.reserve(
                        cache_key, token, reservation_ttl()
                    )
                    if reserved is True:
                        reservations[query.kind] = (cache_key, token)

            computed = await self.analytics_service.get_summary_stats(
                user_id=first.user_id,
                period_days=first.period_days,
                period_key=first.period_key,
                kinds=missing,
            )

            # A hot entry can disappear while the first snapshot is being read.
            vanished: list[str] = []
            for query in queries:
                if query.kind in missing or not self._caches(query):
                    continue
                replacement = await stats_cache.get_cached_stats(
                    cache=self.cache,
                    kind=query.kind,
                    user_id=query.user_id,
                    period_key=hot_period_keys[query.kind],
                )
                if replacement is None:
                    vanished.append(query.kind)
                else:
                    raw[query.kind] = replacement.payload

            if vanished:
                refreshed = await self.analytics_service.get_summary_stats(
                    user_id=first.user_id,
                    period_days=first.period_days,
                    period_key=first.period_key,
                    kinds=vanished,
                )
                for kind in vanished:
                    raw[kind] = refreshed[kind]

            for query in queries:
                if query.kind not in missing:
                    continue
                payload = computed[query.kind]
                completed = False
                reservation = reservations.get(query.kind)
                if reservation is not None:
                    cache_key, token = reservation
                    completed = (
                        await self.fill_fence.complete(
                            cache_key,
                            token,
                            payload,
                            settings.stats_cache_ttl_seconds,
                        )
                    ) is True
                if not completed and self._caches(query):
                    replacement = await stats_cache.get_cached_stats(
                        cache=self.cache,
                        kind=query.kind,
                        user_id=query.user_id,
                        period_key=stats_cache.resolve_period_key(
                            query.period_key, query.period_days
                        ),
                    )
                    if replacement is not None:
                        payload = replacement.payload
                raw[query.kind] = payload

        return (
            self._stats_result(raw[queries[0].kind], queries[0]),
            self._stats_result(raw[queries[1].kind], queries[1]),
            self._stats_result(raw[queries[2].kind], queries[2]),
        )

    def _stats_result(self, stats: dict[str, Any], query: GetStatsQuery) -> QueryResult:
        # Validators belong to the localized response, not the raw cache entry.
        payload = self._enrich_stats(stats, query)
        etag = self._compute_etag(payload)
        if etag_matches(etag, query.if_none_match):
            return QueryResult(payload=None, etag=format_etag(etag), not_modified=True)
        return QueryResult(payload=payload, etag=format_etag(etag))

    def _enrich_stats(
        self, stats: dict[str, Any], query: GetStatsQuery
    ) -> dict[str, Any]:
        # LOW-W19: translate import moved to top-level
        label = translate(
            f"stats.period.{query.period_key}",
            locale=query.locale,
            default=query.period_key,
            days=query.period_days,
        )
        payload = dict(stats)
        payload["period_key"] = stats.get("period_key") or query.period_key
        payload["period_label"] = label
        # Cache round-trips sort nested keys; keep cold and warm response bytes
        # identical before assigning a strong representation validator.
        canonical: dict[str, Any] = json.loads(
            json.dumps(jsonable_encoder(payload), sort_keys=True)
        )
        return canonical

    def _compute_etag(self, payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()
