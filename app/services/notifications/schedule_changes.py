"""Notifications for changed or cancelled lessons (topic ``schedule.changed``).

The schedule service records ``SCHEDULE_UPDATED`` and ``SCHEDULE_DELETED``
domain events with JSON snapshots of the lesson before and after the change.
The outbox delivers them to these handlers, which notify the active members of
every affected group once per meaningful change.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.localization import DEFAULT_LOCALE, SUPPORTED_LOCALES, translate
from app.models import Notification, User
from app.services.notification_templates import render_notification_template
from app.services.notifications.delivery import create_notifications_for_users

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

SCHEDULE_CHANGE_TOPIC = "schedule.changed"
_WEEKDAYS = frozenset(
    {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
)


def is_significant_change(
    previous: Mapping[str, Any], current: Mapping[str, Any] | None
) -> bool:
    """A cancellation always matters; an update matters when any field differs."""
    if current is None:
        return bool(previous)
    return dict(previous) != dict(current)


def _group_ids(*states: Mapping[str, Any] | None) -> list[uuid.UUID]:
    groups: list[uuid.UUID] = []
    for state in states:
        raw = (state or {}).get("group_id")
        if not raw:
            continue
        try:
            group_id = uuid.UUID(str(raw))
        except ValueError:
            continue
        if group_id not in groups:
            groups.append(group_id)
    return groups


def _clock(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M")
    except ValueError:
        return None


def _weekday(value: Any, locale: str) -> str | None:
    name = str(value or "").strip().lower()
    if name in _WEEKDAYS:
        return translate(f"schedule.weekday.{name}", locale=locale)
    return None


def _render(
    state: Mapping[str, Any], *, cancelled: bool, schedule_id: str, locale: str
) -> dict[str, Any] | None:
    start, end = _clock(state.get("start_time")), _clock(state.get("end_time"))
    summary = (
        translate("notifications.schedule.change.cancelled", locale=locale)
        if cancelled
        else translate("notifications.schedule.change.updated", locale=locale)
    )
    return render_notification_template(
        "schedule.change",
        {
            "subject": state.get("subject"),
            "summary": summary,
            "teacher": state.get("teacher"),
            "room": state.get("room"),
            "date": _weekday(state.get("weekday"), locale),
            "time": f"{start}–{end}" if start and end else start,
            "url": "/schedule",
            "schedule_id": schedule_id,
        },
        locale=locale,
    )


async def _active_members(
    db: AsyncDatabaseSession, group_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    rows = await db.execute(
        select(User.id)
        .where(User.group_id.in_(group_ids))
        .where(User.is_active.is_(True))
    )
    return list(rows.scalars().all())


async def _already_notified(
    db: AsyncDatabaseSession, user_ids: list[uuid.UUID], dedupe_key: str
) -> set[uuid.UUID]:
    rows = await db.execute(
        select(Notification.user_id)
        .where(Notification.user_id.in_(user_ids))
        .where(Notification.dedupe_key == dedupe_key)
    )
    return set(rows.scalars().all())


async def notify_about_schedule_change(
    db: AsyncDatabaseSession,
    *,
    schedule_id: uuid.UUID | str,
    previous: Mapping[str, Any],
    current: Mapping[str, Any] | None,
) -> int:
    """Notify the affected groups about a changed (or cancelled) lesson."""
    if not is_significant_change(previous, current):
        return 0
    group_ids = _group_ids(previous, current)
    if not group_ids:
        return 0
    members = await _active_members(db, group_ids)
    if not members:
        return 0
    identifier = str(schedule_id)
    # One notification per distinct change: a redelivered outbox event finds
    # the key it already wrote and notifies nobody twice.
    fingerprint = hashlib.sha256(
        json.dumps(
            {"previous": previous, "current": current}, sort_keys=True, default=str
        ).encode()
    ).hexdigest()[:16]
    dedupe_key = f"schedule-change:{identifier}:{fingerprint}"
    notified = await _already_notified(db, members, dedupe_key)
    user_ids = [user_id for user_id in members if user_id not in notified]
    if not user_ids:
        return 0

    cancelled = current is None
    state = previous if current is None else current
    rendered = {
        locale: _render(
            state, cancelled=cancelled, schedule_id=identifier, locale=locale
        )
        for locale in sorted(SUPPORTED_LOCALES)
    }
    default = rendered.get(DEFAULT_LOCALE) or {}
    return await create_notifications_for_users(
        db,
        title=str(default.get("title", "")),
        body=str(default.get("body", "")),
        title_translations={
            locale: str(payload["title"])
            for locale, payload in rendered.items()
            if payload and payload.get("title")
        },
        body_translations={
            locale: str(payload["body"])
            for locale, payload in rendered.items()
            if payload and payload.get("body")
        },
        type="schedule.change",
        url="/schedule",
        tag=str(default.get("tag") or f"schedule-change:{identifier}"),
        dedupe_key=dedupe_key,
        payload_data=dict(default.get("data") or {}),
        user_ids=user_ids,
        topic=SCHEDULE_CHANGE_TOPIC,
    )


__all__ = [
    "SCHEDULE_CHANGE_TOPIC",
    "is_significant_change",
    "notify_about_schedule_change",
]
