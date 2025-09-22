from datetime import datetime, timedelta
import base64, urllib.parse
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.api.deps import get_current_user
from app.auth.security import create_access_token, decode_token
from app.models.models import User
from app.schemas import schemas

router = APIRouter()

def _basic_headers():
    token = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/x-www-form-urlencoded"}

@router.get("/spotify/auth-url")
async def spotify_auth_url(user: User = Depends(get_current_user)):
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise HTTPException(status_code=500, detail="Spotify не сконфигурирован")
    state = create_access_token(str(user.id), expires_delta=10)
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": settings.spotify_scopes,
        "state": state,
    }
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    return {"url": url}

async def _refresh_if_needed(db: AsyncSession, user: User) -> bool:
    now = datetime.utcnow()
    if user.spotify_access_token and user.spotify_expires_at and user.spotify_expires_at > now:
        return True
    if not user.spotify_refresh_token:
        return False
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "refresh_token", "refresh_token": user.spotify_refresh_token},
            headers=_basic_headers(),
        )
    if r.status_code != 200:
        return False
    data = r.json()
    user.spotify_access_token = data.get("access_token") or user.spotify_access_token
    exp = int(data.get("expires_in", 3600))
    user.spotify_expires_at = datetime.utcnow() + timedelta(seconds=exp)
    await db.commit()
    return True

@router.get("/auth/spotify/callback")
async def spotify_callback(code: str = Query(""), state: str = Query(""), db: AsyncSession = Depends(get_db)):
    if not code or not state:
        return RedirectResponse(f"{settings.app_base_url}/profile?spotify=error")
    payload = decode_token(state)
    sub = payload.get("sub") if payload else None
    try:
        user_id = int(sub)
    except:
        return RedirectResponse(f"{settings.app_base_url}/profile?spotify=error")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.spotify_redirect_uri},
            headers=_basic_headers(),
        )
        if r.status_code != 200:
            return RedirectResponse(f"{settings.app_base_url}/profile?spotify=error")
        tok = r.json()
        access = tok.get("access_token")
        refresh = tok.get("refresh_token")
        exp = int(tok.get("expires_in", 3600))
        me = await client.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access}"})
        me_data = me.json() if me.status_code == 200 else {}
    user = await db.get(User, user_id)
    if not user:
        return RedirectResponse(f"{settings.app_base_url}/profile?spotify=error")
    user.spotify_access_token = access
    if refresh:
        user.spotify_refresh_token = refresh
    user.spotify_expires_at = datetime.utcnow() + timedelta(seconds=exp)
    user.spotify_is_connected = True
    if me_data.get("id"):
        user.spotify_user_id = me_data["id"]
    await db.commit()
    return RedirectResponse(f"{settings.app_base_url}/profile?spotify=connected")

@router.get("/spotify/now-playing", response_model=schemas.SpotifyNowPlayingOut)
async def spotify_now_playing(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if not user.spotify_is_connected:
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=datetime.utcnow())
    ok = await _refresh_if_needed(db, user)
    if not ok:
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=datetime.utcnow())
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.spotify.com/v1/me/player/currently-playing",
            headers={"Authorization": f"Bearer {user.spotify_access_token}"},
        )
    user.spotify_last_checked_at = datetime.utcnow()
    if r.status_code == 204:
        user.spotify_is_playing = False
        await db.commit()
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=datetime.utcnow())
    if r.status_code != 200:
        await db.commit()
        return schemas.SpotifyNowPlayingOut(is_playing=False, fetched_at=datetime.utcnow())
    data = r.json()
    item = data.get("item") or {}
    album = item.get("album") or {}
    artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]
    img = None
    for im in album.get("images", []):
        if im.get("url"):
            img = im["url"]
            break
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
        fetched_at=datetime.utcnow(),
    )