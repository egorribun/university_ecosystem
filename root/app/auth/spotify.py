import base64
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from app.api.deps import get_current_user
from app.auth.security import create_access_token, decode_token
from app.core.config import settings
from app.core.database import get_db
from app.models.models import User
from app.schemas import schemas
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

REFRESH_EARLY_S = 30  # обновляем токен заранее на небольшой буфер


def _basic_headers() -> dict:
    token = base64.b64encode(
        f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _normalize_scope(scope_val) -> str:
    # settings.spotify_scopes может быть строкой или списком
    if isinstance(scope_val, (list, tuple, set)):
        return " ".join(scope_val)
    return str(scope_val or "").strip()


@router.get("/spotify/auth-url", response_model=schemas.SpotifyAuthURL)
async def spotify_auth_url(user: User = Depends(get_current_user)):
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise HTTPException(status_code=500, detail="Spotify не сконфигурирован")
    if not settings.spotify_redirect_uri:
        raise HTTPException(status_code=500, detail="REDIRECT URI не задан")

    # state: короткоживущий JWT
    # ВАЖНО: если у вас create_access_token ждёт timedelta — передаём timedelta.
    state = create_access_token(str(user.id), expires_delta=timedelta(minutes=10))

    scope = _normalize_scope(settings.spotify_scopes)
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": scope,
        "state": state,
    }
    # code flow: желательно кодировать пробелы в scope как %20
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        params, quote_via=quote
    )
    return {"url": url}


async def _refresh_if_needed(db: AsyncSession, user: User) -> bool:
    now = datetime.now(timezone.utc)
    if (
        user.spotify_access_token
        and user.spotify_expires_at
        and user.spotify_expires_at > now + timedelta(seconds=REFRESH_EARLY_S)
    ):
        return True

    if not user.spotify_refresh_token:
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": user.spotify_refresh_token,
                },
                headers=_basic_headers(),
            )
    except httpx.HTTPError:
        return False

    if r.status_code != 200:
        return False

    data = r.json()
    user.spotify_access_token = data.get("access_token") or user.spotify_access_token
    exp = int(data.get("expires_in", 3600))
    user.spotify_expires_at = datetime.now(timezone.utc) + timedelta(seconds=exp)
    await db.commit()
    return True


@router.get("/auth/spotify/callback")
async def spotify_callback(
    code: str = Query(""), state: str = Query(""), db: AsyncSession = Depends(get_db)
):
    base = settings.app_base_url_clean or ""
    fail = RedirectResponse(f"{base}/profile?spotify=error", status_code=303)

    if not code or not state:
        return fail

    user_id: int | None = None
    try:
        payload = decode_token(state) or {}
        sub = payload.get("sub")
        user_id = int(sub) if sub is not None else None
    except Exception:
        return fail

    if not user_id:
        return fail

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.spotify_redirect_uri,
                },
                headers=_basic_headers(),
            )
            if r.status_code != 200:
                return fail

            tok = r.json()
            access = tok.get("access_token")
            refresh = tok.get("refresh_token")
            exp = int(tok.get("expires_in", 3600))

            # опционально подтянем профиль — полезно сохранить spotify_user_id
            me = await client.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {access}"},
            )
            me_data = me.json() if me.status_code == 200 else {}
    except httpx.HTTPError:
        return fail

    user = await db.get(User, user_id)
    if not user:
        return fail

    now = datetime.now(timezone.utc)
    user.spotify_access_token = access
    if refresh:
        user.spotify_refresh_token = refresh
    user.spotify_expires_at = now + timedelta(seconds=exp)
    user.spotify_is_connected = True
    if me_data.get("id"):
        user.spotify_user_id = me_data["id"]
    await db.commit()

    return RedirectResponse(f"{base}/profile?spotify=connected", status_code=303)


@router.get("/spotify/now-playing", response_model=schemas.SpotifyNowPlayingOut)
async def spotify_now_playing(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)

    if not getattr(user, "spotify_is_connected", False):
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=now)

    ok = await _refresh_if_needed(db, user)
    if not ok:
        # токен протух/нет refresh — отключаем интеграцию
        user.spotify_is_connected = False
        await db.commit()
        raise HTTPException(status_code=401, detail="Требуется переподключить Spotify")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.spotify.com/v1/me/player/currently-playing",
                headers={"Authorization": f"Bearer {user.spotify_access_token}"},
            )
    except httpx.HTTPError:
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=now)

    user.spotify_last_checked_at = now

    # 429 — ограничение по rate limit, передаём сигнал фронту подождать
    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", "1"))
        await db.commit()
        raise HTTPException(
            status_code=429, detail=f"Rate limited, retry after {retry_after}s"
        )

    # 204 — ничего не играет
    if r.status_code == 204:
        user.spotify_is_playing = False
        await db.commit()
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=now)

    # 401 — токен недействителен/отозван
    if r.status_code == 401:
        user.spotify_is_connected = False
        await db.commit()
        raise HTTPException(status_code=401, detail="Требуется переподключить Spotify")

    if r.status_code != 200:
        await db.commit()
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=now)

    data = r.json() or {}
    item = data.get("item") or {}
    album = item.get("album") or {}
    artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]

    # первая доступная картинка альбома
    album_images = album.get("images") or []
    img = next((im.get("url") for im in album_images if im.get("url")), None)

    user.spotify_is_playing = bool(data.get("is_playing"))
    user.spotify_last_track_id = item.get("id") or None
    user.spotify_last_track_name = item.get("name") or None
    user.spotify_last_artist_name = ", ".join(artists) if artists else None
    user.spotify_last_album_name = album.get("name") or None
    user.spotify_last_track_url = (item.get("external_urls") or {}).get("spotify")
    user.spotify_last_album_image_url = img
    await db.commit()

    return schemas.SpotifyNowPlayingOut(
        is_playing=bool(data.get("is_playing")),
        progress_ms=data.get("progress_ms"),
        duration_ms=(item.get("duration_ms") if item else None),
        track_id=item.get("id"),
        track_name=item.get("name"),
        artists=artists,
        album_name=album.get("name"),
        album_image_url=img,
        track_url=(item.get("external_urls") or {}).get("spotify"),
        preview_url=item.get("preview_url"),
        fetched_at=now,
    )
