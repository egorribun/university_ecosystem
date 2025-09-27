import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.auth.security import get_password_hash
from app.models import models
from app.schemas import schemas
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def get_user_auth(db: AsyncSession, login: str):
    login_norm = login.strip().lower()
    stmt = select(models.User).where(func.lower(models.User.email) == login_norm)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: schemas.UserCreate):
    code = None
    if hasattr(user_in, "invite_code") and getattr(user_in, "role", "student") in (
        "teacher",
        "admin",
    ):
        code_q = select(models.InviteCode).where(
            models.InviteCode.code == user_in.invite_code,
            models.InviteCode.role == user_in.role,
            models.InviteCode.is_active.is_(True),
            models.InviteCode.is_used.is_(False),
        )
        code = (await db.execute(code_q)).scalar_one_or_none()
        if not code:
            raise ValueError("Неверный или уже использованный invite code")

    exists = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == user_in.email.strip().lower()
        )
    )
    if exists.scalar_one_or_none():
        raise ValueError("Пользователь с таким email уже существует")

    hashed_password = get_password_hash(user_in.password)
    db_user = models.User(
        email=user_in.email.strip(),
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        role=getattr(user_in, "role", "student"),
        group_id=getattr(user_in, "group_id", None),
        avatar_url=getattr(user_in, "avatar_url", None),
        cover_url=getattr(user_in, "cover_url", None),
        about=getattr(user_in, "about", None),
        record_book_number=getattr(user_in, "record_book_number", None),
        status=getattr(user_in, "status", None),
        institute=getattr(user_in, "institute", None),
        course=getattr(user_in, "course", None),
        education_level=getattr(user_in, "education_level", None),
        track=getattr(user_in, "track", None),
        program=getattr(user_in, "program", None),
        telegram=getattr(user_in, "telegram", None),
        achievements=getattr(user_in, "achievements", None),
        department=getattr(user_in, "department", None),
        position=getattr(user_in, "position", None),
    )
    db.add(db_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Ошибка создания пользователя")

    await db.refresh(db_user)

    if code:
        code.is_used = True
        code.is_active = False
        code.used_by_user_id = db_user.id
        db.add(code)
        await db.commit()

    return db_user


async def create_news(db: AsyncSession, news: schemas.NewsCreate):
    record = models.News(**news.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_news_list(db: AsyncSession, skip: int = 0, limit: int = 10):
    stmt = (
        select(models.News)
        .order_by(models.News.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def _attendance_counts(db: AsyncSession, event_ids: List[int]) -> Dict[int, int]:
    if not event_ids:
        return {}
    rows = await db.execute(
        select(models.EventAttendance.event_id, func.count(models.EventAttendance.id))
        .where(models.EventAttendance.event_id.in_(event_ids))
        .group_by(models.EventAttendance.event_id)
    )
    return {eid: cnt for eid, cnt in rows.all()}


async def _files_by_event(
    db: AsyncSession, event_ids: List[int]
) -> Dict[int, List[models.EventFile]]:
    if not event_ids:
        return {}
    rows = await db.execute(
        select(models.EventFile).where(models.EventFile.event_id.in_(event_ids))
    )
    files = rows.scalars().all()
    out: Dict[int, List[models.EventFile]] = {}
    for f in files:
        out.setdefault(f.event_id, []).append(f)
    return out


async def get_all_events(
    db: AsyncSession,
    user_id: int | None = None,
    search: str = "",
    type: str = "",
    location: str = "",
    is_active: bool = True,
):
    q = select(models.Event)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if search:
        q = q.where(
            or_(
                models.Event.title.ilike(f"%{search}%"),
                models.Event.description.ilike(f"%{search}%"),
            )
        )
    if type:
        q = q.where(models.Event.event_type == type)
    if location:
        q = q.where(models.Event.location.ilike(f"%{location}%"))
    if is_active:
        q = q.where(models.Event.ends_at >= now)
    else:
        q = q.where(models.Event.ends_at < now)

    events = (
        (await db.execute(q.order_by(models.Event.starts_at.asc()))).scalars().all()
    )
    ids = [e.id for e in events]
    counts = await _attendance_counts(db, ids)
    files_map = await _files_by_event(db, ids)

    registered_ids = set()
    if user_id:
        reg_q = await db.execute(
            select(models.EventAttendance.event_id).where(
                models.EventAttendance.user_id == user_id
            )
        )
        registered_ids = set(reg_q.scalars().all())

    result = []
    for event in events:
        result.append(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "about": getattr(event, "about", None),
                "event_type": getattr(event, "event_type", None),
                "location": event.location,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "created_by": event.created_by,
                "created_at": event.created_at,
                "participant_count": counts.get(event.id, 0),
                "files": [
                    schemas.EventFileOut.from_orm(f)
                    for f in files_map.get(event.id, [])
                ],
                "is_active": getattr(event, "is_active", True),
                "is_registered": event.id in registered_ids,
                "speaker": getattr(event, "speaker", None),
                "image_url": getattr(event, "image_url", None),
            }
        )
    return result


async def create_event(db: AsyncSession, event: schemas.EventCreate, user_id: int):
    starts_at = (
        event.starts_at.replace(tzinfo=None) if event.starts_at.tzinfo else event.starts_at
    )
    ends_at = (
        event.ends_at.replace(tzinfo=None) if event.ends_at.tzinfo else event.ends_at
    )
    record = models.Event(
        title=event.title,
        description=event.description,
        about=getattr(event, "about", None),
        event_type=getattr(event, "event_type", None),
        location=event.location,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=user_id,
        speaker=getattr(event, "speaker", None),
        image_url=getattr(event, "image_url", None),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def register_attendance(
    db: AsyncSession, data: schemas.EventAttendanceCreate, user_id: int
):
    stmt = select(models.EventAttendance).where(
        and_(
            models.EventAttendance.event_id == data.event_id,
            models.EventAttendance.user_id == user_id,
        )
    )
    exist = (await db.execute(stmt)).scalar_one_or_none()
    if exist:
        return exist

    qr_code = str(uuid.uuid4())
    record = models.EventAttendance(
        user_id=user_id, event_id=data.event_id, qr_code=qr_code
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def unregister_attendance(
    db: AsyncSession, data: schemas.EventAttendanceCreate, user_id: int
):
    stmt = select(models.EventAttendance).where(
        and_(
            models.EventAttendance.event_id == data.event_id,
            models.EventAttendance.user_id == user_id,
        )
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        return {"ok": False}
    await db.delete(record)
    await db.commit()
    return {"ok": True}


async def get_my_events(db: AsyncSession, user_id: int):
    ids = (
        (
            await db.execute(
                select(models.EventAttendance.event_id).where(
                    models.EventAttendance.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return []
    q = select(models.Event).where(models.Event.id.in_(ids))
    events = (await db.execute(q)).scalars().all()
    counts = await _attendance_counts(db, ids)
    files_map = await _files_by_event(db, ids)

    result = []
    for event in events:
        result.append(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "about": getattr(event, "about", None),
                "event_type": getattr(event, "event_type", None),
                "location": event.location,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "created_by": event.created_by,
                "created_at": event.created_at,
                "participant_count": counts.get(event.id, 0),
                "files": [
                    schemas.EventFileOut.from_orm(f)
                    for f in files_map.get(event.id, [])
                ],
                "is_active": getattr(event, "is_active", True),
                "is_registered": True,
                "speaker": getattr(event, "speaker", None),
                "image_url": getattr(event, "image_url", None),
            }
        )
    return result


async def get_schedule_by_group(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(models.Schedule)
        .where(models.Schedule.group_id == group_id)
        .order_by(models.Schedule.weekday, models.Schedule.start_time)
    )
    return result.scalars().all()


async def create_schedule(db: AsyncSession, data: schemas.ScheduleCreate):
    start_time = (
        data.start_time.replace(tzinfo=None)
        if data.start_time.tzinfo
        else data.start_time
    )
    end_time = (
        data.end_time.replace(tzinfo=None) if data.end_time.tzinfo else data.end_time
    )
    record = models.Schedule(
        group_id=data.group_id,
        subject=data.subject,
        teacher=data.teacher,
        room=data.room,
        weekday=data.weekday,
        start_time=start_time,
        end_time=end_time,
        parity=getattr(data, "parity", "both"),
        lesson_type=getattr(data, "lesson_type", "Лекция"),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def create_group(db: AsyncSession, data: schemas.GroupCreate):
    group = models.Group(name=data.name, course=data.course, faculty=data.faculty)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


async def get_users(
    db: AsyncSession,
    group_id: Optional[int] = None,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
) -> List[models.User]:
    stmt = select(models.User)
    if group_id:
        stmt = stmt.where(models.User.group_id == group_id)
    if full_name:
        stmt = stmt.where(models.User.full_name.ilike(f"%{full_name}%"))
    if role:
        stmt = stmt.where(models.User.role == role)
    result = await db.execute(stmt)
    return result.scalars().all()


async def admin_update_user(
    db: AsyncSession, user_id: int, data: schemas.UserAdminUpdate
) -> models.User:
    user = await db.get(models.User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int):
    user = await db.get(models.User, user_id)
    if not user:
        raise ValueError("Пользователь не найден")
    await db.delete(user)
    await db.commit()
