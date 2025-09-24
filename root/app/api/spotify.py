from datetime import datetime, timedelta, timezone
from typing import Optional
import base64
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.auth.security import create_access_token, decode_token
from app.api.deps import get_current_user
from app.models.models import User
from app.schemas.schemas import SpotifyAuthURL, SpotifyNowPlayingOut

router = APIRouter(prefix="/spotify", tags=["spotify"])

def _now_naive() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)

def _as_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt

def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()

async def _save_tokens(db: AsyncSession, user: User, access: str, refresh: Optional[str], scope: Optional[str], expires_in: int):
    user.spotify_access_token = access
    if refresh:
        user.spotify_refresh_token = refresh
    user.spotify_token_expires_at = _now_naive() + timedelta(seconds=expires_in - 10)
    user.spotify_scope = scope or ""
    user.spotify_is_connected = True
    await db.commit()
    await db.refresh(user)

async def _ensure_access_token(db: AsyncSession, user: User) -> Optional[str]:
    if not user.spotify_access_token or not user.spotify_refresh_token:
        return None
    exp = _as_naive_utc(user.spotify_token_expires_at)
    if exp and exp > _now_naive():
        return user.spotify_access_token
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "refresh_token", "refresh_token": user.spotify_refresh_token},
            headers={"Authorization": "Basic " + _b64(f"{settings.spotify_client_id}:{settings.spotify_client_secret}")},
        )
    if r.status_code != 200:
        return None
    data = r.json()
    await _save_tokens(db, user, data["access_token"], data.get("refresh_token"), data.get("scope"), int(data.get("expires_in", 3600)))
    return user.spotify_access_token

@router.get("/auth-url", response_model=SpotifyAuthURL)
async def spotify_auth_url(user: User = Depends(get_current_user)):
    state = create_access_token(str(user.id), expires_delta=10)
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": settings.spotify_scopes,
        "state": state,
        "show_dialog": "false",
    }
    url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return {"url": url}

@router.get("/callback")
async def spotify_callback(code: str = Query(...), state: str = Query(...), db: AsyncSession = Depends(get_db)):
    payload = decode_token(state) or {}
    if not payload.get("sub"):
        raise HTTPException(status_code=400, detail="invalid state")
    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=400, detail="user not found")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.spotify_redirect_uri},
            headers={"Authorization": "Basic " + _b64(f"{settings.spotify_client_id}:{settings.spotify_client_secret}")},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="token exchange failed")
    data = r.json()
    await _save_tokens(db, user, data["access_token"], data.get("refresh_token"), data.get("scope"), int(data.get("expires_in", 3600)))
    async with httpx.AsyncClient(timeout=15) as client:
        me = await client.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {user.spotify_access_token}"})
    if me.status_code == 200:
        info = me.json()
        user.spotify_user_id = info.get("id") or None
        user.spotify_display_name = info.get("display_name") or None
        await db.commit()
    target = settings.app_base_url_clean + "/profile?spotify=connected"
    return RedirectResponse(target, status_code=302)

@router.get("/now-playing", response_model=SpotifyNowPlayingOut)
async def now_playing(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    token = await _ensure_access_token(db, user)
    if not token:
        return SpotifyNowPlayingOut(is_playing=False, fetched_at=_now_naive())
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.spotify.com/v1/me/player/currently-playing", headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 204:
        user.spotify_is_playing = False
        user.spotify_last_checked_at = _now_naive()
        await db.commit()
        return SpotifyNowPlayingOut(is_playing=False, fetched_at=_now_naive())
    if r.status_code != 200:
        return SpotifyNowPlayingOut(is_playing=False, fetched_at=_now_naive())
    j = r.json()
    item = j.get("item") or {}
    artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]
    album = item.get("album") or {}
    images = album.get("images") or []
    img = images[0]["url"] if images else None
    url = item.get("external_urls", {}).get("spotify")
    preview = item.get("preview_url")
    user.spotify_is_playing = bool(j.get("is_playing"))
    user.spotify_last_checked_at = _now_naive()
    user.spotify_last_track_id = item.get("id")
    user.spotify_last_track_name = item.get("name")
    user.spotify_last_artist_name = ", ".join(artists) if artists else None
    user.spotify_last_album_name = album.get("name")
    user.spotify_last_track_url = url
    user.spotify_last_album_image_url = img
    await db.commit()
    return SpotifyNowPlayingOut(
        is_playing=bool(j.get("is_playing")),
        progress_ms=j.get("progress_ms"),
        duration_ms=(item.get("duration_ms") if item else None),
        track_id=item.get("id"),
        track_name=item.get("name"),
        artists=artists,
        album_name=album.get("name"),
        album_image_url=img,
        track_url=url,
        preview_url=preview,
        fetched_at=_now_naive(),
    )

@router.post("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    user.spotify_access_token = None
    user.spotify_refresh_token = None
    user.spotify_token_expires_at = None
    user.spotify_scope = None
    user.spotify_display_name = None
    user.spotify_user_id = None
    user.spotify_is_connected = False
    user.spotify_is_playing = False
    await db.commit()
    return {"ok": True}
