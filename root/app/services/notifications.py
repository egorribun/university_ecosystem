import asyncio
import datetime as dt
import logging
import re
from datetime import UTC
from html import unescape
from textwrap import shorten
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence

from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session
from app.models.models import (
    Event,
    News,
    Notification,
    PushSubscription,
    Schedule,
    User,
)
from app.services.notification_templates import render_notification_template
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import send_web_push


def _current_local_time() -> dt.time:
    return dt.datetime.now().astimezone().time()


logger = logging.getLogger(__name__)


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
    lesson: Schedule,
) -> tuple[str, str, str, dict[str, Any]]:
    start_dt = _ensure_aware(getattr(lesson, "start_time", None))
    start_local = start_dt.astimezone()
    payload_input = {
        "subject": getattr(lesson, "subject", None),
        "group": getattr(getattr(lesson, "group", None), "name", None),
        "lesson_type": getattr(lesson, "lesson_type", None),
        "teacher": getattr(lesson, "teacher", None),
        "room": getattr(lesson, "room", None),
        "starts_at": start_dt.isoformat(),
        "date": start_local.strftime("%d.%m"),
        "time": start_local.strftime("%H:%M"),
        "url": "/schedule",
        "lesson_id": getattr(lesson, "id", None),
    }
    template = render_notification_template("schedule.reminder", payload_input)
    default_title = (
        f"Скоро пара: {lesson.subject}"
        if getattr(lesson, "subject", None)
        else "Скоро пара"
    )
    summary_parts: list[str] = []
    if getattr(lesson, "lesson_type", None):
        summary_parts.append(str(lesson.lesson_type))
    room_value = getattr(lesson, "room", None)
    if room_value:
        room_text = str(room_value)
        summary_parts.append(
            room_text if room_text.lower().startswith("ауд") else f"ауд. {room_text}"
        )
    if getattr(lesson, "teacher", None):
        summary_parts.append(str(lesson.teacher))
    when_line = f"{start_local.strftime('%d.%m')} · {start_local.strftime('%H:%M')}"
    default_lines = [f"Начало: {when_line}"]
    if summary_parts:
        default_lines.append(" · ".join(summary_parts))
    else:
        default_lines.append("Проверьте расписание для подробностей.")
    default_body = "\n".join(default_lines)
    default_tag = f"schedule-reminder:{getattr(lesson, 'id', 'lesson')}:{int(start_dt.timestamp())}"
    default_data: dict[str, Any] = {
        "url": "/schedule",
        "category": "schedule",
        "lessonId": getattr(lesson, "id", None),
        "subject": getattr(lesson, "subject", None),
        "groupId": getattr(lesson, "group_id", None),
        "lessonType": getattr(lesson, "lesson_type", None),
        "teacher": getattr(lesson, "teacher", None),
        "room": getattr(lesson, "room", None),
        "startText": when_line,
        "startsAt": start_dt.isoformat(),
        "startTimestamp": int(start_dt.timestamp()),
    }
    if template:
        title = str(template.get("title") or default_title)
        body = str(template.get("body") or default_body)
        tag = str(template.get("tag") or default_tag)
        template_data = (
            template.get("data") if isinstance(template.get("data"), Mapping) else {}
        )
        merged_data = {**default_data}
        if isinstance(template_data, Mapping):
            merged_data.update(template_data)
    else:
        title, body, tag, merged_data = (
            default_title,
            default_body,
            default_tag,
            default_data,
        )
    filtered_data = {
        key: value for key, value in merged_data.items() if value not in (None, "")
    }
    return title, body, tag, filtered_data


def is_user_in_quiet_hours(
    user: User | None, *, now_time: dt.time | None = None
) -> bool:
    if not user or not getattr(user, "dnd_enabled", False):
        return False
    start = getattr(user, "dnd_start", None)
    end = getattr(user, "dnd_end", None)
    if now_time is None:
        now_time = _current_local_time()
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


