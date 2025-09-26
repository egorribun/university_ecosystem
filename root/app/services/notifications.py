import asyncio
import datetime as dt
from typing import Awaitable, Callable, Optional, Sequence

from sqlalchemy import select, and_, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.config import settings
from app.models.models import User, Schedule, Notification, PushSubscription
from app.services.webpush import send_web_push


async def create_notifications_for_users(
    db: AsyncSession,
    *,
    title: str,
    body: Optional[str] = None,
    type: Optional[str] = None,
    url: Optional[str] = None,
    user_ids: Sequence[int],
) -> int:
    now = dt.datetime.utcnow()
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
    if settings.vapid_private_key and settings.vapid_public_key:
        subs = (
            await db.execute(
                select(PushSubscription).where(
                    and_(
                        PushSubscription.active.is_(True),
                        PushSubscription.user_id.in_(uids),
                    )
                )
            )
        ).scalars().all()
        payload = {
            "title": title,
            "body": body or "",
            "url": url or "/",
            "type": type or None,
        }
        loop = asyncio.get_running_loop()
        for s in subs:
            loop.create_task(asyncio.to_thread(send_web_push, s, payload))
    return len(rows)


async def generate_schedule_reminders(db: AsyncSession, *, window_minutes: int = 6) -> int:
    now = dt.datetime.utcnow()
    soon = now + dt.timedelta(minutes=window_minutes)
    q = select(Schedule).where(and_(Schedule.start_time >= now, Schedule.start_time <= soon))
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return 0
    total_created = 0
    for sch in rows:
        title = f"Скоро пара: {sch.subject}"
        time_str = sch.start_time.strftime("%H:%M")
        body = f"{sch.lesson_type or ''} в {sch.room or 'ауд.'}, начало в {time_str}"
        uids_all = (await db.execute(select(User.id).where(User.group_id == sch.group_id))).scalars().all()
        if not uids_all:
            continue
        dup_since = now - dt.timedelta(minutes=30)
        existing_q = (
            select(Notification.user_id)
            .where(
                and_(
                    Notification.user_id.in_(select(User.id).where(User.group_id == sch.group_id)),
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
            user_ids=to_notify,
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
