import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth.security import get_password_hash
from app.core.config import settings
from app.deps.cache import BaseCache
from app.localization import localized_text, normalize_locale, translate
from app.models import models
from app.models.enums import UserRole
from app.models.user_loaders import (
    USER_MFA_LOAD_OPTIONS,
    ensure_mfa_relationships_loaded,
)
from app.schemas import schemas
from app.services import attendance_tokens, stats_cache


async def get_user_auth(db: AsyncSession, login: str):
    login_norm = login.strip().lower()
    stmt = select(models.User).where(func.lower(models.User.email) == login_norm)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _decode_event_cursor(value: str | None) -> tuple[datetime, int] | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw_starts_at = payload.get("starts_at")
    raw_id = payload.get("id")
    if not isinstance(raw_starts_at, str):
        return None
    try:
        parsed_starts_at = datetime.fromisoformat(raw_starts_at)
    except ValueError:
        return None
    try:
        event_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return _ensure_utc(parsed_starts_at), event_id


def _encode_event_cursor(starts_at: datetime, event_id: int) -> str:
    return json.dumps(
        {
            "starts_at": _ensure_utc(starts_at).isoformat(),
            "id": int(event_id),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


_EVENT_TIME_ORDER_KEY = "validation.events.end_after_start"
_EVENT_TIME_PAIR_KEY = "validation.events.times_required"


def sanitize_optional_text(value: Any) -> str | None:
    """Normalize optional text values to strings."""

    if value is None:
        return None
    if isinstance(value, bytes | bytearray):
        try:
            decoded = value.decode("utf-8")
        except Exception:
            decoded = value.decode("utf-8", "ignore")
        return decoded if decoded.strip() else None
    if isinstance(value, str):
        return value if value.strip() else None
    text = str(value)
    return text if text.strip() else None


async def _is_postgres_session(session: AsyncSession) -> bool:
    """Return ``True`` when the bound engine speaks PostgreSQL."""

    bind = session.bind
    if bind is None:
        try:
            bind = await session.get_bind()
        except Exception:  # pragma: no cover - defensive guard
            return False
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", "") or ""
    return name.lower().startswith("postgres")


async def create_user(db: AsyncSession, user_in: schemas.UserCreate):
    raw_role = getattr(user_in, "role", None)
    requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT

    normalized_email = user_in.email.strip().lower()

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
        select(models.User).where(func.lower(models.User.email) == normalized_email)
    )
    if exists.scalar_one_or_none():
        raise ValueError(translate("errors.users.email_in_use"))

    hashed_password = get_password_hash(user_in.password)
    db_user = models.User(
        email=normalized_email,
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
        mfa_required=settings.mfa_enabled,
        mfa_default_method=settings.mfa_default_method,
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

    await ensure_mfa_relationships_loaded(db, db_user)

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


async def create_story(
    db: AsyncSession,
    story: schemas.StoryCreate,
    *,
    created_by: int | None = None,
):
    payload = story.model_dump()
    payload["title_en"] = sanitize_optional_text(payload.get("title_en"))
    payload["short_text_en"] = sanitize_optional_text(payload.get("short_text_en"))
    payload["cover_url"] = sanitize_optional_text(payload.get("cover_url"))
    payload["cta_url"] = sanitize_optional_text(payload.get("cta_url"))

    published_at = payload.get("published_at")
    expires_at = payload.get("expires_at")
    if published_at is not None:
        payload["published_at"] = _ensure_utc(published_at)
    if expires_at is not None:
        payload["expires_at"] = _ensure_utc(expires_at)
    if created_by is not None:
        payload["created_by"] = created_by

    record = models.Story(**payload)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_story(
    db: AsyncSession,
    story: models.Story,
    updates: schemas.StoryUpdate | None,
) -> models.Story:
    payload = updates.model_dump(exclude_unset=True) if updates else {}
    if "title_en" in payload:
        payload["title_en"] = sanitize_optional_text(payload.get("title_en"))
    if "short_text_en" in payload:
        payload["short_text_en"] = sanitize_optional_text(payload.get("short_text_en"))
    if "cover_url" in payload:
        payload["cover_url"] = sanitize_optional_text(payload.get("cover_url"))
    if "cta_url" in payload:
        payload["cta_url"] = sanitize_optional_text(payload.get("cta_url"))
    if "published_at" in payload and payload["published_at"] is not None:
        payload["published_at"] = _ensure_utc(payload["published_at"])
    if "expires_at" in payload and payload["expires_at"] is not None:
        payload["expires_at"] = _ensure_utc(payload["expires_at"])

    for field, value in payload.items():
        setattr(story, field, value)

    await db.commit()
    await db.refresh(story)
    return story


async def list_active_stories(
    db: AsyncSession,
    *,
    reference_time: datetime | None = None,
) -> list[models.Story]:
    now = reference_time or datetime.now(UTC)
    now_utc = _ensure_utc(now)
    stmt = (
        select(models.Story)
        .where(
            models.Story.is_active.is_(True),
            models.Story.published_at <= now_utc,
            models.Story.expires_at > now_utc,
        )
        .order_by(models.Story.published_at.desc(), models.Story.id.desc())
    )
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


async def delete_story(db: AsyncSession, story: models.Story) -> None:
    await db.delete(story)
    await db.commit()


def serialize_story(
    story: models.Story | schemas.StoryOut,
    locale: str | None,
) -> schemas.StoryOut:
    normalized_locale = normalize_locale(locale)
    story_out = (
        story
        if isinstance(story, schemas.StoryOut)
        else schemas.StoryOut.model_validate(story)
    )
    data = story_out.model_dump()
    data["title"] = localized_text(
        normalized_locale,
        ru=data.get("title"),
        en=data.get("title_en"),
    ) or (data.get("title") or "")
    data["short_text"] = localized_text(
        normalized_locale,
        ru=data.get("short_text"),
        en=data.get("short_text_en"),
    ) or (data.get("short_text") or "")
    return schemas.StoryOut.model_validate(data)


async def _attendance_counts(db: AsyncSession, event_ids: list[int]) -> dict[int, int]:
    if not event_ids:
        return {}
    rows = await db.execute(
        select(models.EventAttendance.event_id, func.count(models.EventAttendance.id))
        .where(models.EventAttendance.event_id.in_(event_ids))
        .group_by(models.EventAttendance.event_id)
    )
    return {eid: cnt for eid, cnt in rows.all()}


async def _files_by_event(
    db: AsyncSession, event_ids: list[int]
) -> dict[int, list[models.EventFile]]:
    if not event_ids:
        return {}
    rows = await db.execute(
        select(models.EventFile).where(models.EventFile.event_id.in_(event_ids))
    )
    files = rows.scalars().all()
    out: dict[int, list[models.EventFile]] = {}
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
    my_qr_token: str | None = None,
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
            normalized_locale,
            getattr(record, "title", None),
            getattr(record, "title_en", None),
            required=True,
        ),
        "description": _localized_event_field(
            normalized_locale,
            getattr(record, "description", None),
            getattr(record, "description_en", None),
        ),
        "title_en": sanitize_optional_text(getattr(record, "title_en", None)),
        "description_en": sanitize_optional_text(
            getattr(record, "description_en", None)
        ),
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
        "my_qr_token": my_qr_token,
    }

    return schemas.EventOut.model_validate(data)


