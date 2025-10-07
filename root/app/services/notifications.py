import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC
from typing import Any

from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session
from app.models.models import Notification, PushSubscription, Schedule, User
from app.services.push_topics import normalize_topic, subscription_supports_topic
from app.services.webpush import send_web_push


def _current_local_time() -> dt.time:
    return dt.datetime.now().astimezone().time()


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
    body: str | None = None,
    type: str | None = None,
    url: str | None = None,
    badge: str | None = None,
    tag: str | None = None,
    actions: Sequence[Mapping[str, Any]] | None = None,
    payload_data: Mapping[str, Any] | None = None,
    user_ids: Sequence[int],
    topic: str | None = None,
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
        title = f"Скоро пара: {sch.subject}"
        time_str = sch.start_time.strftime("%H:%M")
        body = f"{sch.lesson_type or ''} в {sch.room or 'ауд.'}, начало в {time_str}"
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
            type="lesson",
            url="/schedule",
            tag=f"schedule-{sch.id}",
            actions=[
                {
                    "action": "open-schedule",
                    "title": "Открыть расписание",
                    "url": "/schedule",
                }
            ],
            user_ids=to_notify,
            topic="schedule",
        )
    return total_created


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
