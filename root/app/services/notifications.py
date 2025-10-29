import asyncio
import datetime as dt
import logging
import re
from collections import defaultdict
from datetime import UTC
from html import unescape
from textwrap import shorten
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session as _async_session
from app.localization import (
    SUPPORTED_LOCALES,
    localized_text,
    normalize_locale,
    resolve_locale,
    translate,
    translate_lesson_type,
)
from app.models.models import (
    Event,
    News,
    Notification,
    NotificationDelivery,
    PushSubscription,
    Schedule,
    User,
)
from app.services import stats_cache
from app.services.notification_templates import render_notification_template
from app.services.push_schema import ensure_push_subscription_schema
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import WebPushResult, send_web_push


def _current_local_time(user: User | None = None) -> dt.time:
    tz = UTC
    if user is not None:
        raw = getattr(user, "timezone", None)
        if isinstance(raw, str):
            candidate = raw.strip()
            if candidate:
                try:
                    tz = ZoneInfo(candidate)
                except (ZoneInfoNotFoundError, ValueError):
                    tz = UTC
    now = dt.datetime.now(tz)
    current = now.timetz()
    if current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return current


logger = logging.getLogger(__name__)


def _room_label_prefixes() -> set[str]:
    prefixes: set[str] = set()
    for locale_code in SUPPORTED_LOCALES:
        template = translate(
            "notifications.schedule.room_label", locale=locale_code, room=""
        )
        for variant in (template, template.replace(".", "")):
            normalized = variant.strip().lower()
            if normalized:
                prefixes.add(normalized)
    prefixes.update({"room", "aud"})
    return prefixes


_ROOM_LABEL_PREFIXES = _room_label_prefixes()