DEFAULT_EVENTS_LIMIT = 20
MAX_EVENTS_LIMIT = 50


async def get_all_events(
    db: AsyncSession,
    user_id: int | None = None,
    search: str = "",
    type: str = "",
    location: str = "",
    is_active: bool = True,
    locale: str | None = None,
    *,
    limit: int | None = None,
    cursor: str | None = None,
):
    now = datetime.now(UTC)
    safe_limit = max(1, min(MAX_EVENTS_LIMIT, limit or DEFAULT_EVENTS_LIMIT))
    cursor_values = _decode_event_cursor(cursor)

    conditions = []
    rank_expr = None
    if search:
        if await _is_postgres_session(db):
            ts_query = func.plainto_tsquery("simple", search)
            conditions.append(models.Event.search_vector.op("@@")(ts_query))
            rank_expr = func.ts_rank(models.Event.search_vector, ts_query)
        else:
            like = f"%{search}%"
            conditions.append(
                or_(
                    models.Event.title.ilike(like),
                    models.Event.title_en.ilike(like),
                    models.Event.description.ilike(like),
                    models.Event.description_en.ilike(like),
                    models.Event.location.ilike(like),
                    models.Event.location_en.ilike(like),
                    models.Event.about.ilike(like),
                    models.Event.about_en.ilike(like),
                )
            )
    if type:
        conditions.append(
            or_(
                models.Event.event_type == type,
                models.Event.event_type_en == type,
            )
        )
    if location:
        like = f"%{location}%"
        conditions.append(
            or_(
                models.Event.location.ilike(like),
                models.Event.location_en.ilike(like),
            )
        )
    if is_active:
        conditions.append(models.Event.ends_at >= now)
    else:
        conditions.append(models.Event.ends_at < now)

    stmt = select(models.Event)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    if cursor_values:
        last_starts_at, last_id = cursor_values
        stmt = stmt.where(
            or_(
                models.Event.starts_at > last_starts_at,
                and_(
                    models.Event.starts_at == last_starts_at,
                    models.Event.id > last_id,
                ),
            )
        )

    if rank_expr is not None:
        ordered_stmt = stmt.order_by(
            rank_expr.desc(), models.Event.starts_at.asc(), models.Event.id.asc()
        )
    else:
        ordered_stmt = stmt.order_by(
            models.Event.starts_at.asc(), models.Event.id.asc()
        )
    page_stmt = ordered_stmt.limit(safe_limit + 1)
    rows = await db.execute(page_stmt)
    fetched_events = rows.scalars().all()
    events = fetched_events[:safe_limit]
    ids = [e.id for e in events]
    counts = await _attendance_counts(db, ids)
    files_map = await _files_by_event(db, ids)

    total_stmt = select(func.count()).select_from(models.Event)
    if conditions:
        total_stmt = total_stmt.where(and_(*conditions))
    total = (await db.execute(total_stmt)).scalar_one()

    registered_ids: set[int] = set()
    qr_map: dict[int, str | None] = {}
    if user_id and ids:
        attendance_rows = (
            (
                await db.execute(
                    select(models.EventAttendance).where(
                        and_(
                            models.EventAttendance.user_id == user_id,
                            models.EventAttendance.event_id.in_(ids),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        updated_rows: list[models.EventAttendance] = []
        for row in attendance_rows:
            if attendance_tokens.ensure_secret_material(row):
                db.add(row)
                updated_rows.append(row)
        if updated_rows:
            await db.commit()
            for row in updated_rows:
                await db.refresh(row)
        registered_ids = {row.event_id for row in attendance_rows}
        qr_map = {
            row.event_id: attendance_tokens.issue_token(row) for row in attendance_rows
        }

    normalized_locale = normalize_locale(locale)
    result: list[schemas.EventOut] = []
    for event in events:
        files = files_map.get(event.id, [])
        result.append(
            serialize_event(
                event,
                normalized_locale,
                participant_count=counts.get(event.id, 0),
                files=files,
                is_registered=event.id in registered_ids,
                my_qr_token=qr_map.get(event.id),
            )
        )

    has_more = len(fetched_events) > len(events)
    next_cursor: str | None = None
    if has_more and events:
        last_event = events[-1]
        next_cursor = _encode_event_cursor(last_event.starts_at, last_event.id)

    return schemas.PaginatedEvents(
        items=result,
        total=total,
        limit=safe_limit,
        cursor=cursor if cursor_values else None,
        next_cursor=next_cursor,
        has_more=has_more,
    )


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
    cache_kinds = ("attendance", "participation")
    stmt = select(models.EventAttendance).where(
        and_(
            models.EventAttendance.event_id == data.event_id,
            models.EventAttendance.user_id == user_id,
        )
    )
    exist = (await db.execute(stmt)).scalar_one_or_none()
    if exist:
        updated = False
        if exist.registered_at is None:
            exist.registered_at = datetime.now(UTC)
            updated = True
        if attendance_tokens.ensure_secret_material(exist):
            updated = True
        if updated:
            db.add(exist)
            await db.commit()
            await db.refresh(exist)
        exist.qr_token = attendance_tokens.issue_token(exist)
        await stats_cache.invalidate_user_stats_cache(
            user_ids=user_id,
            kinds=cache_kinds,
        )
        return exist

    secret = attendance_tokens.generate_secret()
    record = models.EventAttendance(
        user_id=user_id,
        event_id=data.event_id,
        qr_secret=secret,
        qr_hmac=attendance_tokens.compute_secret_hmac(secret),
        registered_at=datetime.now(UTC),
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        exist = (await db.execute(stmt)).scalar_one_or_none()
        if not exist:
            event = await db.get(models.Event, data.event_id)
            if not event:
                raise LookupError("event_not_found") from None
            raise ValueError("attendance_registration_failed") from None
        updated = False
        if exist.registered_at is None:
            exist.registered_at = datetime.now(UTC)
            updated = True
        if attendance_tokens.ensure_secret_material(exist):
            updated = True
        if updated:
            db.add(exist)
            await db.commit()
            await db.refresh(exist)
        exist.qr_token = attendance_tokens.issue_token(exist)
        await stats_cache.invalidate_user_stats_cache(
            user_ids=user_id,
            kinds=cache_kinds,
        )
        return exist
    await db.refresh(record)
    record.qr_token = attendance_tokens.issue_token(record)
    await stats_cache.invalidate_user_stats_cache(
        user_ids=user_id,
        kinds=cache_kinds,
    )
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
    await stats_cache.invalidate_user_stats_cache(
        user_ids=user_id,
        kinds=("attendance", "participation"),
    )
    return {"ok": True}


async def get_my_events(db: AsyncSession, user_id: int, *, locale: str | None = None):
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
    updated_rows: list[models.EventAttendance] = []
    for row in attendance_rows:
        if attendance_tokens.ensure_secret_material(row):
            db.add(row)
            updated_rows.append(row)
    if updated_rows:
        await db.commit()
        for row in updated_rows:
            await db.refresh(row)
    ids = [row.event_id for row in attendance_rows]
    qr_map = {
        row.event_id: attendance_tokens.issue_token(row) for row in attendance_rows
    }
    q = select(models.Event).where(models.Event.id.in_(ids))
    events = (await db.execute(q)).scalars().all()
    counts = await _attendance_counts(db, ids)
    files_map = await _files_by_event(db, ids)

    normalized_locale = normalize_locale(locale)
    result: list[schemas.EventOut] = []
    for event in events:
        files = files_map.get(event.id, [])
        result.append(
            serialize_event(
                event,
                normalized_locale,
                participant_count=counts.get(event.id, 0),
                files=files,
                is_registered=True,
                my_qr_token=qr_map.get(event.id),
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
        lesson_type=getattr(data, "lesson_type", None),
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
    group_id: int | None = None,
    full_name: str | None = None,
    role: str | None = None,
) -> list[models.User]:
    stmt = select(models.User).options(*USER_MFA_LOAD_OPTIONS)
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
) -> tuple[models.User, mfa.MfaResetStats | None]:
    user = await db.get(models.User, user_id)
    if not user:
        raise ValueError(translate("errors.users.not_found"))
    payload = data.model_dump(exclude_unset=True)
    reset_requested = bool(payload.pop("reset_mfa", False))
    if "email" in payload and payload["email"] is not None:
        payload["email"] = str(payload["email"]).strip().lower()
    for field, value in payload.items():
        setattr(user, field, value)
    reset_stats: mfa.MfaResetStats | None = None
    if reset_requested:
        reset_stats = await mfa.reset_user_mfa(db, user=user)
    await db.commit()
    await db.refresh(user)
    await ensure_mfa_relationships_loaded(db, user)
    return user, reset_stats


async def delete_user(db: AsyncSession, user_id: int):
    user = await db.get(models.User, user_id)
    if not user:
        raise ValueError(translate("errors.users.not_found"))
    await db.delete(user)
    await db.commit()


def _dt_to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


async def get_attendance_stats(
    db: AsyncSession,
    *,
    user_id: int,
    period_days: int,
    period_key: str | None = None,
    cache: BaseCache | None = None,
    skip_cache: bool = False,
) -> dict[str, Any]:
    cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
    cached = await stats_cache.get_cached_stats(
        cache=cache,
        kind="attendance",
        user_id=user_id,
        period_key=cache_period_key,
        skip_cache=skip_cache,
    )
    if cached is not None:
        return cached

    now = datetime.now(UTC)
    window_start = now - timedelta(days=period_days)
    previous_start = window_start - timedelta(days=period_days)

    base_event_filter = (
        models.Event.is_active.is_(True),
        models.Event.starts_at >= window_start,
        models.Event.starts_at < now,
    )
    total_events = await db.scalar(
        select(func.count()).select_from(models.Event).where(*base_event_filter)
    )
    total_events = int(total_events or 0)

    attendance_filter = (
        models.EventAttendance.user_id == user_id,
        models.EventAttendance.event_id == models.Event.id,
        *base_event_filter,
    )
    attended_events = await db.scalar(
        select(func.count())
        .select_from(models.EventAttendance)
        .join(models.Event, models.Event.id == models.EventAttendance.event_id)
        .where(*attendance_filter)
    )
    attended_events = int(attended_events or 0)

    percent = (attended_events / total_events * 100) if total_events else 0.0

    previous_events = await db.scalar(
        select(func.count())
        .select_from(models.Event)
        .where(
            models.Event.is_active.is_(True),
            models.Event.starts_at >= previous_start,
            models.Event.starts_at < window_start,
        )
    )
    previous_events = int(previous_events or 0)

    previous_attended = await db.scalar(
        select(func.count())
        .select_from(models.EventAttendance)
        .join(models.Event, models.Event.id == models.EventAttendance.event_id)
        .where(
            models.EventAttendance.user_id == user_id,
            models.Event.starts_at >= previous_start,
            models.Event.starts_at < window_start,
            models.Event.is_active.is_(True),
        )
    )
    previous_attended = int(previous_attended or 0)
    previous_percent = (
        previous_attended / previous_events * 100 if previous_events else 0.0
    )

    recent_rows = await db.execute(
        select(
            models.EventAttendance.registered_at,
            models.Event.starts_at,
            models.Event.title,
        )
        .join(models.Event, models.Event.id == models.EventAttendance.event_id)
        .where(*attendance_filter)
        .order_by(models.EventAttendance.registered_at.desc())
        .limit(5)
    )
    recent = []
    for registered_at, starts_at, title in recent_rows.all():
        date_source = starts_at or registered_at
        recent.append(
            {
                "date": _dt_to_iso(date_source),
                "status": "present",
                "course": title or None,
            }
        )

    result = {
        "percent": round(percent, 2),
        "present": attended_events,
        "total": total_events,
        "trend": round(percent - previous_percent, 2),
        "period_key": cache_period_key,
        "recent": recent,
    }
    await stats_cache.set_cached_stats(
        cache=cache,
        kind="attendance",
        user_id=user_id,
        period_key=cache_period_key,
        payload=result,
        skip_cache=skip_cache,
    )
    return result


def _parse_grade_payload(
    body: str | None, *, fallback_title: str, fallback_date: datetime | None
) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    score = payload.get("score")
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return None
    max_score = payload.get("max")
    max_value = None
    if max_score is not None:
        try:
            max_value = float(max_score)
        except (TypeError, ValueError):
            max_value = None
    course = payload.get("course")
    if not isinstance(course, str) or not course.strip():
        course = fallback_title
    date_raw = payload.get("date")
    if isinstance(date_raw, str):
        try:
            parsed = datetime.fromisoformat(date_raw)
        except ValueError:
            parsed = None
    else:
        parsed = None
    date_value = parsed or fallback_date
    return {
        "course": course,
        "score": score_value,
        "max": max_value,
        "date": _dt_to_iso(date_value),
    }


async def get_grade_stats(
    db: AsyncSession,
    *,
    user_id: int,
    period_days: int,
    period_key: str | None = None,
    cache: BaseCache | None = None,
    skip_cache: bool = False,
) -> dict[str, Any]:
    cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
    cached = await stats_cache.get_cached_stats(
        cache=cache,
        kind="grades",
        user_id=user_id,
        period_key=cache_period_key,
        skip_cache=skip_cache,
    )
    if cached is not None:
        return cached

    now = datetime.now(UTC)
    window_start = now - timedelta(days=period_days)
    previous_start = window_start - timedelta(days=period_days)

    current_rows = await db.execute(
        select(models.Notification)
        .where(
            models.Notification.user_id == user_id,
            models.Notification.type == "grade",
            models.Notification.created_at >= window_start,
            models.Notification.created_at < now,
        )
        .order_by(models.Notification.created_at.desc())
    )
    current_entries = []
    for notification in current_rows.scalars():
        entry = _parse_grade_payload(
            notification.body,
            fallback_title=notification.title or "",
            fallback_date=notification.created_at,
        )
        if entry:
            current_entries.append(entry)

    previous_rows = await db.execute(
        select(models.Notification).where(
            models.Notification.user_id == user_id,
            models.Notification.type == "grade",
            models.Notification.created_at >= previous_start,
            models.Notification.created_at < window_start,
        )
    )
    previous_entries = []
    for notification in previous_rows.scalars():
        entry = _parse_grade_payload(
            notification.body,
            fallback_title=notification.title or "",
            fallback_date=notification.created_at,
        )
        if entry:
            previous_entries.append(entry)

    def _average(items: list[dict[str, Any]]) -> float:
        if not items:
            return 0.0
        return sum(item["score"] for item in items) / len(items)

    average = _average(current_entries)
    previous_average = _average(previous_entries)

    max_values = [item["max"] for item in current_entries if item.get("max")]
    scale = "5"
    if any(value and value > 5 for value in max_values):
        scale = "100"

    recent = current_entries[:5]

    result = {
        "average": round(average, 2) if current_entries else 0.0,
        "scale": scale,
        "trend": round(average - previous_average, 2),
        "recent": recent,
        "period_key": cache_period_key,
    }
    await stats_cache.set_cached_stats(
        cache=cache,
        kind="grades",
        user_id=user_id,
        period_key=cache_period_key,
        payload=result,
        skip_cache=skip_cache,
    )
    return result


async def get_participation_stats(
    db: AsyncSession,
    *,
    user_id: int,
    period_days: int,
    period_key: str | None = None,
    cache: BaseCache | None = None,
    skip_cache: bool = False,
) -> dict[str, Any]:
    cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
    cached = await stats_cache.get_cached_stats(
        cache=cache,
        kind="participation",
        user_id=user_id,
        period_key=cache_period_key,
        skip_cache=skip_cache,
    )
    if cached is not None:
        return cached

    now = datetime.now(UTC)
    window_start = now - timedelta(days=period_days)
    previous_start = window_start - timedelta(days=period_days)

    def _attendance_query(start: datetime, end: datetime):
        return (
            select(
                models.EventAttendance.event_id,
                models.EventAttendance.registered_at,
                models.Event.starts_at,
                models.Event.ends_at,
                models.Event.title,
                models.Event.event_type,
            )
            .join(models.Event, models.Event.id == models.EventAttendance.event_id)
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.starts_at >= start,
                models.Event.starts_at < end,
                models.Event.is_active.is_(True),
            )
        )

    current_rows = await db.execute(
        _attendance_query(window_start, now).order_by(models.Event.starts_at.desc())
    )
    current_entries = current_rows.all()
    previous_rows = await db.execute(_attendance_query(previous_start, window_start))
    previous_entries = previous_rows.all()

    unique_events = {}
    total_hours = 0.0
    event_types = set()
    recent = []
    for (
        event_id,
        registered_at,
        starts_at,
        ends_at,
        title,
        event_type,
    ) in current_entries:
        if event_id not in unique_events:
            unique_events[event_id] = (starts_at, ends_at)
            if starts_at and ends_at:
                start_dt = _ensure_utc(starts_at)
                end_dt = _ensure_utc(ends_at)
                if end_dt > start_dt:
                    total_hours += (end_dt - start_dt).total_seconds() / 3600
        if event_type:
            event_types.add(event_type)
        recent.append(
            {
                "title": title or "",
                "date": _dt_to_iso(starts_at or registered_at),
                "role": event_type or None,
            }
        )

    recent.sort(key=lambda item: item["date"], reverse=True)
    recent = recent[:5]

    previous_event_ids = {row[0] for row in previous_entries}

    result = {
        "events": len(unique_events),
        "hours": round(total_hours, 2) if total_hours else 0.0,
        "groups": len(event_types),
        "trend": len(unique_events) - len(previous_event_ids),
        "recent": recent,
        "period_key": cache_period_key,
    }
    await stats_cache.set_cached_stats(
        cache=cache,
        kind="participation",
        user_id=user_id,
        period_key=cache_period_key,
        payload=result,
        skip_cache=skip_cache,
    )
    return result
