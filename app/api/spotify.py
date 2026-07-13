from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import get_current_user
from app.api.validation import (
    ensure_exists,
    raise_http_error,
    raise_unauthorized,
    raise_validation_error,
)
from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.models import SpotifyIntegration, User
from app.schemas.schemas import SpotifyAuthURL, SpotifyNowPlayingOut

logger = get_logger(__name__)

router = APIRouter(prefix="/spotify", tags=["spotify"])

# Circuit breaker for Spotify API with sensible defaults
_spotify_circuit_breaker = CircuitBreaker(
    "spotify_api",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout_seconds=30.0,
        success_threshold=2,
        excluded_exceptions=(HTTPException,),  # Don't count app-level errors
    ),
)

# PERF-002 (audit 2026-03-04): shared HTTP client across requests prevents
# per-request TCP handshake and TLS negotiation overhead.  HTTP/2 multiplexing
# allows multiple concurrent Spotify API calls over a single connection.
# PERF-W17-04 (Wave 17): Explicit pool limits prevent unbounded connections
# to Spotify API. httpx defaults to max_connections=100, which is excessive
# for a single third-party API and risks overwhelming Spotify's rate limits.
_spotify_http_client = httpx.AsyncClient(
    http2=True,
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30,
    ),
)


def _mint_state_token(subject: str, *, expires_minutes: int) -> str:
    """Mint a short-lived JWT state token for the Spotify OAuth round-trip.

    RZ-002 (audit 2026-03-04): uses a dedicated spotify_oauth_state_secret
    distinct from the main JWT signing key.  Prevents a confused-deputy attack
    where an externally-supplied state token (returned by Spotify callback) could
    be mistaken for or forged into a user access token.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": str(uuid4()),
    }
    # P2-W5-18: No fallback to spotify_token_secret — using the wrong key would
    # allow a confused-deputy attack.  The model_validator in integrations.py
    # already rejects empty SPOTIFY_OAUTH_STATE_SECRET in production; here we
    # guard the dev/test path with an explicit early failure.
    state_secret = settings.spotify_oauth_state_secret
    if not state_secret:
        raise ValueError(
            "SPOTIFY_OAUTH_STATE_SECRET must be set before Spotify OAuth flows can be used."
        )
    return jwt.encode(payload, state_secret, algorithm="HS256")


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _coerce_expires(value: int | str | None) -> int:
    try:
        seconds = int(value) if value is not None else 3600
    except TypeError, ValueError:
        seconds = 3600
    # Spotify may technically return small values during testing; make sure
    # we always refresh slightly before the real expiry to avoid rapid loops.
    return max(seconds, 30)


def _disconnect_user(
    user: User, *, clear_refresh: bool = False, clear_profile: bool = False
) -> None:
    if not user.spotify:
        return
    user.spotify.access_token = None
    if clear_refresh:
        user.spotify.refresh_token = None
        user.spotify.scope = None
    user.spotify.token_expires_at = None
    user.spotify.is_connected = False
    user.spotify.is_playing = False
    if clear_profile:
        user.spotify.display_name = None
        user.spotify.spotify_user_id = None


def _fallback_now_playing(user: User) -> SpotifyNowPlayingOut:
    if not user.spotify:
        return SpotifyNowPlayingOut(is_playing=False, fetched_at=_now_utc())

    artists: list[str] = []
    if user.spotify.last_artist_name:
        artists = [
            name.strip()
            for name in user.spotify.last_artist_name.split(",")
            if name.strip()
        ]

    has_payload = any(
        (
            user.spotify.last_track_id,
            user.spotify.last_track_name,
            artists,
        )
    )

    if not has_payload:
        return SpotifyNowPlayingOut(is_playing=False, fetched_at=_now_utc())

    return SpotifyNowPlayingOut(
        is_playing=False,
        progress_ms=None,
        duration_ms=None,
        track_id=user.spotify.last_track_id,
        track_name=user.spotify.last_track_name,
        artists=artists,
        album_name=user.spotify.last_album_name,
        album_image_url=user.spotify.last_album_image_url,
        track_url=user.spotify.last_track_url,
        preview_url=None,
        fetched_at=_now_utc(),
    )


async def _save_tokens(
    db: AsyncDatabaseSession,
    user: User,
    access: str,
    refresh: str | None,
    scope: str | None,
    expires_in: int | str | None,
) -> None:
    if not user.spotify:
        user.spotify = SpotifyIntegration(user_id=user.id)

    user.spotify.access_token = access or None
    if refresh is not None:
        user.spotify.refresh_token = refresh or None
    seconds = _coerce_expires(expires_in)
    # Refresh a little earlier to compensate for latency and clock skew.
    user.spotify.token_expires_at = _now_utc() + timedelta(seconds=seconds - 10)
    user.spotify.scope = scope or ""
    user.spotify.is_connected = True
    await db.commit()
    await db.refresh(user)


async def _ensure_access_token(
    db: AsyncDatabaseSession, user: User, *, locale: str | None = None
) -> str | None:
    """Return a usable Spotify access token, refreshing it when possible.

    Previously we returned ``None`` when ``spotify_access_token`` was empty,
    even if a refresh token was still stored. After the backend was restarted,
    some users ended up in that exact state and the frontend kept showing the
    stale fallback data until they manually reconnected the integration. To
    avoid forcing a re-link, we now treat a missing access token the same way
    as an expired one and trigger the refresh flow when a refresh token exists.
    """

    now = _now_utc()
    if not user.spotify:
        return None
    token = user.spotify.access_token or None
    exp = _ensure_utc(user.spotify.token_expires_at)
    if token and exp and exp > now:
        return str(token)
    refresh_token = user.spotify.refresh_token or None
    if not refresh_token:
        if not token and not user.spotify.is_connected:
            # The user never connected Spotify or already disconnected it;
            # returning ``None`` allows the caller to fall back gracefully.
            return None
        _disconnect_user(user, clear_refresh=True)
        await db.commit()
        raise_unauthorized(locale or "en", "errors.spotify.reconnect_required")
    try:
        async with _spotify_circuit_breaker:
            # TD-W16-07: Reuse module-level HTTP/2 client instead of per-request creation.
            r = await _spotify_http_client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Authorization": "Basic "
                    + _b64(
                        f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
                    )
                },
            )
    except CircuitBreakerOpenError as exc:
        logger.warning(
            "Spotify circuit breaker open, using fallback",
            extra={"remaining_seconds": exc.remaining_seconds},
        )
        return None
    if r.status_code != 200:
        _disconnect_user(user, clear_refresh=True)
        await db.commit()
        raise_unauthorized(locale or "en", "errors.spotify.reconnect_required")
    data = r.json()
    access_token = data.get("access_token")
    if not access_token:
        _disconnect_user(user, clear_refresh=True)
        await db.commit()
        raise_unauthorized(locale or "en", "errors.spotify.reconnect_required")

    # TD-W5-06: Detect scope downgrade — Spotify may return a reduced scope when
    # the user revoked individual permissions in their Spotify account settings.
    # If any previously-granted scope is missing, disconnect to force re-auth so
    # the user knows their integration lost capabilities (vs silent 403 on next call).
    new_scope_str: str = data.get("scope") or ""
    old_scope_str: str = user.spotify.scope or ""
    if old_scope_str:
        old_scope_set = set(old_scope_str.split())
        new_scope_set = set(new_scope_str.split())
        missing_scopes = old_scope_set - new_scope_set
        if missing_scopes:
            logger.warning(
                "Spotify token refresh returned downgraded scope — disconnecting integration",
                extra={
                    "user_id": str(user.id),
                    "missing_scopes": sorted(missing_scopes),
                    "old_scope": old_scope_str,
                    "new_scope": new_scope_str,
                },
            )
            _disconnect_user(user, clear_refresh=True)
            await db.commit()
            raise_unauthorized(locale or "en", "errors.spotify.scope_downgraded")

    await _save_tokens(
        db,
        user,
        access_token,
        data.get("refresh_token"),
        new_scope_str,
        data.get("expires_in"),
    )
    return str(user.spotify.access_token) if user.spotify.access_token else None


@router.get("/auth-url", response_model=SpotifyAuthURL)
async def spotify_auth_url(
    user: User = Depends(get_current_user),
) -> SpotifyAuthURL | dict[str, str]:
    state_token = _mint_state_token(str(user.id), expires_minutes=10)
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": settings.spotify_scopes,
        "state": state_token,
        "show_dialog": "false",
    }
    url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return {"url": url}


@router.get(
    "/callback",
    responses={
        503: {"description": "Service Unavailable"},
        400: {"description": "Bad Request"},
    },
)
async def spotify_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncDatabaseSession = Depends(get_db),
) -> RedirectResponse:
    locale = resolve_locale(request=request)
    # RZ-W19-07: decode state with the SAME key used to mint it
    state_secret = settings.spotify_oauth_state_secret
    if not state_secret:
        raise_http_error(503, "errors.spotify.misconfigured", locale)
    try:
        payload = jwt.decode(state, state_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        payload = {}
    if not payload.get("sub"):
        raise_validation_error("errors.spotify.invalid_state", locale)
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if not user:
        ensure_exists(user, "spotify.user_not_found", locale)
        raise ValueError("Unreachable")
    locale = resolve_locale(request=request, user=user)
    try:
        async with _spotify_circuit_breaker:
            # TD-W16-07: Reuse module-level HTTP/2 client.
            r = await _spotify_http_client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.spotify_redirect_uri,
                },
                headers={
                    "Authorization": "Basic "
                    + _b64(
                        f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
                    )
                },
            )
    except CircuitBreakerOpenError:
        raise_http_error(503, "errors.spotify.service_unavailable", locale)
    if r.status_code != 200:
        raise_validation_error("errors.spotify.token_exchange_failed", locale)
    data = r.json()
    await _save_tokens(
        db,
        user,
        data["access_token"],
        data.get("refresh_token"),
        data.get("scope"),
        int(data.get("expires_in", 3600)),
    )
    try:
        async with _spotify_circuit_breaker:
            # TD-W16-07: Reuse module-level HTTP/2 client.
            me = await _spotify_http_client.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {user.spotify.access_token}"},
            )
    except CircuitBreakerOpenError:
        me = None
    if me is not None and me.status_code == 200:
        info = me.json()
        user.spotify.spotify_user_id = info.get("id") or None
        user.spotify.display_name = info.get("display_name") or None
        await db.commit()
    # Redirect to the frontend, not the backend
    frontend_base = settings.frontend_origin.rstrip("/")
    target = f"{frontend_base}/profile?spotify=connected"
    return RedirectResponse(target, status_code=302)


@router.get("/now-playing", response_model=SpotifyNowPlayingOut)
async def now_playing(
    request: Request,
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SpotifyNowPlayingOut | Response:
    locale = resolve_locale(request=request, user=user)

    def _as_response(data: SpotifyNowPlayingOut) -> SpotifyNowPlayingOut | Response:
        if data.track_id or data.track_name or data.artists:
            return data
        return Response(status_code=204)

    async def _request(access_token: str) -> httpx.Response | None:
        try:
            async with _spotify_circuit_breaker:
                # TD-W16-07: Reuse module-level HTTP/2 client.
                return await _spotify_http_client.get(
                    "https://api.spotify.com/v1/me/player/currently-playing",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except CircuitBreakerOpenError:
            return None
        return None

    token = await _ensure_access_token(db, user, locale=locale)
    if not token:
        return _as_response(_fallback_now_playing(user))

    r = await _request(token)
    if r is None:
        # Circuit breaker is open, return fallback data
        return _as_response(_fallback_now_playing(user))
    if r.status_code == 401:
        # Access tokens occasionally expire slightly earlier than advertised or
        # get invalidated server-side. Instead of forcing the user to reconnect
        # immediately, attempt a single refresh and retry before giving up.
        user.spotify.access_token = None
        user.spotify.token_expires_at = _now_utc() - timedelta(seconds=30)
        try:
            refreshed = await _ensure_access_token(db, user, locale=locale)
        except HTTPException:
            # ``_ensure_access_token`` already disconnected the user and raised
            # an appropriate error; propagate it unchanged.
            raise
        if not refreshed:
            return _as_response(_fallback_now_playing(user))
        r = await _request(refreshed)
        if r is None:
            return _as_response(_fallback_now_playing(user))
        if r.status_code == 401:
            _disconnect_user(user, clear_refresh=True)
            await db.commit()
            raise_unauthorized(locale or "en", "errors.spotify.reconnect_required")
    if r.status_code == 204:
        user.spotify.is_playing = False
        user.spotify.last_checked_at = _now_utc()
        await db.commit()
        return Response(status_code=204)
    if r.status_code == 401:
        _disconnect_user(user, clear_refresh=True)
        await db.commit()
        raise_unauthorized(locale or "en", "errors.spotify.reconnect_required")
    if r.status_code == 429:
        retry_after_header = r.headers.get("Retry-After")
        try:
            retry_after = (
                max(1, int(float(retry_after_header))) if retry_after_header else 5
            )
        except TypeError, ValueError:
            retry_after = 5
        user.spotify.last_checked_at = _now_utc()
        await db.commit()
        raise HTTPException(
            status_code=429,
            detail=translate("errors.spotify.rate_limited", locale=locale),
            headers={"Retry-After": str(retry_after)},
        )
    if r.status_code != 200:
        return _as_response(_fallback_now_playing(user))
    j = r.json()
    item = j.get("item") or {}
    artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]
    album = item.get("album") or {}
    images = album.get("images") or []
    img = images[0]["url"] if images else None
    url = item.get("external_urls", {}).get("spotify")
    preview = item.get("preview_url")
    user.spotify.is_playing = bool(j.get("is_playing"))
    user.spotify.last_checked_at = _now_utc()
    user.spotify.last_track_id = item.get("id")
    user.spotify.last_track_name = item.get("name")
    user.spotify.last_artist_name = ", ".join(artists) if artists else None
    user.spotify.last_album_name = album.get("name")
    user.spotify.last_track_url = url
    user.spotify.last_album_image_url = img
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
        fetched_at=_now_utc(),
    )


@router.post("/disconnect")
async def disconnect(
    db: AsyncDatabaseSession = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, bool]:
    _disconnect_user(user, clear_refresh=True, clear_profile=True)
    await db.commit()
    return {"ok": True}


@router.get("/playlists")
async def list_playlists(
    request: Request,
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Any:
    locale = resolve_locale(request=request, user=user)
    token = await _ensure_access_token(db, user, locale=locale)
    if not token:
        raise_unauthorized(locale, "errors.spotify.reconnect_required")

    # TD-W16-07: Reuse module-level HTTP/2 client.
    r = await _spotify_http_client.get(
        "https://api.spotify.com/v1/me/playlists",
        headers={"Authorization": f"Bearer {token}"},
    )
    if r.status_code != 200:
        raise_http_error(r.status_code, "errors.spotify.api_error", locale)
    return r.json()


@router.post("/sync-playlists")
async def sync_playlists(
    request: Request,
    db: AsyncDatabaseSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Synchronize Spotify playlists metadata to the local database.
    """
    # Placeholder implementation
    return {"status": "success", "synced_count": 0}