_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: Any, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        return shorten(text, width=limit, placeholder="…")
    return text


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_translation_map(
    translations: Mapping[str, Any] | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not translations:
        return normalized
    for key, value in translations.items():
        if value is None:
            continue
        locale_key = str(key).strip().lower()
        if locale_key not in SUPPORTED_LOCALES:
            continue
        text = _coerce_optional_text(value)
        if text is None:
            continue
        normalized[locale_key] = text
    return normalized


def _build_delivery_row(
    notification_id: int,
    *,
    status: str,
    channel: str = "webpush",
    attempted_at: dt.datetime | None = None,
    delivered: bool = False,
    status_code: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    attempt_ts = attempted_at or dt.datetime.now(UTC)
    row: dict[str, Any] = {
        "notification_id": int(notification_id),
        "channel": channel,
        "status": status,
        "attempted_at": attempt_ts,
        "delivered_at": attempt_ts if delivered else None,
    }
    if status_code is not None:
        row["status_code"] = int(status_code)
    if detail:
        row["detail"] = str(detail)
    return row


async def cleanup_stale_notifications(
    *,
    db: AsyncSession | None = None,
    retention_days: int | None = None,
    now: dt.datetime | None = None,
) -> tuple[int, int]:
    """Remove notifications and deliveries older than the retention window.

    Unread notifications are preserved regardless of age. Returns a tuple with
    counts of deleted notifications and deliveries respectively.
    """

    if retention_days is None:
        retention_days = getattr(settings, "notifications_retention_days", 0) or 0

    retention_days = int(retention_days)

    if retention_days <= 0:
        return (0, 0)

    now_value = now or dt.datetime.now(UTC)

    if db is None:
        async with _async_session() as session:
            return await cleanup_stale_notifications(
                db=session, retention_days=retention_days, now=now_value
            )

    cutoff = now_value - dt.timedelta(days=int(retention_days))

    deliveries_stmt = delete(NotificationDelivery).where(
        NotificationDelivery.attempted_at < cutoff
    )
    notifications_stmt = delete(Notification).where(
        Notification.created_at < cutoff,
        or_(Notification.read.is_(True), Notification.read_at.is_not(None)),
    )

    deliveries_result = await db.execute(deliveries_stmt)
    notifications_result = await db.execute(notifications_stmt)
    await db.commit()

    deliveries_deleted = int(deliveries_result.rowcount or 0)
    notifications_deleted = int(notifications_result.rowcount or 0)

    if notifications_deleted or deliveries_deleted:
        logger.info(
            "Removed %s notifications and %s deliveries older than %s days",
            notifications_deleted,
            deliveries_deleted,
            retention_days,
        )

    return notifications_deleted, deliveries_deleted


async def _fetch_active_user_ids(
    db: AsyncSession, *, exclude: Sequence[int] | None = None
) -> list[int]:
    stmt = select(User.id).where(User.is_active.is_(True))
    if exclude:
        excluded = {int(uid) for uid in exclude if uid is not None}
        if excluded:
            stmt = stmt.where(User.id.notin_(excluded))
    rows = await db.execute(stmt)
    return [int(uid) for uid in rows.scalars().all()]


def _ensure_aware(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


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
    start_dt = _ensure_aware(getattr(lesson, "start_time", None))
    start_local = start_dt.astimezone()
    lesson_type_raw = getattr(lesson, "lesson_type", None)
    when_line = f"{start_local.strftime('%d.%m')} · {start_local.strftime('%H:%M')}"

    schedule_id = getattr(lesson, "id", None)
    timestamp_part = str(int(start_dt.timestamp())) if start_dt else "timestamp"

    cache: dict[str, tuple[str, str, str, dict[str, Any], str]] = {}

    def _render(locale_option: str | None) -> tuple[str, str, str, dict[str, Any]]:
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
            template_data = (
                template.get("data")
                if isinstance(template.get("data"), Mapping)
                else {}
            )
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
        if localized_body:
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


def is_user_in_quiet_hours(
    user: User | None, *, now_time: dt.time | None = None
) -> bool:
    if not user or not getattr(user, "dnd_enabled", False):
        return False
    start = getattr(user, "dnd_start", None)
    end = getattr(user, "dnd_end", None)
    if now_time is None:
        now_time = _current_local_time(user)
    if start is None or end is None:
        return True
    if start == end:
        return True
    if start < end:
        return start <= now_time < end
    return now_time >= start or now_time < end


def prepare_push_payload_for_user(
    payload: Mapping[str, Any],
    user: User | None,
    *,
    now_time: dt.time | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = dict(payload)
    data_section = base.get("data")
    if isinstance(data_section, Mapping):
        base["data"] = dict(data_section)
    if is_user_in_quiet_hours(user, now_time=now_time):
        base["silent"] = True
        base["vibrate"] = []
        base["renotify"] = False
        base["requireInteraction"] = False
        data_payload = base.get("data")
        if isinstance(data_payload, dict):
            data_payload = dict(data_payload)
        else:
            data_payload = {}
        data_payload["dnd_suppressed"] = True
        base["data"] = data_payload
    return base


_SCHEMA_CHECK_LOCK = asyncio.Lock()
_SCHEMA_CHECK_MARKER: float | None = None


async def _ensure_push_subscription_schema_once(db: AsyncSession) -> None:
    """Ensure the push subscription schema exists once per process."""

    global _SCHEMA_CHECK_MARKER

    if _SCHEMA_CHECK_MARKER is not None:
        return

    async with _SCHEMA_CHECK_LOCK:
        if _SCHEMA_CHECK_MARKER is not None:
            return
        await ensure_push_subscription_schema(db)
        _SCHEMA_CHECK_MARKER = dt.datetime.now(UTC).timestamp()


def invalidate_push_subscription_schema_cache() -> None:
    """Reset the cached schema check state so it runs again on next use."""

    global _SCHEMA_CHECK_MARKER
    _SCHEMA_CHECK_MARKER = None


async def create_notifications_for_users(
    db: AsyncSession,
    *,
    title: str,
    body: Optional[str] = None,
    title_translations: Mapping[str, Any] | None = None,
    body_translations: Mapping[str, Any] | None = None,
    type: Optional[str] = None,
    url: Optional[str] = None,
    badge: Optional[str] = None,
    tag: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    actions: Optional[Sequence[Mapping[str, Any]]] = None,
    payload_data: Optional[Mapping[str, Any]] = None,
    user_ids: Sequence[int],
    topic: Optional[str] = None,
) -> int:
    now = dt.datetime.now(UTC)
    uids = list({int(uid) for uid in user_ids})
    if not uids:
        return 0
    title_map = _normalize_translation_map(title_translations)
    body_map = _normalize_translation_map(body_translations)

    notifications: list[Notification] = []
    for uid in uids:
        title_ru = title_map.get("ru") or str(title)
        body_ru = body_map.get("ru") or _coerce_optional_text(body)
        notification_title_en = title_map.get("en")
        notification_body_en = body_map.get("en")
        notification = Notification(
            user_id=uid,
            title=title_ru,
            title_en=notification_title_en,
            body=body_ru,
            body_en=notification_body_en,
            type=type,
            url=url,
            dedupe_key=dedupe_key,
            created_at=now,
            read=False,
        )
        notifications.append(notification)
    db.add_all(notifications)
    await db.flush()
    notification_ids_by_user = {
        int(notification.user_id): int(notification.id)
        for notification in notifications
        if notification.id is not None
    }
    await db.commit()

    if notification_ids_by_user and type == "grade":
        await stats_cache.invalidate_user_stats_cache(
            user_ids=list(notification_ids_by_user.keys()),
            kinds=("grades",),
        )

    if not notification_ids_by_user:
        return 0

    vapid_ready = bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)
    delivery_rows: list[dict[str, Any]] = []

    if not vapid_ready:
        attempt_ts = dt.datetime.now(UTC)
        for notification_id in notification_ids_by_user.values():
            delivery_rows.append(
                _build_delivery_row(
                    notification_id,
                    status="skipped_no_credentials",
                    attempted_at=attempt_ts,
                )
            )
    else:
        await _ensure_push_subscription_schema_once(db)
        subs = (
            (
                await db.execute(
                    select(PushSubscription)
                    .options(selectinload(PushSubscription.user))
                    .where(PushSubscription.user_id.in_(uids))
                )
            )
            .scalars()
            .all()
        )

        if not subs:
            attempt_ts = dt.datetime.now(UTC)
            for notification_id in notification_ids_by_user.values():
                delivery_rows.append(
                    _build_delivery_row(
                        notification_id,
                        status="skipped_no_subscription",
                        attempted_at=attempt_ts,
                    )
                )
        else:
            base_payload: dict[str, Any] = {
                "title": title,
                "body": body or "",
                "url": url or "/",
                "type": type or None,
            }
            normalized_topic = normalize_topic(topic)
            if normalized_topic:
                base_payload["topic"] = normalized_topic
            if badge:
                base_payload["badge"] = badge
            if tag:
                base_payload["tag"] = tag
            if payload_data:
                base_payload["data"] = dict(payload_data)
            if actions:
                normalized_actions: list[dict[str, Any]] = []
                for action in actions:
                    if not isinstance(action, Mapping):
                        continue
                    normalized = {
                        key: value
                        for key, value in action.items()
                        if key in {"action", "title", "icon", "url"}
                    }
                    if not normalized.get("action") or not normalized.get("title"):
                        continue
                    normalized_actions.append(normalized)
                if normalized_actions:
                    base_payload["actions"] = normalized_actions

            send_jobs: list[tuple[PushSubscription, int]] = []
            tasks: list[Awaitable[WebPushResult]] = []

            limit = int(
                getattr(settings, "notifications_webpush_concurrency_limit", 0) or 0
            )
            semaphore: asyncio.Semaphore | None = None
            if limit > 0:
                semaphore = asyncio.Semaphore(limit)

            async def _send_push(
                subscription: PushSubscription, payload: Mapping[str, Any]
            ) -> WebPushResult:
                if semaphore is None:
                    return await asyncio.to_thread(send_web_push, subscription, payload)
                async with semaphore:
                    return await asyncio.to_thread(send_web_push, subscription, payload)

            for sub in subs:
                user_id = int(getattr(sub, "user_id", 0) or 0)
                notification_id = notification_ids_by_user.get(user_id)
                if not notification_id:
                    continue
                if not subscription_supports_topic(sub, normalized_topic):
                    delivery_rows.append(
                        _build_delivery_row(
                            notification_id,
                            status="skipped_topic",
                            detail=f"subscription:{sub.id}",
                        )
                    )
                    continue
                prepared_payload = prepare_push_payload_for_user(
                    base_payload, getattr(sub, "user", None)
                )
                send_jobs.append((sub, notification_id))
                tasks.append(_send_push(sub, prepared_payload))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for (sub, notification_id), result in zip(send_jobs, results):
                    attempt_ts = dt.datetime.now(UTC)
                    if isinstance(result, WebPushResult):
                        detail_parts: list[str] = [f"subscription:{sub.id}"]
                        if result.error:
                            detail_parts.append(result.error)
                        delivery_rows.append(
                            _build_delivery_row(
                                notification_id,
                                status=result.status,
                                attempted_at=attempt_ts,
                                delivered=result.status == "sent",
                                status_code=result.status_code,
                                detail="; ".join(detail_parts),
                            )
                        )
                    else:
                        delivery_rows.append(
                            _build_delivery_row(
                                notification_id,
                                status="error",
                                attempted_at=attempt_ts,
                                detail=f"subscription:{sub.id}; exception:{result}",
                            )
                        )

    if delivery_rows:
        await db.execute(insert(NotificationDelivery).values(delivery_rows))
        await db.commit()

    return len(notifications)


async def generate_schedule_reminders(
    db: AsyncSession, *, window_minutes: int = 6
) -> int:
    now = dt.datetime.now(UTC)
    soon = now + dt.timedelta(minutes=window_minutes)
    q = select(Schedule).where(
        and_(Schedule.start_time >= now, Schedule.start_time <= soon)
    )
    schedules = (await db.execute(q)).scalars().all()
    if not schedules:
        return 0

    schedules_by_group: dict[int, list[Schedule]] = defaultdict(list)
    message_payloads: dict[
        int,
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
        schedules_by_group[int(schedule.group_id)].append(schedule)
        payload = build_schedule_reminder_message(schedule)
        message_payloads[int(schedule.id)] = payload
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

    users_stmt = select(User.id, User.group_id).where(User.group_id.in_(group_ids))
    user_rows = await db.execute(users_stmt)
    group_users: dict[int, set[int]] = defaultdict(set)
    for user_id, group_id in user_rows:
        if user_id is None or group_id is None:
            continue
        group_users[int(group_id)].add(int(user_id))

    if not any(group_users.values()):
        return 0

    dup_since = now - dt.timedelta(minutes=30)
    all_user_ids = {uid for users in group_users.values() for uid in users}
    existing_by_dedupe: dict[str, set[int]] = defaultdict(set)
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
            existing_by_dedupe[str(dedupe_key)].add(int(user_id))

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
            ) = message_payloads[int(schedule.id)]
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
                topic="schedule",
            )
            existing_by_dedupe[key_for_dedupe].update(to_notify)
    return total_created


async def notify_about_news(
    db: AsyncSession, news: News, *, locale: str | None = None
) -> int:
    resolved_locale = resolve_locale(locale=locale)

    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    def _variant(
        locale_option: str | None,
    ) -> tuple[
        str,
        str,
        str,
        str,
        dict[str, Any],
        str | None,
        str | None,
    ]:
        normalized = resolve_locale(locale=locale_option)

        def _localized_attr(attr: str) -> str | None:
            ru_value = _clean_text(getattr(news, attr, None))
            en_value = _clean_text(getattr(news, f"{attr}_en", None))
            if normalized == "en":
                return en_value or ru_value
            return ru_value or en_value

        headline = _localized_attr("title")
        summary_source = _localized_attr("content")
        summary = _plain_text(summary_source, limit=220)
        url = f"/news/{news.id}" if getattr(news, "id", None) else "/news"
        template_payload = {
            "headline": headline or getattr(news, "title", None),
            "summary": summary,
            "id": getattr(news, "id", None),
            "url": url,
        }
        template = render_notification_template(
            "news.new", template_payload, locale=normalized
        )
        if headline:
            default_title = translate(
                "notifications.news.title_with_headline",
                locale=normalized,
                headline=headline,
            )
        else:
            default_title = translate("notifications.news.title", locale=normalized)
        default_body = summary or translate(
            "notifications.news.no_summary", locale=normalized
        )
        default_tag = f"news:{news.id}" if getattr(news, "id", None) else "news"
        if template:
            title_value = str(template.get("title") or default_title)
            body_value = str(template.get("body") or default_body)
            resolved_url = str(template.get("url") or url)
            tag_value = str(template.get("tag") or default_tag)
            template_data = (
                template.get("data")
                if isinstance(template.get("data"), Mapping)
                else {}
            )
            payload_data = (
                dict(template_data) if isinstance(template_data, Mapping) else {}
            )
        else:
            title_value, body_value, resolved_url, tag_value = (
                default_title,
                default_body,
                url,
                default_tag,
            )
            payload_data = {}
        payload_data.setdefault("headline", headline or getattr(news, "title", None))
        payload_data.setdefault("newsId", getattr(news, "id", None))
        if summary:
            payload_data.setdefault("summary", summary)
        payload_data.setdefault("url", resolved_url)
        payload_data.setdefault("category", "news")
        filtered_payload = {
            key: value for key, value in payload_data.items() if value not in (None, "")
        }
        return (
            normalized,
            title_value,
            body_value,
            resolved_url,
            tag_value,
            filtered_payload,
            headline,
            summary,
        )

    (
        _,
        title,
        body,
        resolved_url,
        tag,
        payload_data,
        _headline,
        _summary,
    ) = _variant(resolved_locale)

    title_translations: dict[str, str] = {}
    body_translations: dict[str, str] = {}
    for locale_code in SUPPORTED_LOCALES:
        (
            _normalized,
            localized_title,
            localized_body,
            _url,
            _tag,
            _payload,
            _loc_headline,
            _loc_summary,
        ) = _variant(locale_code)
        if localized_title:
            title_translations[locale_code] = localized_title
        if localized_body:
            body_translations[locale_code] = localized_body

    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        title_translations=title_translations,
        body_translations=body_translations,
        type="news.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="news",
    )


async def notify_about_event(
    db: AsyncSession, event: Event, *, locale: str | None = None
) -> int:
    def _variant(
        locale_option: str | None,
    ) -> tuple[
        str,
        str,
        str,
        str,
        dict[str, Any],
        str,
        str,
        str | None,
        str | None,
    ]:
        normalized = normalize_locale(locale_option)
        localized_title_value = localized_text(
            normalized,
            ru=getattr(event, "title", None),
            en=getattr(event, "title_en", None),
        )
        if not localized_title_value:
            localized_title_value = (
                getattr(event, "title", None) or getattr(event, "title_en", None) or ""
            )
        localized_description = localized_text(
            normalized,
            ru=getattr(event, "description", None),
            en=getattr(event, "description_en", None),
        )
        localized_about = localized_text(
            normalized,
            ru=getattr(event, "about", None),
            en=getattr(event, "about_en", None),
        )
        localized_location = localized_text(
            normalized,
            ru=getattr(event, "location", None),
            en=getattr(event, "location_en", None),
        )
        localized_event_type = localized_text(
            normalized,
            ru=getattr(event, "event_type", None),
            en=getattr(event, "event_type_en", None),
        )
        summary_source = localized_description or localized_about
        summary = _plain_text(summary_source, limit=220)
        url = f"/events/{event.id}" if getattr(event, "id", None) else "/events"
        start_dt = _ensure_aware(getattr(event, "starts_at", None))
        start_local = start_dt.astimezone()
        template_payload = {
            "title": localized_title_value,
            "summary": summary,
            "location": localized_location,
            "speaker": getattr(event, "speaker", None),
            "event_type": localized_event_type,
            "starts_at": start_dt.isoformat(),
            "date": start_local.strftime("%d.%m"),
            "time": start_local.strftime("%H:%M"),
            "url": url,
            "id": getattr(event, "id", None),
        }
        template = render_notification_template(
            "events.new", template_payload, locale=locale_option
        )
        if localized_title_value:
            default_title = translate(
                "notifications.events.title_with_name",
                locale=locale_option,
                title=localized_title_value,
            )
        else:
            default_title = translate(
                "notifications.events.title", locale=locale_option
            )
        details = [start_local.strftime("%d.%m · %H:%M")]
        if localized_location:
            details.append(str(localized_location))
        if getattr(event, "speaker", None):
            details.append(str(event.speaker))
        if localized_event_type:
            details.append(str(localized_event_type))
        default_lines = []
        if summary:
            default_lines.append(summary)
        if details:
            default_lines.append(" · ".join(details))
        default_body = "\n".join(default_lines) or translate(
            "notifications.events.no_details", locale=locale_option
        )
        default_tag = f"event:{event.id}" if getattr(event, "id", None) else "event"
        if template:
            title_value = str(template.get("title") or default_title)
            body_value = str(template.get("body") or default_body)
            resolved_url = str(template.get("url") or url)
            tag_value = str(template.get("tag") or default_tag)
            template_data = (
                template.get("data")
                if isinstance(template.get("data"), Mapping)
                else {}
            )
            payload_data = (
                dict(template_data) if isinstance(template_data, Mapping) else {}
            )
        else:
            title_value, body_value, resolved_url, tag_value = (
                default_title,
                default_body,
                url,
                default_tag,
            )
            payload_data = {}
        payload_data.setdefault("eventId", getattr(event, "id", None))
        payload_data.setdefault("title", localized_title_value)
        if summary:
            payload_data.setdefault("summary", summary)
        if localized_location:
            payload_data.setdefault("location", str(localized_location))
        if getattr(event, "speaker", None):
            payload_data.setdefault("speaker", str(event.speaker))
        if localized_event_type:
            payload_data.setdefault("eventType", str(localized_event_type))
        payload_data.setdefault("startsAt", start_dt.isoformat())
        payload_data.setdefault("startText", start_local.strftime("%d.%m · %H:%M"))
        payload_data.setdefault("url", resolved_url)
        payload_data.setdefault("category", "events")
        filtered_payload = {
            key: value for key, value in payload_data.items() if value not in (None, "")
        }
        return (
            normalized,
            title_value,
            body_value,
            resolved_url,
            tag_value,
            filtered_payload,
            start_dt.isoformat(),
            start_local.strftime("%d.%m · %H:%M"),
            localized_title_value,
            summary,
        )

    (
        _,
        title,
        body,
        resolved_url,
        tag,
        payload_data,
        _starts_at,
        _start_text,
        _localized_title,
        _summary,
    ) = _variant(locale)

    title_translations: dict[str, str] = {}
    body_translations: dict[str, str] = {}
    for locale_code in SUPPORTED_LOCALES:
        (
            _normalized,
            localized_title,
            localized_body,
            _url,
            _tag,
            _payload,
            _starts_at,
            _start_text,
            _title_value,
            _summary_value,
        ) = _variant(locale_code)
        if localized_title:
            title_translations[locale_code] = localized_title
        if localized_body:
            body_translations[locale_code] = localized_body

    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        title_translations=title_translations,
        body_translations=body_translations,
        type="events.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="events",
    )


