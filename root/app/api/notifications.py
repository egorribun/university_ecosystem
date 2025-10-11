from datetime import UTC, datetime, timedelta
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Notification, Schedule, User
from app.schemas.schemas import NotificationOut, NotificationsListOut
from app.services.notifications import (
    build_schedule_reminder_message,
    create_notifications_for_users,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _ensure_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def _encode_cursor(dt: datetime, nid: int) -> str:
    aware = _ensure_utc(dt)
    return f"{int(aware.timestamp() * 1000)}:{nid}"


def _decode_cursor(value: Optional[str]) -> Optional[Tuple[datetime, int]]:
    if not value:
        return None
    try:
        ms_s, id_s = value.split(":", 1)
        return datetime.fromtimestamp(int(ms_s) / 1000.0, UTC), int(id_s)
    except Exception:
        return None


@router.get("", response_model=NotificationsListOut)
async def list_notifications(
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    where = [Notification.user_id == user.id]
    if cursor:
        parsed = _decode_cursor(cursor)
        if not parsed:
            raise HTTPException(status_code=400, detail="bad cursor")
        c_dt, c_id = parsed
        c_dt = _ensure_utc(c_dt)
        where.append(
            or_(
                Notification.created_at < c_dt,
                and_(Notification.created_at == c_dt, Notification.id < c_id),
            )
        )

    q_items = (
        select(Notification)
        .where(and_(*where))
        .order_by(desc(Notification.created_at), desc(Notification.id))
        .limit(limit + 1)
    )
    rows = (await db.execute(q_items)).scalars().all()
    items = rows[:limit]
    has_more = len(rows) > limit

    q_unread = select(func.count(Notification.id)).where(
        and_(Notification.user_id == user.id, Notification.read.is_(False))
    )
    unread = (await db.execute(q_unread)).scalar_one() or 0

    next_cursor = (
        _encode_cursor(_ensure_utc(items[-1].created_at), items[-1].id)
        if items and has_more
        else None
    )

    return NotificationsListOut(
        items=[NotificationOut.from_orm(n) for n in items],
        unread_count=int(unread),
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.patch("/{notif_id}/read")
async def mark_read_single(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notif = await db.get(Notification, notif_id)
    if not notif or notif.user_id != user.id:
        raise HTTPException(status_code=404, detail="notification not found")

    if notif.read:
        return {"ok": True}

    notif.read = True
    notif.read_at = datetime.now(UTC)
    await db.commit()

    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == user.id, Notification.read.is_(False)))
        .values(read=True, read_at=now)
    )
    await db.commit()
    updated = result.rowcount or 0
    return {"ok": True, "updated": int(updated)}


@router.delete("")
async def clear_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        delete(Notification).where(Notification.user_id == user.id)
    )
    await db.commit()
    deleted = result.rowcount or 0
    return {"ok": True, "deleted": int(deleted)}


@router.post("/check-schedule", response_model=NotificationsListOut)
async def check_schedule_and_generate(
    lookahead_minutes: int = Query(15, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.group_id:
        return await list_notifications(db=db, user=user, limit=20, cursor=None)

    now = datetime.now(UTC)
    soon = now + timedelta(minutes=lookahead_minutes)

    q = (
        select(Schedule)
        .where(
            and_(
                Schedule.group_id == user.group_id,
                Schedule.start_time >= now,
                Schedule.start_time <= soon,
            )
        )
        .order_by(Schedule.start_time.asc())
    )
    lessons = (await db.execute(q)).scalars().all()

    for les in lessons:
        title, body, tag, data_payload = build_schedule_reminder_message(les)
        url = "/schedule"

        dupe = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user.id,
                Notification.title == title,
                Notification.url == url,
                Notification.created_at >= now - timedelta(hours=1),
            )
        )
        exists = (await db.execute(dupe)).scalar_one() or 0
        if exists:
            continue
        await create_notifications_for_users(
            db,
            title=title,
            body=body,
            type="schedule.reminder",
            url=url,
            tag=tag,
            payload_data=data_payload,
            actions=[
                {
                    "action": "open-schedule",
                    "title": "Открыть расписание",
                    "url": url,
                }
            ],
            user_ids=[user.id],
            topic="schedule",
        )

    return await list_notifications(db=db, user=user, limit=20, cursor=None)