async def create_notifications_for_users(
    db: AsyncSession,
    *,
    title: str,
    body: Optional[str] = None,
    type: Optional[str] = None,
    url: Optional[str] = None,
    badge: Optional[str] = None,
    tag: Optional[str] = None,
    actions: Optional[Sequence[Mapping[str, Any]]] = None,
    payload_data: Optional[Mapping[str, Any]] = None,
    user_ids: Sequence[int],
    topic: Optional[str] = None,
) -> int:
    now = dt.datetime.now(UTC)
    uids = list({int(uid) for uid in user_ids})
    if not uids:
        return 0
    rows = [
        {
            "user_id": uid,
            "title": title,
            "body": body,
            "type": type,
            "url": url,
            "created_at": now,
            "read": False,
        }
        for uid in uids
    ]
    await db.execute(insert(Notification).values(rows))
    await db.commit()
    if settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY:
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
        now_time = _current_local_time()
        for s in subs:
            if not subscription_supports_topic(s, normalized_topic):
                continue
            prepared_payload = prepare_push_payload_for_user(
                base_payload, getattr(s, "user", None), now_time=now_time
            )
            asyncio.create_task(asyncio.to_thread(send_web_push, s, prepared_payload))
    return len(rows)


async def generate_schedule_reminders(
    db: AsyncSession, *, window_minutes: int = 6
) -> int:
    now = dt.datetime.now(UTC)
    soon = now + dt.timedelta(minutes=window_minutes)
    q = select(Schedule).where(
        and_(Schedule.start_time >= now, Schedule.start_time <= soon)
    )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return 0
    total_created = 0
    for sch in rows:
        title, body, tag, data_payload = build_schedule_reminder_message(sch)
        uids_all = (
            (await db.execute(select(User.id).where(User.group_id == sch.group_id)))
            .scalars()
            .all()
        )
        if not uids_all:
            continue
        dup_since = now - dt.timedelta(minutes=30)
        existing_q = (
            select(Notification.user_id)
            .where(
                and_(
                    Notification.user_id.in_(
                        select(User.id).where(User.group_id == sch.group_id)
                    ),
                    Notification.title == title,
                    Notification.url == "/schedule",
                    Notification.created_at >= dup_since,
                )
            )
            .distinct()
        )
        existing = set((await db.execute(existing_q)).scalars().all())
        to_notify = [u for u in uids_all if u not in existing]
        if not to_notify:
            continue
        total_created += await create_notifications_for_users(
            db,
            title=title,
            body=body,
            type="schedule.reminder",
            url="/schedule",
            tag=tag,
            actions=[
                {
                    "action": "open-schedule",
                    "title": "Открыть расписание",
                    "url": "/schedule",
                }
            ],
            payload_data=data_payload,
            user_ids=to_notify,
            topic="schedule",
        )
    return total_created


async def notify_about_news(db: AsyncSession, news: News) -> int:
    summary = _plain_text(getattr(news, "content", None), limit=220)
    url = f"/news/{news.id}" if getattr(news, "id", None) else "/news"
    template_payload = {
        "headline": getattr(news, "title", None),
        "summary": summary,
        "id": getattr(news, "id", None),
        "url": url,
    }
    template = render_notification_template("news.new", template_payload)
    default_title = (
        f"Новая новость: {news.title}"
        if getattr(news, "title", None)
        else "Новая новость"
    )
    default_body = summary or "Откройте новость, чтобы узнать подробности."
    default_tag = f"news:{news.id}" if getattr(news, "id", None) else "news"
    if template:
        title = str(template.get("title") or default_title)
        body = str(template.get("body") or default_body)
        resolved_url = str(template.get("url") or url)
        tag = str(template.get("tag") or default_tag)
        template_data = (
            template.get("data") if isinstance(template.get("data"), Mapping) else {}
        )
        payload_data = dict(template_data) if isinstance(template_data, Mapping) else {}
    else:
        title, body, resolved_url, tag = default_title, default_body, url, default_tag
        payload_data = {}
    payload_data.setdefault("headline", getattr(news, "title", None))
    payload_data.setdefault("newsId", getattr(news, "id", None))
    if summary:
        payload_data.setdefault("summary", summary)
    payload_data.setdefault("url", resolved_url)
    payload_data.setdefault("category", "news")
    payload_data = {
        key: value for key, value in payload_data.items() if value not in (None, "")
    }
    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        type="news.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="news",
    )


