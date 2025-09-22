from typing import Optional, Tuple, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func, and_, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Notification, Schedule
from app.schemas.schemas import NotificationOut, NotificationsListOut

router = APIRouter(prefix="/notifications", tags=["notifications"])

def _encode_cursor(dt: datetime, nid: int) -> str:
    return f"{int(dt.timestamp() * 1000)}:{nid}"

def _decode_cursor(value: Optional[str]) -> Optional[Tuple[datetime, int]]:
    if not value:
        return None
    try:
        ms_s, id_s = value.split(":", 1)
        return datetime.utcfromtimestamp(int(ms_s) / 1000.0), int(id_s)
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
        where.append(or_(Notification.created_at < c_dt, and_(Notification.created_at == c_dt, Notification.id < c_id)))

    q_items = (
        select(Notification)
        .where(and_(*where))
        .order_by(desc(Notification.created_at), desc(Notification.id))
        .limit(limit + 1)
    )
    rows = (await db.execute(q_items)).scalars().all()
    items = rows[:limit]
    has_more = len(rows) > limit

    q_unread = select(func.count(Notification.id)).where(and_(Notification.user_id == user.id, Notification.read.is_(False)))
    unread = (await db.execute(q_unread)).scalar_one() or 0

    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if items and has_more else None

    return NotificationsListOut(
        items=[NotificationOut.from_orm(n) for n in items],
        unread_count=int(unread),
        has_more=has_more,
        next_cursor=next_cursor,
    )

@router.post("/{notif_id}/read")
async def mark_read_single(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == user.id, Notification.id == notif_id))
        .values(read=True)
    )
    await db.commit()
    return {"ok": True}

@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == user.id, Notification.read.is_(False)))
        .values(read=True)
    )
    await db.commit()
    return {"ok": True}

@router.post("/check-schedule", response_model=NotificationsListOut)
async def check_schedule_and_generate(
    lookahead_minutes: int = Query(15, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not user.group_id:
        return await list_notifications(db=db, user=user, limit=20, cursor=None)

    now = datetime.utcnow()
    soon = now + timedelta(minutes=lookahead_minutes)

    q = (
        select(Schedule)
        .where(and_(Schedule.group_id == user.group_id, Schedule.start_time >= now, Schedule.start_time <= soon))
        .order_by(Schedule.start_time.asc())
    )
    lessons = (await db.execute(q)).scalars().all()

    created_any = False
    for les in lessons:
        title = f"Скоро пара: {les.subject}"
        body = f"Начало в {les.start_time.strftime('%H:%M')} — {les.room or 'аудитория не указана'}"
        url = "/schedule"

        dupe = select(func.count(Notification.id)).where(
            and_(Notification.user_id == user.id, Notification.title == title, Notification.url == url, Notification.created_at >= now - timedelta(hours=1))
        )
        exists = (await db.execute(dupe)).scalar_one() or 0
        if exists:
            continue

        db.add(Notification(user_id=user.id, type="schedule", title=title, body=body, url=url, created_at=now, read=False))
        created_any = True

    if created_any:
        await db.commit()

    return await list_notifications(db=db, user=user, limit=20, cursor=None)