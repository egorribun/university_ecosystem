from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.models import Grade
from app.repositories.user_stats_repository import UserStatsRepository
from app.schemas.dtos.analytics import ParticipationStatsDTO
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

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normalize database timestamps; SQLite drops timezone metadata."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _dt_to_iso(self, value: datetime | None) -> str:
        if value is None:
            return ""
        return self._as_utc(value).isoformat()

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

            campus_zone = ZoneInfo(settings.campus_timezone)
            total = 0
            attended = 0
            previous_total = 0
            previous_attended = 0
            daily_counts: dict[date, dict[str, int]] = {}
            streak_dates: set[date] = set()
            recent_candidates: list[tuple[datetime, Any]] = []

            # The repository returns only active, past event rows, never an empty head.
            for row in rows:
                starts_at = self._as_utc(row.starts_at)
                registered = bool(row.is_registered)

                if registered:
                    streak_dates.add(starts_at.astimezone(campus_zone).date())

                if previous_start <= starts_at < window_start:
                    previous_total += 1
                    previous_attended += int(registered)
                elif starts_at >= window_start:
                    total += 1
                    attended += int(registered)
                    campus_date = starts_at.astimezone(campus_zone).date()
                    counts = daily_counts.setdefault(
                        campus_date, {"registered": 0, "total": 0}
                    )
                    counts["total"] += 1
                    counts["registered"] += int(registered)

                    if registered:
                        recent_candidates.append((self._as_utc(row.registered_at), row))

            percent = attended / total * 100 if total else 0.0
            previous_percent = (
                previous_attended / previous_total * 100 if previous_total else 0.0
            )

            recent_candidates.sort(key=lambda item: item[0], reverse=True)
            recent = [
                {
                    "date": self._dt_to_iso(row.starts_at),
                    "status": "present",
                    "course": row.title or None,
                }
                for _, row in recent_candidates[:_RECENT_LIMIT]
            ]

            today = self._as_utc(now).astimezone(campus_zone).date()
            yesterday = today - timedelta(days=1)
            anchor: date | None
            if today in streak_dates:
                anchor = today
            elif yesterday in streak_dates:
                anchor = yesterday
            else:
                anchor = None

            streak_days = 0
            while anchor is not None and anchor in streak_dates:
                streak_days += 1
                anchor -= timedelta(days=1)

            daily = [
                {
                    "date": day.isoformat(),
                    "registered": counts["registered"],
                    "total": counts["total"],
                }
                for day, counts in sorted(daily_counts.items())
            ]
            return {
                "percent": round(percent, 2),
                "present": attended,
                "total": total,
                "trend": round(percent - previous_percent, 2),
                "period_key": cache_period_key,
                "streak_days": streak_days,
                "daily": daily,
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
            window_grades = await self.stats_repo.get_grades(
                user_id, previous_start, now
            )
            current: list[Grade] = []
            previous: list[Grade] = []
            for grade in window_grades:
                created_at = self._as_utc(grade.created_at)
                if created_at >= window_start:
                    current.append(grade)
                else:
                    previous.append(grade)

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
            window_rows = await self.stats_repo.get_participation_stats_raw(
                user_id=user_id, window_start=previous_start, now=now
            )
            rows: list[ParticipationStatsDTO] = []
            previous_rows: list[ParticipationStatsDTO] = []
            for row in window_rows:
                starts_at = self._as_utc(row.starts_at)
                if starts_at >= window_start:
                    rows.append(row)
                else:
                    previous_rows.append(row)

            hours = sum(
                max(
                    0.0,
                    (
                        self._as_utc(row.ends_at) - self._as_utc(row.starts_at)
                    ).total_seconds()
                    / 3600,
                )
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
