from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks, Request, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
import uuid
import secrets
import mimetypes
import hashlib
import base64
from starlette.responses import RedirectResponse
from urllib.parse import urlencode
import httpx
from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas import schemas
from app.models import models
from app import crud
from app.core.config import settings
from app.auth.security import decode_token
from app.utils.email import send_reset_email

router = APIRouter()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def save_upload(file: UploadFile, subdir: str, prefix: str) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="unsupported media type")
    data = await file.read(MAX_IMAGE_SIZE + 1)
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="file too large")
    ext = mimetypes.guess_extension(file.content_type) or f".{file.filename.split('.')[-1].lower()}"
    name = f"{prefix}_{secrets.token_hex(8)}{ext}"
    base_dir = settings.static_dir_path
    folder = base_dir / subdir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return f"/static/{subdir}/{name}"

@router.post("/password/forgot")
async def forgot_password(payload: schemas.ForgotPasswordIn, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == payload.email))
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(minutes=45)
        db.add(models.PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires, used=False))
        await db.commit()
        base = settings.app_base_url_clean
        reset_link = f"{base}/reset-password?token={token}"
        bg.add_task(send_reset_email, user.email, reset_link, user.full_name or "")
    return {"ok": True}

@router.post("/password/reset")
async def reset_password(payload: schemas.ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    result = await db.execute(select(models.PasswordResetToken).where(models.PasswordResetToken.token_hash == token_hash, models.PasswordResetToken.used == False))
    rec = result.scalar_one_or_none()
    if not rec or rec.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительная или просроченная ссылка")
    user = await db.get(models.User, rec.user_id)
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недействительная ссылка")
    from app.auth.security import get_password_hash
    user.hashed_password = get_password_hash(payload.password)
    rec.used = True
    await db.execute(update(models.PasswordResetToken).where(models.PasswordResetToken.user_id == rec.user_id, models.PasswordResetToken.used == False).values(used=True))
    await db.commit()
    return {"ok": True}

@router.get("/users/me", response_model=schemas.UserOut)
async def me(user: models.User = Depends(get_current_user)):
    return user

@router.put("/users/me", response_model=schemas.UserOut)
async def update_me(data: schemas.UserProfileUpdate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    db_user = await db.get(models.User, user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(db_user, field, value)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.post("/users/me/avatar", response_model=schemas.UserOut)
async def upload_avatar(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    url = await save_upload(file, "avatars", f"user_{user.id}_avatar")
    db_user = await db.get(models.User, user.id)
    db_user.avatar_url = url
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.post("/users/me/cover", response_model=schemas.UserOut)
async def upload_cover(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    url = await save_upload(file, "covers", f"user_{user.id}_cover")
    db_user = await db.get(models.User, user.id)
    db_user.cover_url = url
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.post("/users", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    code_obj = None
    if data.role in ["teacher", "admin"]:
        if not data.invite_code:
            raise HTTPException(status_code=400, detail="Необходим уникальный код для регистрации преподавателя/админа")
        q = select(models.InviteCode).where(
            models.InviteCode.code == data.invite_code,
            models.InviteCode.role == data.role,
            models.InviteCode.is_active == True,
        )
        code_obj = (await db.execute(q)).scalar_one_or_none()
        if not code_obj:
            raise HTTPException(status_code=400, detail="Неверный или неактивный код")
    user = await crud.create_user(db, data)
    return user

@router.get("/users", response_model=List[schemas.UserOut])
async def get_users(db: AsyncSession = Depends(get_db), full_name: Optional[str] = Query(None), group_id: Optional[int] = Query(None), role: Optional[str] = Query(None), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.get_users(db, full_name=full_name, group_id=group_id, role=role)

@router.patch("/users/{user_id}", response_model=schemas.UserOut)
async def update_user_admin(user_id: int, data: schemas.UserAdminUpdate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.admin_update_user(db, user_id, data)

@router.delete("/users/me/avatar", response_model=schemas.UserOut)
async def delete_avatar(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
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
async def create_group(data: schemas.GroupCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_group(db, data)

@router.get("/groups", response_model=List[schemas.GroupOut])
async def get_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Group))
    return result.scalars().all()

@router.post("/schedule", response_model=schemas.ScheduleOut)
async def add_schedule(data: schemas.ScheduleCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_schedule(db, data)

@router.get("/schedule/{group_id}", response_model=List[schemas.ScheduleOut])
async def get_schedule(group_id: int, db: AsyncSession = Depends(get_db)):
    return await crud.get_schedule_by_group(db, group_id)

@router.patch("/schedule/{schedule_id}", response_model=schemas.ScheduleOut)
async def update_schedule(schedule_id: int, data: schemas.ScheduleUpdate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(sched, field, value)
    await db.commit()
    await db.refresh(sched)
    return sched

@router.delete("/schedule/{schedule_id}", response_model=dict)
async def delete_schedule(schedule_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    sched = await db.get(models.Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(sched)
    await db.commit()
    return {"ok": True}

def _spotify_auth_header() -> str:
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()

async def _spotify_refresh_if_needed(db: AsyncSession, user: models.User) -> None:
    if not getattr(user, "spotify_access_token", None) or not getattr(user, "spotify_refresh_token", None):
        raise HTTPException(status_code=400, detail="Spotify не подключён")
    now = datetime.now(timezone.utc)
    if getattr(user, "spotify_token_expires_at", None) and user.spotify_token_expires_at > now + timedelta(seconds=30):
        return
    async with httpx.AsyncClient(timeout=10) as client:
        data = {"grant_type": "refresh_token", "refresh_token": user.spotify_refresh_token}
        headers = {"Authorization": _spotify_auth_header(), "Content-Type": "application/x-www-form-urlencoded"}
        r = await client.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="Не удалось обновить токен Spotify")
        j = r.json()
        user.spotify_access_token = j.get("access_token") or user.spotify_access_token
        expires_in = j.get("expires_in") or 3600
        user.spotify_token_expires_at = now + timedelta(seconds=int(expires_in))
        await db.commit()
        await db.refresh(user)

@router.get("/spotify/auth-url", response_model=schemas.SpotifyAuthURL)
async def spotify_auth_url(req: Request, user: models.User = Depends(get_current_user)):
    if not settings.spotify_client_id or not settings.spotify_redirect_uri:
        raise HTTPException(status_code=500, detail="Spotify не сконфигурирован")
    state = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
    scope = settings.spotify_scopes or "user-read-currently-playing user-read-playback-state"
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": scope,
        "state": state or secrets.token_urlsafe(16),
        "show_dialog": "false",
    }
    return {"url": "https://accounts.spotify.com/authorize?" + urlencode(params)}

@router.get("/spotify/callback")
async def spotify_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    if error or not code:
        url = settings.app_base_url_clean + "/profile?spotify=error"
        return RedirectResponse(url)
    uid = None
    if state:
        try:
            payload = decode_token(state)
            uid = int(payload.get("sub")) if payload and payload.get("sub") else None
        except Exception:
            uid = None
    if not uid:
        url = settings.app_base_url_clean + "/profile?spotify=error"
        return RedirectResponse(url)
    user = await db.get(models.User, uid)
    if not user or not user.is_active:
        url = settings.app_base_url_clean + "/profile?spotify=error"
        return RedirectResponse(url)
    async with httpx.AsyncClient(timeout=10) as client:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.spotify_redirect_uri,
        }
        headers = {"Authorization": _spotify_auth_header(), "Content-Type": "application/x-www-form-urlencoded"}
        r = await client.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
    if r.status_code != 200:
        url = settings.app_base_url_clean + "/profile?spotify=error"
        return RedirectResponse(url)
    j = r.json()
    now = datetime.now(timezone.utc)
    user.spotify_access_token = j.get("access_token")
    user.spotify_refresh_token = j.get("refresh_token") or user.spotify_refresh_token
    user.spotify_token_expires_at = now + timedelta(seconds=int(j.get("expires_in") or 3600))
    user.spotify_scope = j.get("scope") or settings.spotify_scopes
    if hasattr(user, "spotify_connected"):
        setattr(user, "spotify_connected", True)
    if hasattr(user, "spotify_is_connected"):
        setattr(user, "spotify_is_connected", True)
    await db.commit()
    url = settings.app_base_url_clean + "/profile?spotify=connected"
    return RedirectResponse(url)

@router.get("/spotify/now-playing", response_model=schemas.SpotifyNowPlayingOut)
async def spotify_now_playing(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    await _spotify_refresh_if_needed(db, user)
    token = user.spotify_access_token
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://api.spotify.com/v1/me/player/currently-playing", headers={"Authorization": f"Bearer {token}"})
    now = datetime.now(timezone.utc)
    if r.status_code == 204:
        if hasattr(user, "spotify_is_playing"):
            user.spotify_is_playing = False
            user.spotify_last_checked_at = now
            await db.commit()
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=now)
    if r.status_code == 200:
        data = r.json() or {}
        item = data.get("item") or {}
        artists = [a.get("name") for a in (item.get("artists") or []) if a.get("name")]
        album = item.get("album") or {}
        images = album.get("images") or []
        album_img = images[0]["url"] if images else None
        out = schemas.SpotifyNowPlayingOut(
            is_playing=bool(data.get("is_playing")),
            progress_ms=data.get("progress_ms"),
            duration_ms=item.get("duration_ms"),
            track_id=item.get("id"),
            track_name=item.get("name"),
            artists=artists,
            album_name=album.get("name"),
            album_image_url=album_img,
            track_url=(item.get("external_urls") or {}).get("spotify"),
            preview_url=item.get("preview_url"),
            fetched_at=now,
        )
        try:
            if hasattr(user, "spotify_is_playing"):
                user.spotify_is_playing = out.is_playing
                user.spotify_last_checked_at = now
                user.spotify_last_track_id = out.track_id
                user.spotify_last_track_name = out.track_name
                user.spotify_last_artist_name = ", ".join(out.artists)
                user.spotify_last_album_name = out.album_name
                user.spotify_last_track_url = out.track_url
                user.spotify_last_album_image_url = out.album_image_url
                await db.commit()
        except Exception:
            pass
        return out
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Требуется переподключить Spotify")
    raise HTTPException(status_code=400, detail="Не удалось получить трек")

@router.post("/events", response_model=schemas.EventOut)
async def create_event(data: schemas.EventCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_event(db, data, user_id=user.id)

@router.get("/events", response_model=List[schemas.EventOut])
async def all_events(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user), search: str = Query("", alias="search"), type: str = Query("", alias="type"), location: str = Query("", alias="location"), is_active: bool = Query(True, alias="is_active")):
    return await crud.get_all_events(db, user_id=user.id, search=search, type=type, location=location, is_active=is_active)

@router.post("/events/attendance", response_model=schemas.EventAttendanceOut)
async def attend(data: schemas.EventAttendanceCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="Регистрация на мероприятия недоступна для вашей роли")
    return await crud.register_attendance(db, data, user_id=user.id)

@router.delete("/events/attendance", response_model=dict)
async def unregister_event(data: schemas.EventAttendanceCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    return await crud.unregister_attendance(db, data, user_id=user.id)

@router.get("/events/my", response_model=List[schemas.EventOut])
async def my_events(db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    return await crud.get_my_events(db, user_id=user.id)

@router.post("/events/{id}/upload_file", response_model=schemas.EventFileOut)
async def upload_event_file(id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
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
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")
    file_path.write_bytes(data)
    ef = models.EventFile(event_id=id, file_url=f"/static/event_files/{filename}")
    db.add(ef)
    await db.commit()
    await db.refresh(ef)
    return ef

@router.get("/events/{id}/files", response_model=List[schemas.EventFileOut])
async def get_event_files(id: int, db: AsyncSession = Depends(get_db)):
    files = (await db.execute(select(models.EventFile).where(models.EventFile.event_id == id))).scalars().all()
    return files

@router.post("/events/upload_image")
async def upload_event_image(file: UploadFile = File(...), user: models.User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_upload(file, "event_images", "event")
    return {"url": url}

@router.patch("/events/{event_id}", response_model=schemas.EventOut)
async def update_event(event_id: int, data: schemas.EventUpdate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(q, field, value)
    await db.commit()
    await db.refresh(q)
    files = (await db.execute(select(models.EventFile).where(models.EventFile.event_id == q.id))).scalars().all()
    participant_count = (await db.execute(select(func.count()).select_from(models.EventAttendance).where(models.EventAttendance.event_id == q.id))).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    return out

@router.delete("/events/{event_id}", response_model=dict)
async def delete_event(event_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.get(models.Event, event_id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    if user.role not in ("admin", "teacher") and q.created_by != user.id:
        raise HTTPException(status_code=403, detail="forbidden")
    await db.delete(q)
    await db.commit()
    return {"ok": True}

@router.get("/events/{id}", response_model=schemas.EventOut)
async def get_event(id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    q = await db.get(models.Event, id)
    if not q:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    files = (await db.execute(select(models.EventFile).where(models.EventFile.event_id == q.id))).scalars().all()
    participant_count = (await db.execute(select(func.count()).select_from(models.EventAttendance).where(models.EventAttendance.event_id == q.id))).scalar()
    out = schemas.EventOut.from_orm(q)
    out.files = [schemas.EventFileOut.from_orm(f) for f in files]
    out.participant_count = participant_count
    return out

@router.delete("/events/file/{file_id}", response_model=dict)
async def delete_event_file(file_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
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
async def create_news(data: schemas.NewsCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return await crud.create_news(db, data)

@router.get("/news", response_model=List[schemas.NewsOut])
async def news_list(db: AsyncSession = Depends(get_db)):
    return await crud.get_news_list(db)

@router.get("/news/{id}", response_model=schemas.NewsOut)
async def get_news(id: int, db: AsyncSession = Depends(get_db)):
    q = await db.get(models.News, id)
    if not q:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    return q

@router.patch("/news/{id}", response_model=schemas.NewsOut)
async def update_news(id: int, data: schemas.NewsCreate, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(news, field, value)
    await db.commit()
    await db.refresh(news)
    return news

@router.delete("/news/{id}", response_model=dict)
async def delete_news(id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    news = await db.get(models.News, id)
    if not news:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    await db.delete(news)
    await db.commit()
    return {"ok": True}

@router.post("/news/upload_image")
async def upload_news_image(file: UploadFile = File(...), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    url = await save_upload(file, "news_images", "news")
    return {"url": url}

@router.get("/activity/{id}")
async def get_activity(id: int):
    return {"id": id, "activity": "Demo activity"}

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db), user: models.User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    if user.id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    await crud.delete_user(db, user_id)
    return None
