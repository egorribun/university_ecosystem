"""Schedule reminder notifications.

This module handles building and generating schedule reminder notifications
for upcoming lessons.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select

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


def build_schedule_reminder_message(
    lesson: Schedule, *, locale: str | None = None
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
    start_dt = _ensure_aware(getattr(lesson, "start_time", None))
    start_local = start_dt.astimezone()
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
    now = dt.datetime.now(UTC)
    soon = now + dt.timedelta(minutes=window_minutes)
    # HIGH-W19: add weekday and week-parity filters so reminders are only sent for
    # lessons that actually occur today; without this every stored schedule row
    # whose start_time falls in the window triggers a notification regardless of
    # whether the lesson recurs on the current day-of-week or week parity.
    current_weekday_name = now.strftime("%A").lower()  # e.g. "monday"
    current_weekday_int = now.weekday()  # 0=Monday … 6=Sunday
    # ISO week number: odd → "odd" / "нечет", even → "even" / "чет"
    current_week_number = now.isocalendar()[1]
    current_parity = "odd" if current_week_number % 2 != 0 else "even"

    weekday_filter = (Schedule.weekday == current_weekday_name) | (
        Schedule.weekday == str(current_weekday_int)
    )
    parity_filter = (
        Schedule.parity.is_(None)
        | (Schedule.parity == "")
        | (Schedule.parity == current_parity)
        | (Schedule.parity == "both")
    )
    q = select(Schedule).where(
        and_(
            Schedule.start_time >= now,
            Schedule.start_time <= soon,
            weekday_filter,
            parity_filter,
        )
    )
    schedules = (await db.execute(q)).scalars().all()
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
        payload = build_schedule_reminder_message(schedule)
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

    dup_since = now - dt.timedelta(minutes=30)
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
