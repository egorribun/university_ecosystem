import hashlib
import logging
import secrets
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app import crud
from app.api.deps import get_current_user
from app.api.spotify import (
    _fallback_now_playing as _spotify_fallback_now_playing,  # noqa: F401
)
from app.auth.security import decode_token
from app.core.config import settings
from app.core.database import get_db
from app.deps.cache import etag_matches, format_etag, get_cache
from app.models import models
from app.schemas import schemas
from app.utils.files import save_image

router = APIRouter()

logger = logging.getLogger(__name__)


def _news_item_cache_key(news_id: int) -> str:
    return f"news:item:{news_id}"


def _schedule_cache_key(group_id: int) -> str:
    return f"schedule:group:{group_id}"


_NEWS_LIST_CACHE_KEY = "news:list"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _redact_sensitive_query(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return "[redacted]"
    redacted_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in {"token", "code"}:
            redacted_items.append((key, "***redacted***"))
        else:
            redacted_items.append((key, value))
    sanitized_query = urlencode(redacted_items, doseq=True)
    sanitized = parts._replace(query=sanitized_query)
    result = urlunsplit(sanitized)
    return result or "[redacted]"


def _send_reset_email(to_email: str, link: str, full_name: str = "") -> None:
    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    mail_from = settings.mail_from or "no-reply@example.com"
    security = (
        settings.smtp_security or ("starttls" if settings.smtp_starttls else "none")
    ).lower()
    name = f", {full_name}" if full_name else ""
    html = f"""
    <div style="font-family:Inter,Arial,sans-serif">
      <h2>Сброс пароля</h2>
      <p>Здравствуйте{name}!</p>
      <p>Вы запросили сброс пароля в Экосистеме ГУУ. Ссылка действует 45 минут.</p>
      <p><a href="{link}" style="display:inline-block;padding:10px 16px;background:#1d5fff;color:#fff;border-radius:8px;text-decoration:none">Сбросить пароль</a></p>
      <p>Если вы не запрашивали сброс, проигнорируйте это письмо.</p>
    </div>
    """
    msg = EmailMessage()
    msg["Subject"] = "Сброс пароля — Экосистема ГУУ"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(f"Ссылка для сброса пароля: {link}\nОна действует 45 минут.")
    msg.add_alternative(html, subtype="html")
    try:
        if not host or not port:
            safe_link = _redact_sensitive_query(link)
            logger.warning(
                "password.reset_email.fallback",
                extra={"email": to_email, "link": safe_link},
            )
            return
        ctx = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        elif security == "starttls":
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except Exception:
        safe_link = _redact_sensitive_query(link)
        logger.error(
            "password.reset_email.error",
            extra={"email": to_email, "link": safe_link},
            exc_info=True,
        )


async def save_upload(file: UploadFile, subdir: str, prefix: str) -> str:
    return await save_image(file, subdir, prefix)


@router.post("/password/forgot")
async def forgot_password(
    payload: schemas.ForgotPasswordIn,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.User).where(models.User.email == payload.email)
    )
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(minutes=45)
        db.add(
            models.PasswordResetToken(
                user_id=user.id, token_hash=token_hash, expires_at=expires, used=False
            )
        )
        await db.commit()
        base = settings.app_base_url_clean
        reset_link = f"{base}/reset-password?token={token}"
        bg.add_task(_send_reset_email, user.email, reset_link, user.full_name or "")
    return {"ok": True}


