"""Utilities for generating iCalendar exports."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.localization import (
    resolve_weekday_index,
    translate,
    translate_lesson_type,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import app.models as models
    from app.schemas.dtos import ScheduleDTO

    # A lesson reaches this generator either as the mapped row or as the DTO
    # the schedule service returns (including from cache); every field is read
    # through ``getattr``, so both shapes work and both are declared.
    LessonLike = models.Schedule | ScheduleDTO


def _weekday_index(value: str | None) -> int | None:
    return resolve_weekday_index(value)


def _ensure_time(value: datetime | time | None) -> time | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.time()
    # Schedule timestamps are reference-week campus wall times. Their stored
    # UTC offset is a persistence detail, not the timezone of the recurrence.
    return value.replace(tzinfo=None, fold=0)


def _resolve_campus_occurrence(
    lesson_date: date, lesson_time: time, campus_timezone: ZoneInfo
) -> datetime | None:
    """Resolve one weekly wall time; skip DST gaps and choose the first fold."""
    local_naive = datetime.combine(
        lesson_date, lesson_time.replace(tzinfo=None, fold=0)
    )
    occurrence = local_naive.replace(tzinfo=campus_timezone, fold=0)
    round_trip = (
        occurrence.astimezone(UTC).astimezone(campus_timezone).replace(tzinfo=None)
    )
    if round_trip != local_naive:
        return None
    return occurrence


def _escape(value: str | None) -> str:
    if not value:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _format_dt(dt: datetime) -> str:
    if dt.tzinfo is UTC:
        return dt.strftime("%Y%m%dT%H%M%SZ")
    if dt.tzinfo:
        aware = dt.astimezone(UTC)
        return aware.strftime("%Y%m%dT%H%M%SZ")
    return dt.strftime("%Y%m%dT%H%M%S")


def _iter_lesson_dates(
    weekday_idx: int,
    parity: str,
    weeks: int,
    *,
    start_monday: date,
) -> Iterable[date]:
    parity_normalized = parity.lower()
    for week_offset in range(weeks):
        lesson_date = start_monday + timedelta(days=weekday_idx + week_offset * 7)
        week_number = lesson_date.isocalendar().week
        actual_parity = "odd" if week_number % 2 else "even"
        if parity_normalized in {"odd", "even"} and parity_normalized != actual_parity:
            continue
        yield lesson_date


def generate_schedule_ics(
    group: models.Group,
    lessons: Sequence[LessonLike],
    *,
    weeks: int = 16,
    locale: str | None = None,
) -> str:
    """Generate an iCalendar representation for the provided schedule."""

    now = datetime.now(UTC)
    campus_timezone = ZoneInfo(settings.campus_timezone)
    today = now.astimezone(campus_timezone).date()
    start_monday = today - timedelta(days=today.weekday())

    group_name = getattr(group, "name", None)
    calendar_name = (
        translate("schedule.ics.calendar_name", locale=locale, group=group_name)
        if group_name
        else translate("schedule.ics.calendar_name_generic", locale=locale)
    )

    prodid = translate("schedule.ics.prodid", locale=locale)

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        f"PRODID:{_escape(prodid)}",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"NAME:{_escape(calendar_name)}",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]

    dtstamp = _format_dt(now)
    for lesson in lessons:
        weekday_idx = _weekday_index(getattr(lesson, "weekday", None))
        start_time = _ensure_time(getattr(lesson, "start_time", None))
        end_time = _ensure_time(getattr(lesson, "end_time", None))

        if weekday_idx is None or start_time is None or end_time is None:
            continue

        parity = getattr(lesson, "parity", "both") or "both"
        subject = getattr(lesson, "subject", None) or translate(
            "schedule.ics.lesson_default_subject", locale=locale
        )
        lesson_type = getattr(lesson, "lesson_type", None)
        lesson_type_display = translate_lesson_type(lesson_type, locale=locale)
        summary = (
            subject if not lesson_type_display else f"{subject} ({lesson_type_display})"
        )
        teacher = getattr(lesson, "teacher", None)
        room = getattr(lesson, "room", None)

        for lesson_date in _iter_lesson_dates(
            weekday_idx,
            parity,
            weeks,
            start_monday=start_monday,
        ):
            start_local = _resolve_campus_occurrence(
                lesson_date, start_time, campus_timezone
            )
            end_local = _resolve_campus_occurrence(
                lesson_date, end_time, campus_timezone
            )
            if start_local is None or end_local is None:
                continue
            start_dt = start_local.astimezone(UTC)
            end_dt = end_local.astimezone(UTC)
            uid = (
                "lesson-"
                f"{getattr(lesson, 'id', 'x')}-"
                f"{lesson_date.strftime('%Y%m%d')}@university-ecosystem"
            )
            description_parts = []
            if lesson_type_display:
                description_parts.append(
                    translate(
                        "schedule.ics.description.lesson_type",
                        locale=locale,
                        lesson_type=lesson_type_display,
                    )
                )
            if teacher:
                description_parts.append(
                    translate(
                        "schedule.ics.description.teacher",
                        locale=locale,
                        teacher=teacher,
                    )
                )
            if room:
                description_parts.append(
                    translate(
                        "schedule.ics.description.room",
                        locale=locale,
                        room=room,
                    )
                )
            if parity and parity.lower() in {"odd", "even"}:
                parity_key = (
                    "schedule.ics.description.parity_odd"
                    if parity.lower() == "odd"
                    else "schedule.ics.description.parity_even"
                )
                description_parts.append(translate(parity_key, locale=locale))
            description = "\\n".join(description_parts) if description_parts else ""

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{dtstamp}",
                    f"SUMMARY:{_escape(summary)}",
                    f"DTSTART:{_format_dt(start_dt)}",
                    f"DTEND:{_format_dt(end_dt)}",
                ]
            )

            if room:
                lines.append(f"LOCATION:{_escape(room)}")
            if description:
                lines.append(f"DESCRIPTION:{_escape(description)}")

            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
