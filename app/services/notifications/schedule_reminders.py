"""Schedule reminder notifications.

This module handles building and generating schedule reminder notifications
for upcoming lessons.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.core.localization import SUPPORTED_LOCALES, translate, translate_lesson_type
from app.models import Notification, Schedule, User
from app.services.notification_templates import render_notification_template
from app.services.notifications.core import (
    _ROOM_LABEL_PREFIXES,
    _ensure_aware,
)
from app.services.notifications.delivery import (
    create_notifications_for_users,
    only_active_users,
)

if TYPE_CHECKING:
    import uuid

    from app.core.protocols import AsyncDatabaseSession as AsyncSession


def _resolve_schedule_occurrence(
    schedule: Schedule,
    occurrence_date: dt.date,
    campus_timezone: ZoneInfo,
) -> dt.datetime | None:
    """Resolve a stored weekly wall time to one valid campus-time occurrence.

    The schedule API stores a reference-week datetime, so its calendar date and
    timezone are intentionally ignored here. For an ambiguous fall-back time we
    choose the first occurrence; a nonexistent spring-forward time is skipped.
    """
    stored_start = getattr(schedule, "start_time", None)
    if isinstance(stored_start, datetime):
        wall_time = stored_start.timetz().replace(tzinfo=None, fold=0)
    else:
        return None

    local_naive = datetime.combine(occurrence_date, wall_time)
    occurrence = local_naive.replace(tzinfo=campus_timezone, fold=0)
    round_trip = (
        occurrence.astimezone(UTC).astimezone(campus_timezone).replace(tzinfo=None)
    )
    if round_trip != local_naive:
        return None
    return occurrence


def _schedule_occurrence_in_window(
    schedule: Schedule,
    *,
    now_utc: dt.datetime,
    window_end_utc: dt.datetime,
    campus_timezone: ZoneInfo,
) -> dt.datetime | None:
    """Return the next matching weekly occurrence in the UTC reminder window."""
    local_start = now_utc.astimezone(campus_timezone)
    local_end = window_end_utc.astimezone(campus_timezone)
    stored_weekday = str(getattr(schedule, "weekday", "")).strip().lower()
    stored_parity = str(getattr(schedule, "parity", None) or "both").strip().lower()

    day_count = (local_end.date() - local_start.date()).days
    for day_offset in range(day_count + 1):
        occurrence_date = local_start.date() + dt.timedelta(days=day_offset)
        weekday_name = occurrence_date.strftime("%A").lower()
        if stored_weekday not in {weekday_name, str(occurrence_date.weekday())}:
            continue

        week_number = occurrence_date.isocalendar().week
        occurrence_parity = "odd" if week_number % 2 else "even"
        if stored_parity not in {"", "both", occurrence_parity}:
            continue

        occurrence = _resolve_schedule_occurrence(
            schedule, occurrence_date, campus_timezone
        )
        if occurrence is None:
            continue
        occurrence_utc = occurrence.astimezone(UTC)
        if now_utc <= occurrence_utc <= window_end_utc:
            return occurrence
    return None


def build_schedule_reminder_message(
    lesson: Schedule,
    *,
    locale: str | None = None,
    occurrence_at: dt.datetime | None = None,
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
    dict[str, str],
    dict[str, str],
    str,
]:
    """Build a schedule reminder message for a lesson.

    Returns a tuple of:
    - title
    - body
    - tag
    - data payload
    - title translations
    - body translations
    - dedupe key
    """
    start_dt = _ensure_aware(
        occurrence_at
        if occurrence_at is not None
        else getattr(lesson, "start_time", None)
    )
    start_local = start_dt.astimezone(ZoneInfo(settings.campus_timezone))
    lesson_type_raw = getattr(lesson, "lesson_type", None)
    when_line = f"{start_local.strftime('%d.%m')} · {start_local.strftime('%H:%M')}"

    schedule_id = getattr(lesson, "id", None)
    timestamp_part = str(int(start_dt.timestamp())) if start_dt else "timestamp"

    cache: dict[str, tuple[str, str, str, dict[str, Any], str]] = {}

    def _render(locale_option: str | None) -> tuple[str, str, str, dict[str, Any], str]:
        cache_key = locale_option if locale_option is not None else "__default__"
        if cache_key in cache:
            return cache[cache_key]

        lesson_type_display = translate_lesson_type(
            lesson_type_raw, locale=locale_option
        )
        payload_input = {
            "subject": getattr(lesson, "subject", None),
            "group": getattr(getattr(lesson, "group", None), "name", None),
            "lesson_type": lesson_type_display or lesson_type_raw,
            "teacher": getattr(lesson, "teacher", None),
            "room": getattr(lesson, "room", None),
            "starts_at": start_dt.isoformat(),
            "date": start_local.strftime("%d.%m"),
            "time": start_local.strftime("%H:%M"),
            "url": "/schedule",
            "lesson_id": getattr(lesson, "id", None),
        }
        template = render_notification_template(
            "schedule.reminder", payload_input, locale=locale_option
        )
        subject_value = getattr(lesson, "subject", None)
        if subject_value:
            default_title = translate(
                "notifications.schedule.reminder.title_with_subject",
                locale=locale_option,
                subject=subject_value,
            )
        else:
            default_title = translate(
                "notifications.schedule.reminder.title", locale=locale_option
            )
        summary_parts: list[str] = []
        if lesson_type_display:
            summary_parts.append(lesson_type_display)
        elif lesson_type_raw:
            summary_parts.append(str(lesson_type_raw))
        room_value = getattr(lesson, "room", None)
        if room_value:
            room_text = str(room_value)
            normalized = room_text.strip().lower()
            if any(normalized.startswith(prefix) for prefix in _ROOM_LABEL_PREFIXES):
                summary_parts.append(room_text)
            else:
                summary_parts.append(
                    translate(
                        "notifications.schedule.room_label",
                        locale=locale_option,
                        room=room_text,
                    )
                )
        if getattr(lesson, "teacher", None):
            summary_parts.append(str(lesson.teacher))
        default_lines = [
            translate(
                "notifications.schedule.reminder.start_line",
                locale=locale_option,
                start=when_line,
            )
        ]
        if summary_parts:
            default_lines.append(" · ".join(summary_parts))
        else:
            default_lines.append(
                translate(
                    "notifications.schedule.reminder.no_details", locale=locale_option
                )
            )
        default_body = "\n".join(default_lines)
        identifier_component = str(schedule_id) if schedule_id is not None else "lesson"
        default_tag = f"schedule-reminder:{identifier_component}:{timestamp_part}"
        default_data: dict[str, Any] = {
            "url": "/schedule",
            "category": "schedule",
            "lessonId": getattr(lesson, "id", None),
            "subject": getattr(lesson, "subject", None),
            "groupId": getattr(lesson, "group_id", None),
            "lessonType": lesson_type_display or lesson_type_raw,
            "lessonTypeRaw": lesson_type_raw,
            "teacher": getattr(lesson, "teacher", None),
            "room": getattr(lesson, "room", None),
            "startText": when_line,
            "startsAt": start_dt.isoformat(),
            "startTimestamp": int(start_dt.timestamp()),
        }
        if template:
            title_value = str(template.get("title") or default_title)
            body_value = str(template.get("body") or default_body)
            tag_value = str(template.get("tag") or default_tag)
            template_data = template.get("data")
            merged_data = {**default_data}
            if isinstance(template_data, Mapping):
                merged_data.update(template_data)
        else:
            title_value, body_value, tag_value, merged_data = (
                default_title,
                default_body,
                default_tag,
                default_data,
            )
        filtered_data = {
            key: value for key, value in merged_data.items() if value not in (None, "")
        }
        dedupe_candidate = (
            template.get("dedupeKey")
            if template and template.get("dedupeKey") not in (None, "")
            else (
                template.get("dedupe_key")
                if template and template.get("dedupe_key") not in (None, "")
                else tag_value
            )
        )
        dedupe_value = (
            str(dedupe_candidate) if dedupe_candidate not in (None, "") else ""
        )
        result = (title_value, body_value, tag_value, filtered_data, dedupe_value)
        cache[cache_key] = result
        return result

    title, body, tag, data_payload, dedupe_value = _render(locale)
    title_translations: dict[str, str] = {}
    body_translations: dict[str, str] = {}
    for locale_code in SUPPORTED_LOCALES:
        localized_title, localized_body, _, _, _ = _render(locale_code)
        if localized_title:
            title_translations[locale_code] = localized_title
        if localized_body:  # pragma: no branch - body always includes the start line
            body_translations[locale_code] = localized_body

    return (
        title,
        body,
        tag,
        data_payload,
        title_translations,
        body_translations,
        dedupe_value,
    )


async def generate_schedule_reminders(
    db: AsyncSession, *, window_minutes: int = 6
) -> int:
    """Generate schedule reminder notifications for upcoming lessons."""
    now_utc = dt.datetime.now(UTC)
    window_end_utc = now_utc + dt.timedelta(minutes=window_minutes)
    campus_timezone = ZoneInfo(settings.campus_timezone)
    local_start = now_utc.astimezone(campus_timezone)
    local_end = window_end_utc.astimezone(campus_timezone)
    day_count = (local_end.date() - local_start.date()).days
    weekday_values: set[str] = set()
    for day_offset in range(day_count + 1):
        occurrence_date = local_start.date() + dt.timedelta(days=day_offset)
        weekday_values.add(occurrence_date.strftime("%A").lower())
        weekday_values.add(str(occurrence_date.weekday()))

    # Schedule rows store one reference-week wall time, not a dated occurrence.
    # Filter by relevant campus weekdays in SQL, then resolve recurrence and
    # parity against each concrete local date below.
    q = select(Schedule).where(Schedule.weekday.in_(weekday_values))
    schedules = (await db.execute(q)).scalars().all()
    occurrences_by_id: dict[uuid.UUID, dt.datetime] = {}
    matching_schedules: list[Schedule] = []
    for schedule in schedules:
        occurrence = _schedule_occurrence_in_window(
            schedule,
            now_utc=now_utc,
            window_end_utc=window_end_utc,
            campus_timezone=campus_timezone,
        )
        if occurrence is None:
            continue
        matching_schedules.append(schedule)
        occurrences_by_id[schedule.id] = occurrence
    schedules = matching_schedules
    if not schedules:
        return 0

    schedules_by_group: dict[uuid.UUID, list[Schedule]] = defaultdict(list)
    message_payloads: dict[
        uuid.UUID,
        tuple[
            str,
            str,
            str,
            dict[str, Any],
            dict[str, str],
            dict[str, str],
            str,
        ],
    ] = {}
    for schedule in schedules:
        schedules_by_group[schedule.group_id].append(schedule)
        payload = build_schedule_reminder_message(
            schedule, occurrence_at=occurrences_by_id[schedule.id]
        )
        message_payloads[schedule.id] = payload
    dedupe_keys: set[str] = {
        str(key)
        for key in (
            payload[6] or payload[2] or payload[0]
            for payload in message_payloads.values()
        )
        if key not in (None, "")
    }

    group_ids = list(schedules_by_group.keys())
    if not group_ids:
        return 0

    users_stmt = (
        select(User.id, User.group_id)
        .where(User.group_id.in_(group_ids))
        .where(User.is_active.is_(True))
    )
    user_rows = await db.execute(users_stmt)
    group_users: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for user_id, group_id in user_rows:
        if user_id is None or group_id is None:
            continue
        group_users[group_id].add(user_id)

    if not any(group_users.values()):
        return 0

    dup_since = now_utc - dt.timedelta(minutes=30)
    all_user_ids = {uid for users in group_users.values() for uid in users}
    existing_by_dedupe: dict[str, set[uuid.UUID]] = defaultdict(set)
    if dedupe_keys and all_user_ids:
        existing_stmt = (
            select(Notification.user_id, Notification.dedupe_key)
            .where(
                Notification.user_id.in_(all_user_ids),
                Notification.url == "/schedule",
                Notification.created_at >= dup_since,
                Notification.dedupe_key.in_(dedupe_keys),
            )
            .distinct()
        )
        existing_rows = await db.execute(existing_stmt)
        for user_id, dedupe_key in existing_rows:
            if user_id is None or dedupe_key is None:
                continue
            existing_by_dedupe[str(dedupe_key)].add(user_id)

    action_title = translate("notifications.actions.open_schedule", locale=None)
    total_created = 0
    for group_id, group_schedules in schedules_by_group.items():
        user_ids = group_users.get(group_id)
        if not user_ids:
            continue
        for schedule in group_schedules:
            (
                title,
                body,
                tag,
                data_payload,
                title_translations,
                body_translations,
                dedupe_key,
            ) = message_payloads[schedule.id]
            key_for_dedupe = dedupe_key or tag or title
            already_notified = existing_by_dedupe.get(key_for_dedupe, set())
            to_notify = [uid for uid in user_ids if uid not in already_notified]
            if not to_notify:
                continue
            total_created += await create_notifications_for_users(
                db,
                title=title,
                body=body,
                title_translations=title_translations,
                body_translations=body_translations,
                type="schedule.reminder",
                url="/schedule",
                tag=tag,
                dedupe_key=key_for_dedupe,
                actions=[
                    {
                        "action": "open-schedule",
                        "title": action_title,
                        "url": "/schedule",
                    }
                ],
                payload_data=data_payload,
                user_ids=to_notify,
                topic="schedule.changed",
                user_filter=only_active_users,
            )
            existing_by_dedupe[key_for_dedupe].update(to_notify)
    return total_created
