from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.repositories.user_stats_repository import UserStatsRepository
from app.services import stats_cache

logger = get_logger(__name__)

# Grades on a 5-point scale never exceed this value; anything above it means the
# institution reports on a 100-point scale.
_FIVE_POINT_SCALE_MAX = 5.0
_RECENT_LIMIT = 5


class UserAnalyticsService:
    """Per-user attendance, grade and participation statistics.

    Semantics (product decision): *attendance* is event registration — a user
    "attended" every active event of the window they hold an
    ``EventAttendance`` row for.  Every metric compares the requested window with
    the immediately preceding window of the same length to derive ``trend``.
    Raw SQL lives in :class:`UserStatsRepository`; this class only aggregates and
    caches.
    """

    def __init__(self, db: AsyncDatabaseSession):
        self.db = db
        self.stats_repo = UserStatsRepository(db)

    def _dt_to_iso(self, value: datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    async def _cached(
        self,
        *,
        kind: str,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None,
        cache: BaseCache | None,
        skip_cache: bool,
        compute: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind=kind,
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            return cast(dict[str, Any], cached.payload)

        result = await compute(cache_period_key)
        await stats_cache.set_cached_stats(
            cache=cache,
            kind=kind,
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result

    @staticmethod
    def _windows(period_days: int) -> tuple[datetime, datetime, datetime]:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        return now, window_start, window_start - timedelta(days=period_days)

    async def get_attendance_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        async def compute(cache_period_key: str) -> dict[str, Any]:
            now, window_start, previous_start = self._windows(period_days)
            rows = await self.stats_repo.get_attendance_stats_raw(
                user_id, window_start, previous_start, now
            )

            # The aggregate sub-select yields exactly one row, repeated on every
            # "recent" row, so the first row carries all four counters.
            head = rows[0] if rows else None
            total = int(getattr(head, "current_total", 0) or 0)
            attended = int(getattr(head, "current_attended", 0) or 0)
            previous_total = int(getattr(head, "previous_total", 0) or 0)
            previous_attended = int(getattr(head, "previous_attended", 0) or 0)

            percent = attended / total * 100 if total else 0.0
            previous_percent = (
                previous_attended / previous_total * 100 if previous_total else 0.0
            )

            recent = [
                {
                    "date": self._dt_to_iso(row.starts_at or row.registered_at),
                    "status": "present",
                    "course": row.title or None,
                }
                for row in rows
                if getattr(row, "rn", None) is not None
            ]
            return {
                "percent": round(percent, 2),
                "present": attended,
                "total": total,
                "trend": round(percent - previous_percent, 2),
                "period_key": cache_period_key,
                "recent": recent,
            }

        return await self._cached(
            kind="attendance",
            user_id=user_id,
            period_days=period_days,
            period_key=period_key,
            cache=cache,
            skip_cache=skip_cache,
            compute=compute,
        )

    async def get_grade_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        async def compute(cache_period_key: str) -> dict[str, Any]:
            now, window_start, previous_start = self._windows(period_days)
            current = await self.stats_repo.get_grades(user_id, window_start, now)
            previous = await self.stats_repo.get_grades(
                user_id, previous_start, window_start
            )

            def average(grades: Any) -> float:
                return (
                    sum(float(g.score) for g in grades) / len(grades) if grades else 0.0
                )

            current_average = average(current)
            scale = (
                "100"
                if any(float(g.score) > _FIVE_POINT_SCALE_MAX for g in current)
                else "5"
            )
            recent = [
                {
                    "course": str(g.subject),
                    "score": float(g.score),
                    "max": None,
                    "date": self._dt_to_iso(g.created_at),
                }
                for g in current[:_RECENT_LIMIT]
            ]
            return {
                "average": round(current_average, 2),
                "total_grades": len(current),
                "scale": scale,
                "trend": round(current_average - average(previous), 2),
                "period_key": cache_period_key,
                "recent": recent,
            }

        return await self._cached(
            kind="grades",
            user_id=user_id,
            period_days=period_days,
            period_key=period_key,
            cache=cache,
            skip_cache=skip_cache,
            compute=compute,
        )

    async def get_participation_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        async def compute(cache_period_key: str) -> dict[str, Any]:
            now, window_start, previous_start = self._windows(period_days)
            rows = await self.stats_repo.get_participation_stats_raw(
                user_id=user_id, window_start=window_start, now=now
            )
            previous_rows = await self.stats_repo.get_participation_stats_raw(
                user_id=user_id, window_start=previous_start, now=window_start
            )

            hours = sum(
                max(0.0, (row.ends_at - row.starts_at).total_seconds() / 3600)
                for row in rows
            )
            groups = {row.event_type for row in rows if row.event_type}
            recent = [
                {
                    "title": row.title or "",
                    "date": self._dt_to_iso(row.starts_at),
                    "role": row.event_type or None,
                }
                for row in rows[:_RECENT_LIMIT]
            ]
            return {
                "events": len(rows),
                "hours": round(hours, 2),
                "groups": len(groups),
                "trend": len(rows) - len(previous_rows),
                "recent": recent,
                "period_key": cache_period_key,
            }

        return await self._cached(
            kind="participation",
            user_id=user_id,
            period_days=period_days,
            period_key=period_key,
            cache=cache,
            skip_cache=skip_cache,
            compute=compute,
        )
