"""Schedule reminder notifications.

This module handles building and generating schedule reminder notifications
for upcoming lessons.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import UUID, literal_column, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession as SQLAlchemyAsyncSession

from app.core.config import settings
from app.core.localization import SUPPORTED_LOCALES, translate, translate_lesson_type
from app.core.tenant import (
    bypass_rls_ctx,
    get_bypass_rls,
    get_current_tenant,
    tenant_id_ctx,
)
from app.models import Group, Notification, Schedule, User
from app.models.tenant import Tenant
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

    from sqlalchemy.sql import Select

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


def _active_users_in_scope(
    stmt: Select[Any], *, tenant: uuid.UUID | None, group_id: uuid.UUID
) -> Select[Any]:
    """Recheck recipient ownership when the notification producer filters users."""
    return only_active_users(stmt).where(
        User.tenant_id == tenant, User.group_id == group_id
    )


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
    dialect_name: str | None
    if isinstance(cast(Any, db), SQLAlchemyAsyncSession):
        dialect_name = db.get_bind().dialect.name
        if dialect_name not in {"postgresql", "sqlite"}:
            raise RuntimeError("Unsupported reminder database dialect")
    else:
        # Lightweight test doubles do not all expose a bound dialect.
        bind = getattr(db, "bind", None)
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    tenant_scoped = dialect_name == "postgresql"
    if not tenant_scoped:
        return await _generate_schedule_reminders(db, window_minutes=window_minutes)

    # A privileged worker can inherit unrelated context, and its bypass role sees
    # every row regardless of the GUC. Individual writes establish ownership
    # from the database rows, never from that inherited bypass context.
    previous_tenant = "" if get_bypass_rls() else get_current_tenant()
    tenant_token = tenant_id_ctx.set(previous_tenant)
    bypass_token = bypass_rls_ctx.set(False)
    try:
        previous_setting = await db.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        )
        previous_database_tenant = previous_setting.scalar_one_or_none() or ""
        try:
            return await _generate_schedule_reminders(
                db, window_minutes=window_minutes, tenant_scoped=True
            )
        finally:
            # The session may remain in use after this function, even when a
            # non-database error interrupts the scan. Preserve the original
            # exception if a failed transaction prevents GUC restoration.
            pending_error = sys.exception()
            try:
                await db.execute(
                    text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                    {"tenant_id": previous_database_tenant},
                )
            except (SQLAlchemyError, OSError):
                if pending_error is None:
                    raise
                pending_error.add_note(
                    "Tenant context restoration failed; roll back the transaction"
                )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


async def _generate_schedule_reminders(
    db: AsyncSession, *, window_minutes: int, tenant_scoped: bool = False
) -> int:
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
    if tenant_scoped:
        # The tenant columns on schedule and groups belong to the baseline
        # migration, not the ORM model. Read them without changing metadata.
        schedule_tenant = literal_column("schedule.tenant_id", UUID(as_uuid=True))
        group_tenant = literal_column("groups.tenant_id", UUID(as_uuid=True))
        owned_query = (
            select(Schedule, schedule_tenant, group_tenant)
            .join(Group, Group.id == Schedule.group_id)
            .join(Tenant, Tenant.id == schedule_tenant)
            .where(Schedule.weekday.in_(weekday_values), Tenant.is_active.is_(True))
        )
        schedule_rows = await db.execute(owned_query)
        owned_schedules = [
            (schedule, tenant)
            for schedule, tenant, group_owner in schedule_rows
            if tenant is not None and tenant == group_owner
        ]
    else:
        q = select(Schedule).where(Schedule.weekday.in_(weekday_values))
        owned_schedules = [
            (schedule, None) for schedule in (await db.execute(q)).scalars().all()
        ]
    occurrences_by_id: dict[uuid.UUID, dt.datetime] = {}
    matching_schedules: list[tuple[Schedule, uuid.UUID | None]] = []
    for schedule, tenant in owned_schedules:
        occurrence = _schedule_occurrence_in_window(
            schedule,
            now_utc=now_utc,
            window_end_utc=window_end_utc,
            campus_timezone=campus_timezone,
        )
        if occurrence is None:
            continue
        matching_schedules.append((schedule, tenant))
        occurrences_by_id[schedule.id] = occurrence
    schedules = matching_schedules
    if not schedules:
        return 0

    schedules_by_group: dict[tuple[uuid.UUID, uuid.UUID | None], list[Schedule]] = (
        defaultdict(list)
    )
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
    for schedule, tenant in schedules:
        schedules_by_group[(schedule.group_id, tenant)].append(schedule)
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

    group_ids = list({group_id for group_id, _tenant in schedules_by_group.keys()})
    if not group_ids:
        return 0

    user_columns = (
        (User.id, User.group_id, User.tenant_id)
        if tenant_scoped
        else (User.id, User.group_id)
    )
    users_stmt = (
        select(*user_columns)
        .where(User.group_id.in_(group_ids))
        .where(User.is_active.is_(True))
    )
    user_rows = await db.execute(users_stmt)
    group_users: dict[tuple[uuid.UUID, uuid.UUID | None], set[uuid.UUID]] = defaultdict(
        set
    )
    for row in user_rows:
        user_id, group_id = row[:2]
        tenant = row[2] if tenant_scoped else None
        if user_id is None or group_id is None:
            continue
        if tenant_scoped and tenant is None:
            continue
        group_users[(group_id, tenant)].add(user_id)

    if not any(group_users.values()):
        return 0

    dup_since = now_utc - dt.timedelta(minutes=30)
    all_user_ids = {uid for users in group_users.values() for uid in users}
    existing_by_dedupe: dict[tuple[str, uuid.UUID | None], set[uuid.UUID]] = (
        defaultdict(set)
    )
    if dedupe_keys and all_user_ids:
        notification_columns = (
            (
                Notification.user_id,
                Notification.dedupe_key,
                literal_column("notifications.tenant_id", UUID(as_uuid=True)),
            )
            if tenant_scoped
            else (Notification.user_id, Notification.dedupe_key)
        )
        existing_stmt = (
            select(*notification_columns)
            .where(
                Notification.user_id.in_(all_user_ids),
                Notification.url == "/schedule",
                Notification.created_at >= dup_since,
                Notification.dedupe_key.in_(dedupe_keys),
            )
            .distinct()
        )
        existing_rows = await db.execute(existing_stmt)
        for row in existing_rows:
            user_id, dedupe_key = row[:2]
            if user_id is None or dedupe_key is None:
                continue
            existing_tenant = row[2] if tenant_scoped else None
            existing_by_dedupe[(str(dedupe_key), existing_tenant)].add(user_id)

    action_title = translate("notifications.actions.open_schedule", locale=None)
    total_created = 0
    for (group_id, tenant), group_schedules in schedules_by_group.items():
        user_ids = group_users.get((group_id, tenant))
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
            already_notified = existing_by_dedupe.get((key_for_dedupe, tenant), set())
            to_notify = [uid for uid in user_ids if uid not in already_notified]
            if not to_notify:
                continue
            tenant_token = (
                tenant_id_ctx.set(str(tenant)) if tenant is not None else None
            )
            try:
                if tenant_scoped:
                    await db.execute(
                        text(
                            "SELECT set_config('app.current_tenant', :tenant_id, true)"
                        ),
                        {"tenant_id": str(tenant)},
                    )

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
                    user_filter=(
                        partial(
                            _active_users_in_scope, tenant=tenant, group_id=group_id
                        )
                        if tenant_scoped
                        else only_active_users
                    ),
                )
            finally:
                if tenant_token is not None:
                    tenant_id_ctx.reset(tenant_token)
            existing_by_dedupe[(key_for_dedupe, tenant)].update(to_notify)
    return total_created