async def notify_about_event(db: AsyncSession, event: Event) -> int:
    summary = _plain_text(
        getattr(event, "description", None) or getattr(event, "about", None), limit=220
    )
    url = f"/events/{event.id}" if getattr(event, "id", None) else "/events"
    start_dt = _ensure_aware(getattr(event, "starts_at", None))
    start_local = start_dt.astimezone()
    template_payload = {
        "title": getattr(event, "title", None),
        "summary": summary,
        "location": getattr(event, "location", None),
        "speaker": getattr(event, "speaker", None),
        "event_type": getattr(event, "event_type", None),
        "starts_at": start_dt.isoformat(),
        "date": start_local.strftime("%d.%m"),
        "time": start_local.strftime("%H:%M"),
        "url": url,
        "id": getattr(event, "id", None),
    }
    template = render_notification_template("events.new", template_payload)
    default_title = (
        f"Новое мероприятие: {event.title}"
        if getattr(event, "title", None)
        else "Новое мероприятие"
    )
    details = [start_local.strftime("%d.%m · %H:%M")]
    if getattr(event, "location", None):
        details.append(str(event.location))
    if getattr(event, "speaker", None):
        details.append(str(event.speaker))
    if getattr(event, "event_type", None):
        details.append(str(event.event_type))
    default_lines = []
    if summary:
        default_lines.append(summary)
    if details:
        default_lines.append(" · ".join(details))
    default_body = "\n".join(default_lines) or "Подробнее в карточке события."
    default_tag = f"event:{event.id}" if getattr(event, "id", None) else "event"
    if template:
        title = str(template.get("title") or default_title)
        body = str(template.get("body") or default_body)
        resolved_url = str(template.get("url") or url)
        tag = str(template.get("tag") or default_tag)
        template_data = (
            template.get("data") if isinstance(template.get("data"), Mapping) else {}
        )
        payload_data = dict(template_data) if isinstance(template_data, Mapping) else {}
    else:
        title, body, resolved_url, tag = default_title, default_body, url, default_tag
        payload_data = {}
    payload_data.setdefault("eventId", getattr(event, "id", None))
    payload_data.setdefault("title", getattr(event, "title", None))
    if summary:
        payload_data.setdefault("summary", summary)
    if getattr(event, "location", None):
        payload_data.setdefault("location", str(event.location))
    if getattr(event, "speaker", None):
        payload_data.setdefault("speaker", str(event.speaker))
    if getattr(event, "event_type", None):
        payload_data.setdefault("eventType", str(event.event_type))
    payload_data.setdefault("startsAt", start_dt.isoformat())
    payload_data.setdefault("startText", start_local.strftime("%d.%m · %H:%M"))
    payload_data.setdefault("url", resolved_url)
    payload_data.setdefault("category", "events")
    payload_data = {
        key: value for key, value in payload_data.items() if value not in (None, "")
    }
    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        type="events.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="events",
    )


async def _scheduler_loop(poll_seconds: int = 30, window_minutes: int = 6):
    try:
        while True:
            try:
                async with async_session() as db:
                    await generate_schedule_reminders(db, window_minutes=window_minutes)
            except Exception:
                pass
            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        return


_scheduler_task: asyncio.Task[None] | None = None


async def start_notifications_scheduler(
    *, poll_seconds: int = 30, window_minutes: int = 6
) -> Callable[[], Awaitable[None]]:
    """Start background notifications scheduler and return a stopper."""

    global _scheduler_task

    async def _stop_task(task: asyncio.Task[None]) -> None:
        if task.done():
            try:
                task.result()
            except Exception:
                pass
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    if _scheduler_task and not _scheduler_task.done():
        existing = _scheduler_task

        async def _stop_existing() -> None:
            global _scheduler_task
            await _stop_task(existing)
            if _scheduler_task is existing:
                _scheduler_task = None

        return _stop_existing

    loop = asyncio.get_running_loop()
    task = loop.create_task(
        _scheduler_loop(poll_seconds=poll_seconds, window_minutes=window_minutes)
    )
    _scheduler_task = task

    async def _stop() -> None:
        global _scheduler_task
        await _stop_task(task)
        if _scheduler_task is task:
            _scheduler_task = None

    return _stop
