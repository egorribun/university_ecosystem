from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

import app.models as models
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.services import stats_cache

logger = get_logger(__name__)


class UserAnalyticsService:
    def __init__(self, db: AsyncDatabaseSession):
        self.db = db

    def _dt_to_iso(self, value: datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    def _parse_grade_payload(
        self, body: str | None, *, fallback_title: str, fallback_date: datetime | None
    ) -> dict[str, Any] | None:
        if not body:
            return None
        try:
            payload = json.loads(body)
        except TypeError, ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        score = payload.get("score")
        if score is None:
            return None
        try:
            score_value = float(score)
        except TypeError, ValueError:
            return None
        max_score = payload.get("max")
        max_value = None
        if max_score is not None:
            try:
                max_value = float(max_score)
            except TypeError, ValueError:
                max_value = None
        course = payload.get("course")
        if not isinstance(course, str) or not course.strip():
            course = fallback_title
        date_raw = payload.get("date")
        if isinstance(date_raw, str):
            try:
                parsed = datetime.fromisoformat(date_raw)
            except ValueError:
                parsed = None
        else:
            parsed = None
        date_value = parsed or fallback_date
        return {
            "course": course,
            "score": score_value,
            "max": max_value,
            "date": self._dt_to_iso(date_value),
        }

    async def get_attendance_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="attendance",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            from typing import cast

            return cast(dict[str, Any], cached.payload)

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)

        # Fallback values since UserStats model is not yet available
        percent = 0.0
        attended_events = 0
        total_events = 0
        trend = 0.0

        # 2. Fast OLTP query for recent 5 records only
        recent_attendance_base = (
            select(
                models.EventAttendance.registered_at.label("registered_at"),
                models.Event.starts_at.label("starts_at"),
                models.Event.title.label("title"),
            )
            .join(models.Event, models.Event.id == models.EventAttendance.event_id)
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.is_active.is_(True),
                models.Event.starts_at >= window_start,
                models.Event.starts_at < now,
            )
            .order_by(models.EventAttendance.registered_at.desc())
            .limit(5)
        )
        rows = await self.db.execute(recent_attendance_base)

        recent: list[dict[str, Any]] = []
        for row in rows:
            date_source = row.starts_at or row.registered_at
            recent.append(
                {
                    "date": self._dt_to_iso(date_source),
                    "status": "present",
                    "course": row.title or None,
                }
            )

        # TD-33-02: stub — returns 100% until GradeRecord model exists
        total_events = len(recent)
        attended_events = len(recent)
        if total_events > 0:
            percent = 100.0

        result = {
            "percent": round(percent, 2),
            "present": attended_events,
            "total": total_events,
            "trend": round(trend, 2),
            "period_key": cache_period_key,
            "recent": recent,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="attendance",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result

    async def get_grade_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="grades",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            from typing import cast

            return cast(dict[str, Any], cached.payload)

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)

        average = 0.0
        trend = 0.0

        # TD-33-02 (LOW-W19): Grade data is sourced from the Notification table
        # because a dedicated grades/scores domain model does not yet exist.
        # This is a temporary approach — notification bodies are unstructured
        # text blobs and parsing them with _parse_grade_payload() is fragile
        # (format changes to notification bodies will silently break grade
        # stats).  Once a first-class GradeRecord or CourseScore model is
        # introduced, replace this query with a direct join against that table.
        res = await self.db.execute(
            select(models.Notification)
            .where(
                models.Notification.user_id == user_id,
                models.Notification.type == "grade",
                models.Notification.created_at >= window_start,
            )
            .order_by(models.Notification.created_at.desc())
            .limit(20)
        )
        recent_notifications = res.scalars()

        recent: list[dict[str, Any]] = []
        total_grades = 0
        sum_scores = 0.0
        for notif in recent_notifications:
            parsed = self._parse_grade_payload(
                str(notif.body) if notif.body else None,
                fallback_title=str(notif.title),
                fallback_date=notif.created_at,
            )
            if not parsed:
                continue

            recent.append(parsed)
            total_grades += 1
            if parsed.get("score"):
                sum_scores += parsed["score"]

        recent = sorted(recent, key=lambda x: str(x.get("date")), reverse=True)[:5]

        max_values = [item["max"] for item in recent if item.get("max")]
        scale = "5"
        if any(value and value > 5 for value in max_values):
            scale = "100"

        if total_grades > 0:
            average = sum_scores / total_grades

        result = {
            "average": average,
            "total_grades": total_grades,
            "scale": scale,
            "trend": trend,
            "period_key": cache_period_key,
            "recent": recent,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="grades",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result

    async def get_participation_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="participation",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            from typing import cast

            return cast(dict[str, Any], cached.payload)

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)

        events = 0
        hours = 0.0
        groups = 0
        trend = 0

        # Fast OLTP query for recent 5
        recent_rows = await self.db.execute(
            select(
                models.EventAttendance.registered_at,
                models.Event.starts_at,
                models.Event.title,
                models.Event.event_type,
            )
            .join(models.Event, models.Event.id == models.EventAttendance.event_id)
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.starts_at >= window_start,
                models.Event.starts_at < now,
                models.Event.is_active.is_(True),
            )
            .order_by(models.Event.starts_at.desc())
            .limit(5)
        )

        recent = []
        for registered_at, starts_at, title, event_type in recent_rows:
            recent.append(
                {
                    "title": title or "",
                    "date": self._dt_to_iso(starts_at or registered_at),
                    "role": event_type or None,
                }
            )

        if events == 0 and recent:
            events = len(recent)

        result = {
            "events": events,
            "hours": round(hours, 2),
            "groups": groups,
            "trend": trend,
            "recent": recent,
            "period_key": cache_period_key,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="participation",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result