async def aggregate_notification_delivery_stats(
    db: AsyncSession,
    *,
    since: dt.datetime | None = None,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(
        NotificationDelivery.channel,
        NotificationDelivery.status,
        func.count(NotificationDelivery.id).label("count"),
        func.count(NotificationDelivery.delivered_at).label("delivered"),
        func.min(NotificationDelivery.attempted_at).label("first_attempt_at"),
        func.max(NotificationDelivery.attempted_at).label("last_attempt_at"),
    ).group_by(NotificationDelivery.channel, NotificationDelivery.status)

    if since is not None:
        stmt = stmt.where(NotificationDelivery.attempted_at >= since)
    if channel is not None:
        stmt = stmt.where(NotificationDelivery.channel == channel)

    result = await db.execute(stmt)
    stats: list[dict[str, Any]] = []
    for row in result:
        stats.append(
            {
                "channel": row.channel,
                "status": row.status,
                "count": int(row.count or 0),
                "delivered": int(row.delivered or 0),
                "first_attempt_at": row.first_attempt_at,
                "last_attempt_at": row.last_attempt_at,
            }
        )
    return stats


async def start_notifications_scheduler(
    *,
    poll_seconds: int = 30,
    window_minutes: int = 6,
    max_backoff_seconds: int = 300,
) -> Callable[[], Awaitable[None]]:
    """Start background notifications scheduler via the worker implementation."""

    from app.workers.notifications import start_notifications_scheduler as _start

    return await _start(
        poll_seconds=poll_seconds,
        window_minutes=window_minutes,
        max_backoff_seconds=max_backoff_seconds,
    )


# Backwards compatibility for tests that patch async_session on this module.
async_session = _async_session


async def _scheduler_loop(
    poll_seconds: int = 30,
    window_minutes: int = 6,
    *,
    max_backoff_seconds: int = 300,
) -> None:
    """Compatibility wrapper delegating to the worker scheduler loop."""

    from app.workers import notifications as worker_module

    scheduler = worker_module.NotificationsScheduler(
        poll_seconds=poll_seconds,
        window_minutes=window_minutes,
        max_backoff_seconds=max_backoff_seconds,
        metrics=None,
    )

    original_sleep = worker_module.asyncio.sleep
    original_session = worker_module.async_session
    try:
        worker_module.asyncio.sleep = asyncio.sleep
        worker_module.async_session = async_session  # type: ignore[attr-defined]
        try:
            await scheduler.run_forever()
        except asyncio.CancelledError:
            return
    finally:
        worker_module.asyncio.sleep = original_sleep
        worker_module.async_session = original_session
