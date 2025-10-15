import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
from app.localization import localized_text, normalize_locale, translate
from app.models import models
from app.models.enums import UserRole
from app.schemas import schemas


async def get_user_auth(db: AsyncSession, login: str):
    login_norm = login.strip().lower()
    stmt = select(models.User).where(func.lower(models.User.email) == login_norm)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


_EVENT_TIME_ORDER_KEY = "validation.events.end_after_start"
_EVENT_TIME_PAIR_KEY = "validation.events.times_required"


def sanitize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


async def create_user(db: AsyncSession, user_in: schemas.UserCreate):
    raw_role = getattr(user_in, "role", None)
    requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT

    code = None
    if hasattr(user_in, "invite_code") and requested_role in (
        UserRole.TEACHER,
        UserRole.ADMIN,
    ):
        code_q = select(models.InviteCode).where(
            models.InviteCode.code == user_in.invite_code,
            models.InviteCode.role == requested_role.value,
            models.InviteCode.is_active.is_(True),
            models.InviteCode.is_used.is_(False),
        )
        code = (await db.execute(code_q)).scalar_one_or_none()
        if not code:
            raise ValueError(translate("errors.users.invalid_invite"))

    exists = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == user_in.email.strip().lower()
        )
    )
    if exists.scalar_one_or_none():
        raise ValueError(translate("errors.users.email_in_use"))

    hashed_password = get_password_hash(user_in.password)
    db_user = models.User(
        email=user_in.email.strip(),
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        role=requested_role.value,
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
        raise ValueError(translate("errors.users.create_failed"))

    await db.refresh(db_user)

    if code:
        code.is_used = True
        code.is_active = False
        code.used_by_user_id = db_user.id
        db.add(code)
        await db.commit()

    return db_user


async def create_news(db: AsyncSession, news: schemas.NewsCreate):
    payload = news.model_dump()
    payload["title_en"] = sanitize_optional_text(payload.get("title_en"))
    payload["content_en"] = sanitize_optional_text(payload.get("content_en"))

    record = models.News(**payload)
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


def _localized_event_field(
    locale: str | None,
    ru_value: str | None,
    en_value: str | None,
    *,
    required: bool = False,
) -> str | None:
    ru_clean = sanitize_optional_text(ru_value)
    en_clean = sanitize_optional_text(en_value)
    value = localized_text(locale, ru=ru_clean, en=en_clean)
    if value is not None:
        return value
    if required:
        if isinstance(ru_value, str) and ru_value.strip():
            return ru_value
        if isinstance(en_value, str) and en_value.strip():
            return en_value
        return ru_value or en_value or ""
    return ru_clean or en_clean


def serialize_event(
    record: models.Event,
    locale: str | None,
    *,
    participant_count: int = 0,
    files: Sequence[models.EventFile | schemas.EventFileOut] = (),
    is_registered: bool | None = None,
    my_qr_code: str | None = None,
) -> schemas.EventOut:
    normalized_locale = normalize_locale(locale)
    prepared_files: list[schemas.EventFileOut] = []
    for f in files:
        if isinstance(f, schemas.EventFileOut):
            prepared_files.append(f)
        else:
            prepared_files.append(schemas.EventFileOut.from_orm(f))

    data: dict[str, Any] = {
        "id": record.id,
        "title": _localized_event_field(
            normalized_locale, getattr(record, "title", None), getattr(record, "title_en", None), required=True
        ),
        "description": _localized_event_field(
            normalized_locale,
            getattr(record, "description", None),
            getattr(record, "description_en", None),
        ),
        "title_en": sanitize_optional_text(getattr(record, "title_en", None)),
        "description_en": sanitize_optional_text(getattr(record, "description_en", None)),
        "location": _localized_event_field(
            normalized_locale,
            getattr(record, "location", None),
            getattr(record, "location_en", None),
        ),
        "location_en": sanitize_optional_text(getattr(record, "location_en", None)),
        "event_type": _localized_event_field(
            normalized_locale,
            getattr(record, "event_type", None),
            getattr(record, "event_type_en", None),
        ),
        "event_type_en": sanitize_optional_text(getattr(record, "event_type_en", None)),
        "starts_at": record.starts_at,
        "ends_at": record.ends_at,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "is_active": getattr(record, "is_active", True),
        "speaker": getattr(record, "speaker", None),
        "image_url": getattr(record, "image_url", None),
        "about": _localized_event_field(
            normalized_locale,
            getattr(record, "about", None),
            getattr(record, "about_en", None),
        ),
        "about_en": sanitize_optional_text(getattr(record, "about_en", None)),
        "files": prepared_files,
        "participant_count": participant_count,
        "is_registered": is_registered,
        "my_qr_code": my_qr_code,
    }

    return schemas.EventOut.model_validate(data)


async def get_all_events(
    db: AsyncSession,
    user_id: int | None = None,
    search: str = "",
    type: str = "",
    location: str = "",
    is_active: bool = True,
    locale: str | None = None,
):
    q = select(models.Event)
    now = datetime.now(UTC)

    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                models.Event.title.ilike(like),
                models.Event.title_en.ilike(like),
                models.Event.description.ilike(like),
                models.Event.description_en.ilike(like),
                models.Event.about.ilike(like),
                models.Event.about_en.ilike(like),
            )
        )
    if type:
        q = q.where(
            or_(
                models.Event.event_type == type,
                models.Event.event_type_en == type,
            )
        )
    if location:
        like = f"%{location}%"
        q = q.where(
            or_(
                models.Event.location.ilike(like),
                models.Event.location_en.ilike(like),
            )
        )
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

    registered_ids: set[int] = set()
    qr_map: Dict[int, Optional[str]] = {}
    if user_id:
        attendance_rows = (
            (
                await db.execute(
                    select(models.EventAttendance).where(
                        models.EventAttendance.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        missing_qr = [row for row in attendance_rows if not row.qr_code]
        if missing_qr:
            for row in missing_qr:
                row.qr_code = str(uuid.uuid4())
            await db.commit()
            for row in missing_qr:
                await db.refresh(row)
        registered_ids = {row.event_id for row in attendance_rows}
        qr_map = {row.event_id: row.qr_code for row in attendance_rows}

    result: List[schemas.EventOut] = []
    normalized_locale = normalize_locale(locale)
    for event in events:
        files = files_map.get(event.id, [])
        result.append(
            serialize_event(
                event,
                normalized_locale,
                participant_count=counts.get(event.id, 0),
                files=files,
                is_registered=event.id in registered_ids,
                my_qr_code=qr_map.get(event.id),
            )
        )
    return result


async def create_event(db: AsyncSession, event: schemas.EventCreate, user_id: int):
    starts_at = _ensure_utc(event.starts_at)
    ends_at = _ensure_utc(event.ends_at)
    if ends_at <= starts_at:
        raise ValueError(translate(_EVENT_TIME_ORDER_KEY))
    record = models.Event(
        title=event.title,
        description=event.description,
        about=getattr(event, "about", None),
        about_en=sanitize_optional_text(getattr(event, "about_en", None)),
        event_type=getattr(event, "event_type", None),
        event_type_en=sanitize_optional_text(getattr(event, "event_type_en", None)),
        location=event.location,
        location_en=sanitize_optional_text(getattr(event, "location_en", None)),
        title_en=sanitize_optional_text(getattr(event, "title_en", None)),
        description_en=sanitize_optional_text(getattr(event, "description_en", None)),
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=user_id,
        speaker=getattr(event, "speaker", None),
        image_url=getattr(event, "image_url", None),
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "ck_event_time_order" in str(exc.orig):
            raise ValueError(translate(_EVENT_TIME_ORDER_KEY)) from None
        raise
    await db.refresh(record)
    return record


async def update_event(
    db: AsyncSession, record: models.Event, data: schemas.EventUpdate
) -> models.Event:
    updates = data.model_dump(exclude_unset=True)
    for field in (
        "title_en",
        "description_en",
        "location_en",
        "event_type_en",
        "about_en",
    ):
        if field in updates:
            updates[field] = sanitize_optional_text(updates[field])
    if not updates:
        return record
    if "starts_at" in updates:
        updates["starts_at"] = _ensure_utc(updates["starts_at"])
    if "ends_at" in updates:
        updates["ends_at"] = _ensure_utc(updates["ends_at"])
    starts_set = "starts_at" in updates
    ends_set = "ends_at" in updates
    if starts_set ^ ends_set:
        raise ValueError(translate(_EVENT_TIME_PAIR_KEY))
    if starts_set or ends_set:
        starts_at = updates.get("starts_at", record.starts_at)
        ends_at = updates.get("ends_at", record.ends_at)
        if starts_at is None or ends_at is None:
            raise ValueError(translate(_EVENT_TIME_PAIR_KEY))
        if ends_at <= starts_at:
            raise ValueError(translate(_EVENT_TIME_ORDER_KEY))
    for field, value in updates.items():
        setattr(record, field, value)
    db.add(record)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "ck_event_time_order" in str(exc.orig):
            raise ValueError(translate(_EVENT_TIME_ORDER_KEY)) from None
        raise
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
        if not exist.qr_code:
            exist.qr_code = str(uuid.uuid4())
            await db.commit()
            await db.refresh(exist)
        return exist

    qr_code = str(uuid.uuid4())
    record = models.EventAttendance(
        user_id=user_id, event_id=data.event_id, qr_code=qr_code
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        exist = (await db.execute(stmt)).scalar_one_or_none()
        if not exist:
            raise
        if not exist.qr_code:
            exist.qr_code = str(uuid.uuid4())
            await db.commit()
            await db.refresh(exist)
        return exist
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


async def get_my_events(
    db: AsyncSession, user_id: int, *, locale: str | None = None
):
    attendance_rows = (
        (
            await db.execute(
                select(models.EventAttendance).where(
                    models.EventAttendance.user_id == user_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not attendance_rows:
        return []
    missing_qr = [row for row in attendance_rows if not row.qr_code]
    if missing_qr:
        for row in missing_qr:
            row.qr_code = str(uuid.uuid4())
        await db.commit()
        for row in missing_qr:
            await db.refresh(row)
    ids = [row.event_id for row in attendance_rows]
    qr_map = {row.event_id: row.qr_code for row in attendance_rows}
    q = select(models.Event).where(models.Event.id.in_(ids))
    events = (await db.execute(q)).scalars().all()
    counts = await _attendance_counts(db, ids)
    files_map = await _files_by_event(db, ids)

    normalized_locale = normalize_locale(locale)
    result: List[schemas.EventOut] = []
    for event in events:
        files = files_map.get(event.id, [])
        result.append(
            serialize_event(
                event,
                normalized_locale,
                participant_count=counts.get(event.id, 0),
                files=files,
                is_registered=True,
                my_qr_code=qr_map.get(event.id),
            )
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
    start_time = _ensure_utc(data.start_time)
    end_time = _ensure_utc(data.end_time)
    record = models.Schedule(
        group_id=data.group_id,
        subject=data.subject,
        teacher=data.teacher,
        room=data.room,
        weekday=data.weekday,
        start_time=start_time,
        end_time=end_time,
        parity=getattr(data, "parity", "both"),
        lesson_type=getattr(
            data,
            "lesson_type",
            translate("schedule.lesson.default_type", locale="ru"),
        ),
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
        raise ValueError(translate("errors.users.not_found"))
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int):
    user = await db.get(models.User, user_id)
    if not user:
        raise ValueError(translate("errors.users.not_found"))
    await db.delete(user)
    await db.commit()