@router.post("/password/reset")
async def reset_password(
    payload: schemas.ResetPasswordIn, db: AsyncSession = Depends(get_db)
):
    token_hash = _hash_token(payload.token)
    result = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == token_hash,
            models.PasswordResetToken.used.is_(False),  # E712 -> .is_(False)
        )
    )
    rec = result.scalar_one_or_none()
    if not rec or rec.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недействительная или просроченная ссылка",
        )
    user = await db.get(models.User, rec.user_id)
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительная ссылка"
        )
    from app.auth.security import get_password_hash

    try:
        user.hashed_password = get_password_hash(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    rec.used = True
    await db.execute(
        update(models.PasswordResetToken)
        .where(
            models.PasswordResetToken.user_id == rec.user_id,
            models.PasswordResetToken.used.is_(False),  # E712 -> .is_(False)
        )
        .values(used=True)
    )
    await db.commit()
    return {"ok": True}


@router.get("/users/me", response_model=schemas.UserOut)
async def me(user: models.User = Depends(get_current_user)):
    return user


@router.put("/users/me", response_model=schemas.UserOut)
async def update_me(
    data: schemas.UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    db_user = await db.get(models.User, user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(db_user, field, value)
    await db.commit()
    await db.refresh(db_user)
    return db_user


@router.post("/users/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    url = await save_upload(file, "avatars", f"user_{user.id}_avatar")
    db_user = await db.get(models.User, user.id)
    db_user.avatar_url = url
    await db.commit()
    await db.refresh(db_user)
    return db_user


@router.post("/users/me/cover", response_model=schemas.UserOut)
async def upload_cover(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    url = await save_upload(file, "covers", f"user_{user.id}_cover")
    db_user = await db.get(models.User, user.id)
    db_user.cover_url = url
    await db.commit()
    await db.refresh(db_user)
    return db_user


@router.post("/users", response_model=schemas.UserOut)
async def create_user(data: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    code_obj = None
    if data.role in ["teacher", "admin"]:
        if not data.invite_code:
            raise HTTPException(
                status_code=400,
                detail="Необходим уникальный код для регистрации преподавателя/админа",
            )
        q = select(models.InviteCode).where(
            models.InviteCode.code == data.invite_code,
            models.InviteCode.role == data.role,
            models.InviteCode.is_active.is_(True),  # E712 -> .is_(True)
        )
        code_obj = (await db.execute(q)).scalar_one_or_none()
        if not code_obj:
            raise HTTPException(status_code=400, detail="Неверный или неактивный код")
    user = await crud.create_user(db, data)
    return user


@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(
    db: AsyncSession = Depends(get_db),
    full_name: Optional[str] = Query(None),
    group_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.get_users(db, full_name=full_name, group_id=group_id, role=role)


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
async def update_user_admin(
    user_id: int,
    data: schemas.UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.admin_update_user(db, user_id, data)


@router.delete("/users/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    db_user = await db.get(models.User, user.id)
    if db_user.avatar_url:
        base_dir = settings.static_dir_path
        rel_path = db_user.avatar_url.replace("/static/", "", 1).lstrip("/")
        avatar_path = base_dir / Path(rel_path)
        if avatar_path.exists():
            try:
                avatar_path.unlink()
            except Exception:
                pass
    db_user.avatar_url = None
    await db.commit()
    await db.refresh(db_user)
    return db_user


@router.post("/groups", response_model=schemas.GroupOut)
async def create_group(
    data: schemas.GroupCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_group(db, data)


@router.get("/groups", response_model=List[schemas.GroupOut])
async def get_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Group))
    return result.scalars().all()


@router.post("/schedule", response_model=schemas.ScheduleOut)
async def add_schedule(
    data: schemas.ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    result = await crud.create_schedule(db, data)
    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(result.group_id))
    return result


@router.get("/schedule/{group_id}", response_model=List[schemas.ScheduleOut])
async def get_schedule(
    group_id: int,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    cache = get_cache()
    cache_key = _schedule_cache_key(group_id)
    if cache.enabled:
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload

    rows = await crud.get_schedule_by_group(db, group_id)
    models_out = [schemas.ScheduleOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)

    if cache.enabled:
        entry = await cache.set(cache_key, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


@router.patch("/schedule/{schedule_id}", response_model=schemas.ScheduleOut)
async def update_schedule(
    schedule_id: int,
    data: schemas.ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    previous_group = sched.group_id
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sched, field, value)
    await db.commit()
    await db.refresh(sched)
    cache = get_cache()
    await cache.invalidate(
        _schedule_cache_key(previous_group),
        _schedule_cache_key(sched.group_id),
    )
    return sched


@router.delete("/schedule/{schedule_id}", response_model=dict)
async def delete_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    group_id = sched.group_id
    await db.delete(sched)
    await db.commit()
    cache = get_cache()
    await cache.invalidate(_schedule_cache_key(group_id))
    return {"ok": True}


@router.post("/events", response_model=schemas.EventOut)
async def create_event(
    data: schemas.EventCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_event(db, data, user_id=user.id)


@router.get("/events", response_model=List[schemas.EventOut])
async def all_events(
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
    search: str = Query("", alias="search"),
    type: str = Query("", alias="type"),
    location: str = Query("", alias="location"),
    is_active: bool = Query(True, alias="is_active"),
):
    return await crud.get_all_events(
        db,
        user_id=user.id,
        search=search,
        type=type,
        location=location,
        is_active=is_active,
    )


@router.post("/events/attendance", response_model=schemas.EventAttendanceOut)
async def attend(
    data: schemas.EventAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role in ("admin", "teacher"):
        raise HTTPException(
            status_code=403,
            detail="Регистрация на мероприятия недоступна для вашей роли",
        )
    return await crud.register_attendance(db, data, user_id=user.id)


@router.delete("/events/attendance", response_model=dict)
async def unregister_event(
    data: schemas.EventAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return await crud.unregister_attendance(db, data, user_id=user.id)


@router.get("/events/my", response_model=List[schemas.EventOut])
async def my_events(
    db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)
):
    return await crud.get_my_events(db, user_id=user.id)


@router.post("/events/{id}/upload_file", response_model=schemas.EventFileOut)
async def upload_event_file(
    id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    event = await db.get(models.Event, id)
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    ext = file.filename.split(".")[-1].lower()
    filename = f"event_{id}_{uuid.uuid4()}.{ext}"
    base_dir = settings.static_dir_path
    folder = base_dir / "event_files"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    data = await file.read()
    file_path.write_bytes(data)
    ef = models.EventFile(event_id=id, file_url=f"/static/event_files/{filename}")
    db.add(ef)
    await db.commit()
    await db.refresh(ef)
    return ef


@router.get("/events/{id}/files", response_model=List[schemas.EventFileOut])
async def get_event_files(id: int, db: AsyncSession = Depends(get_db)):
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == id)
            )
        )
        .scalars()
        .all()
    )
    return files


@router.post("/events/upload_image")
async def upload_event_image(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_upload(file, "event_images", "event")
    return {"url": url}


@router.patch("/events/{event_id}", response_model=schemas.EventOut)
async def update_event(
    event_id: int,
    data: schemas.EventUpdate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(q, field, value)
    await db.commit()
    await db.refresh(q)
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    return out


@router.delete("/events/{event_id}", response_model=dict)
async def delete_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    await db.delete(q)
    await db.commit()
    return {"ok": True}


@router.get("/events/{id}", response_model=schemas.EventOut)
async def get_event(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = await db.get(models.Event, id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    files = (
        (
            await db.execute(
                select(models.EventFile).where(models.EventFile.event_id == q.id)
            )
        )
        .scalars()
        .all()
    )
    participant_count = (
        await db.execute(
            select(func.count())
            .select_from(models.EventAttendance)
            .where(models.EventAttendance.event_id == q.id)
        )
    ).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    return out


@router.delete("/events/file/{file_id}", response_model=dict)
async def delete_event_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ef = await db.get(models.EventFile, file_id)
    if not ef:
        raise HTTPException(status_code=404, detail="Файл не найден")
    event = await db.get(models.Event, ef.event_id)
    if user.role not in ("admin", "teacher") and event.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    await db.delete(ef)
    await db.commit()
    return {"ok": True}


@router.post("/news", response_model=schemas.NewsOut)
async def create_news(
    data: schemas.NewsCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await crud.create_news(db, data)
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY)
    return record


@router.get("/news", response_model=List[schemas.NewsOut])
async def news_list(
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    cache = get_cache()
    if cache.enabled:
        cached = await cache.get(_NEWS_LIST_CACHE_KEY)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload

    rows = await crud.get_news_list(db)
    models_out = [schemas.NewsOut.model_validate(item) for item in rows]
    payload = jsonable_encoder(models_out)

    if cache.enabled:
        entry = await cache.set(_NEWS_LIST_CACHE_KEY, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


@router.get("/news/{id}", response_model=schemas.NewsOut)
async def get_news(
    id: int,
    response: Response,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    cache = get_cache()
    cache_key = _news_item_cache_key(id)
    if cache.enabled:
        cached = await cache.get(cache_key)
        if cached:
            etag_header = format_etag(cached.etag)
            if etag_matches(cached.etag, if_none_match):
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": etag_header},
                )
            response.headers["ETag"] = etag_header
            return cached.payload
    q = await db.get(models.News, id)
    if not q:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    model_out = schemas.NewsOut.model_validate(q)
    payload = jsonable_encoder(model_out)
    if cache.enabled:
        entry = await cache.set(cache_key, payload)
        response.headers["ETag"] = format_etag(entry.etag)
    return payload


@router.patch("/news/{id}", response_model=schemas.NewsOut)
async def update_news(
    id: int,
    data: schemas.NewsCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(news, field, value)
    await db.commit()
    await db.refresh(news)
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY, _news_item_cache_key(id))
    return news


@router.delete("/news/{id}", response_model=dict)
async def delete_news(
    id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    await db.delete(news)
    await db.commit()
    cache = get_cache()
    await cache.invalidate(_NEWS_LIST_CACHE_KEY, _news_item_cache_key(id))
    return {"ok": True}


@router.post("/news/upload_image")
async def upload_news_image(
    file: UploadFile = File(...), user: models.User = Depends(get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_upload(file, "news_images", "news")
    return {"url": url}


@router.get("/activity/{id}")
async def get_activity(id: int):
    return {"id": id, "activity": "Demo activity"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    if user.id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    await crud.delete_user(db, user_id)
    return None
