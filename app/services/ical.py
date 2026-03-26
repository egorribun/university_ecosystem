"""Utilities for generating iCalendar exports."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from app.core.localization import (
    resolve_weekday_index,
    translate,
    translate_lesson_type,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import app.models as models


def _weekday_index(value: str | None) -> int | None:
    return resolve_weekday_index(value)


def _ensure_time(value: datetime | time | None) -> time | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        # Always return naive time for consistent iCal generation
        return value.time()
    return value


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
    current_week_parity: str,
) -> Iterable[date]:
    step = 1
    offset = 0
    parity_normalized = parity.lower()
    if parity_normalized in {"odd", "even"}:
        step = 2
        if parity_normalized != current_week_parity:
            offset = 1
    for week in range(offset, weeks, step):
        yield start_monday + timedelta(days=weekday_idx + week * 7)


def generate_schedule_ics(
    group: models.Group,
    lessons: Sequence[models.Schedule],
    *,
    weeks: int = 16,
    locale: str | None = None,
) -> str:
    """Generate an iCalendar representation for the provided schedule."""

    now = datetime.now(UTC)
    today = now.date()
    start_monday = today - timedelta(days=today.weekday())
    current_week_number = today.isocalendar()[1]
    current_week_parity = "odd" if current_week_number % 2 else "even"

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
            current_week_parity=current_week_parity,
        ):
            start_dt = datetime.combine(lesson_date, start_time)
            end_dt = datetime.combine(lesson_date, end_time)
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
