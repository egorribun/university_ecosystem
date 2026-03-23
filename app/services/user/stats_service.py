import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.logging import get_logger
from app.deps.cache import BaseCache
from app.repositories.user_stats_repository import UserStatsRepository
from app.services import stats_cache

logger = get_logger(__name__)


class GradePayload(BaseModel):
    course: str | None = None
    score: float = Field(ge=0)
    max: float | None = Field(default=None, ge=0)
    date: str | None = None


class StatsService:
    def __init__(self, stats_repo: UserStatsRepository) -> None:
        self.stats_repo = stats_repo

    def _dt_to_iso(self, value: datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @stats_cache.cache_stats(kind="attendance")
    async def get_attendance_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        previous_start = window_start - timedelta(days=period_days)

        rows = await self.stats_repo.get_attendance_stats_raw(
            user_id,
            window_start,
            previous_start,
            now,
        )

        if rows:
            first_row = rows[0]
            total_events = int(getattr(first_row, "current_total", 0) or 0)
            attended_events = int(getattr(first_row, "current_attended", 0) or 0)
            previous_events = int(getattr(first_row, "previous_total", 0) or 0)
            previous_attended = int(getattr(first_row, "previous_attended", 0) or 0)
        else:
            total_events = attended_events = previous_events = previous_attended = 0

        percent = (attended_events / total_events * 100) if total_events else 0.0
        previous_percent = (
            previous_attended / previous_events * 100 if previous_events else 0.0
        )

        recent: list[dict[str, Any]] = []
        for row in rows:
            if getattr(row, "rn", None) is None:
                continue
            date_source = getattr(row, "starts_at", None) or getattr(
                row, "registered_at", None
            )
            recent.append(
                {
                    "date": self._dt_to_iso(date_source),
                    "status": "present",
                    "course": getattr(row, "title", None) or None,
                }
            )

        return {
            "percent": round(percent, 2),
            "present": attended_events,
            "total": total_events,
            "trend": round(percent - previous_percent, 2),
            "period_key": stats_cache.resolve_period_key(period_key, period_days),
            "recent": recent,
        }

    def _parse_grade_payload(
        self, body: str | None, *, fallback_title: str, fallback_date: datetime | None
    ) -> dict[str, Any] | None:
        if not body:
            return None
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                return None
            payload = GradePayload.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError):
            return None

        # Resolve fields with fallbacks
        course = (payload.course or "").strip() or fallback_title

        date_value = fallback_date
        if payload.date:
            try:
                date_value = datetime.fromisoformat(payload.date)
            except ValueError:
                pass

        return {
            "course": course,
            "score": payload.score,
            "max": payload.max,
            "date": self._dt_to_iso(date_value),
        }

    @stats_cache.cache_stats(kind="grades")
    async def get_grade_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        previous_start = window_start - timedelta(days=period_days)

        current_rows = await self.stats_repo.get_grade_notifications(
            user_id,
            window_start,
            now,
        )
        current_entries = []
        for notification in current_rows:
            entry = self._parse_grade_payload(
                str(notification.body) if notification.body else None,
                fallback_title=str(notification.title) if notification.title else "",
                fallback_date=notification.created_at,
            )
            if entry:
                current_entries.append(entry)

        previous_rows = await self.stats_repo.get_grade_notifications(
            user_id,
            previous_start,
            window_start,
        )
        previous_entries = []
        for notification in previous_rows:
            entry = self._parse_grade_payload(
                str(notification.body) if notification.body else None,
                fallback_title=str(notification.title) if notification.title else "",
                fallback_date=notification.created_at,
            )
            if entry:
                previous_entries.append(entry)

        def _average(items: list[dict[str, Any]]) -> float:
            if not items:
                return 0.0
            from typing import cast

            return sum(cast(float, item["score"]) for item in items) / len(items)

        average = _average(current_entries)
        previous_average = _average(previous_entries)

        scale = "5"
        # Check if any score or max suggests 100-point scale
        max_vals = [
            item["max"] for item in current_entries if item.get("max") is not None
        ]
        scores = [item["score"] for item in current_entries]
        if any(v > 5 for v in max_vals) or any(s > 5 for s in scores):
            scale = "100"

        recent = current_entries[:5]

        return {
            "average": round(average, 2) if current_entries else 0.0,
            "scale": scale,
            "trend": round(average - previous_average, 2),
            "recent": recent,
            "period_key": stats_cache.resolve_period_key(period_key, period_days),
        }

    @stats_cache.cache_stats(kind="participation")
    async def get_participation_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        start_date = now - timedelta(days=period_days)

        rows = await self.stats_repo.get_participation_stats_raw(
            user_id=user_id,
            window_start=start_date,
            now=now,
        )

        events_count = len(rows)
        total_hours = 0.0
        unique_groups = set()
        recent_items: list[dict[str, Any]] = []

        for row in rows:
            duration = (row.ends_at - row.starts_at).total_seconds() / 3600
            total_hours += max(0.0, duration)
            if row.event_type:
                unique_groups.add(row.event_type)
            if len(recent_items) < 5:
                recent_items.append(
                    {"title": row.title, "date": row.starts_at.isoformat()}
                )

        return {
            "events": events_count,
            "hours": round(total_hours, 2),
            "groups": len(unique_groups),
            # LOW-W19: `trend` is a placeholder value (1 if there are any events,
            # else 0).  A real trend requires comparing participation counts
            # against the previous period.  Replace with:
            #   previous_count = await self.stats_repo.get_participation_count(
            #       user_id, previous_start, window_start)
            #   trend = events_count - previous_count
            # once the previous-period query is implemented in UserStatsRepository.
            "trend": 1 if events_count > 0 else 0,
            "period_key": stats_cache.resolve_period_key(period_key, period_days),
            "recent": recent_items,
        }
