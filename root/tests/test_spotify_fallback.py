from datetime import datetime, timedelta, timezone

import httpx
import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.api.spotify import _ensure_access_token, _fallback_now_playing, _save_tokens

_spotify_fallback_now_playing = _fallback_now_playing
from app.auth.security import get_password_hash
from app.models.models import User as ModelUser

pytestmark = pytest.mark.anyio("asyncio")


def _make_user(
    track_id: str | None = None,
    track_name: str | None = None,
    artists: str | None = None,
    album: str | None = None,
    album_image: str | None = None,
    track_url: str | None = None,
):
    user = ModelUser()
    user.spotify_last_track_id = track_id
    user.spotify_last_track_name = track_name
    user.spotify_last_artist_name = artists
    user.spotify_last_album_name = album
    user.spotify_last_album_image_url = album_image
    user.spotify_last_track_url = track_url
    return user


def test_fallback_now_playing_returns_last_track_details():
    user = _make_user(
        track_id="track-123",
        track_name="Test Song",
        artists="Artist One, Artist Two",
        album="Album",
        album_image="https://img",
        track_url="https://open.spotify.com/track/track-123",
    )

    out = _fallback_now_playing(user)

    assert out.is_playing is False
    assert out.track_id == "track-123"
    assert out.track_name == "Test Song"
    assert out.artists == ["Artist One", "Artist Two"]
    assert out.album_name == "Album"
    assert out.album_image_url == "https://img"
    assert out.track_url == "https://open.spotify.com/track/track-123"
    assert isinstance(out.fetched_at, datetime)
    assert out.fetched_at.tzinfo is not None
    assert out.fetched_at.tzinfo.utcoffset(out.fetched_at) == timezone.utc.utcoffset(
        None
    )


def test_fallback_now_playing_handles_missing_data():
    user = _make_user()

    out = _fallback_now_playing(user)

    assert out.is_playing is False
    assert out.track_id is None
    assert out.track_name is None
    assert out.artists == []


def test_legacy_fallback_matches_new_behavior():
    user = _make_user(
        track_id="track-42",
        track_name="Legacy Song",
        artists="Solo Artist",
        album="Legacy Album",
        album_image="https://legacy",
        track_url="https://open.spotify.com/track/track-42",
    )

    modern = _fallback_now_playing(user)
    legacy = _spotify_fallback_now_playing(user)

    assert legacy.track_id == modern.track_id
    assert legacy.track_name == modern.track_name
    assert legacy.artists == modern.artists
    assert legacy.album_name == modern.album_name
    assert legacy.album_image_url == modern.album_image_url
    assert legacy.track_url == modern.track_url


async def _login(
    async_client: AsyncClient, user: ModelUser, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_now_playing_returns_204_when_user_has_no_track(
    async_client: AsyncClient, user_factory
) -> None:
    password = "SpotifyP@ss1"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 204


async def test_now_playing_uses_last_known_track_from_fallback(
    async_client: AsyncClient, user_factory, db_session
) -> None:
    password = "SpotifyP@ss2"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify_last_track_id = "track-xyz"
    user.spotify_last_track_name = "Fallback Song"
    user.spotify_last_artist_name = "Fallback Artist"
    user.spotify_last_track_url = "https://open.spotify.com/track/track-xyz"
    await db_session.commit()
    await db_session.refresh(user)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["is_playing"] is False
    assert body["track_id"] == "track-xyz"
    assert body["track_name"] == "Fallback Song"
    assert body["artists"] == ["Fallback Artist"]


async def test_now_playing_returns_401_when_refresh_fails(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss3"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify_access_token = "expired"
    user.spotify_refresh_token = "refresh"
    user.spotify_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    user.spotify_is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class DummyResponse:
        status_code = 400
        headers: dict[str, str] = {}

        def json(self) -> dict[str, str]:
            return {}

    original_post = httpx.AsyncClient.post

    async def fake_post(self, url, *args, **kwargs):
        if str(url).endswith("/api/token"):
            return DummyResponse()
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Требуется переподключить Spotify"

    await db_session.refresh(user)
    assert user.spotify_is_connected is False
    assert user.spotify_access_token is None


async def test_now_playing_refreshes_when_access_token_missing(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss4"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify_access_token = None
    user.spotify_refresh_token = "refresh"
    user.spotify_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    user.spotify_is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class RefreshResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self) -> dict[str, str]:
            return {"access_token": "fresh", "expires_in": 120}

    class NowPlayingResponse:
        status_code = 204
        headers: dict[str, str] = {}

        def json(self) -> dict[str, str]:
            return {}

    refresh_called = False

    original_post = httpx.AsyncClient.post
    original_get = httpx.AsyncClient.get

    async def fake_post(self, url, *args, **kwargs):
        nonlocal refresh_called
        if str(url) == "https://accounts.spotify.com/api/token":
            refresh_called = True
            return RefreshResponse()
        return await original_post(self, url, *args, **kwargs)

    async def fake_get(self, url, *args, **kwargs):
        if str(url) == "https://api.spotify.com/v1/me/player/currently-playing":
            return NowPlayingResponse()
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 204
    assert refresh_called is True

    await db_session.refresh(user)
    assert user.spotify_access_token == "fresh"
    assert user.spotify_is_connected is True


async def test_now_playing_disconnects_on_unauthorized_response(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss5"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify_access_token = "valid"
    user.spotify_refresh_token = "refresh"
    user.spotify_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    user.spotify_is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class UnauthorizedResponse:
        status_code = 401
        headers: dict[str, str] = {}

        def json(self) -> dict[str, str]:
            return {"error": {"status": 401, "message": "The access token expired"}}

    original_get = httpx.AsyncClient.get

    async def fake_get(self, url, *args, **kwargs):
        if str(url) == "https://api.spotify.com/v1/me/player/currently-playing":
            return UnauthorizedResponse()
        return await original_get(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Требуется переподключить Spotify"

    await db_session.refresh(user)
    assert user.spotify_is_connected is False
    assert user.spotify_access_token is None
    assert user.spotify_refresh_token is None


async def test_spotify_tokens_are_encrypted_in_database(db_session, user_factory) -> None:
    user = await user_factory(is_active=True)

    await _save_tokens(
        db_session,
        user,
        access="access-token-value",
        refresh="refresh-token-value",
        scope="user-read-currently-playing",
        expires_in=3600,
    )

    row = await db_session.execute(
        sa.text(
            "SELECT spotify_access_token, spotify_refresh_token FROM users "
            "WHERE id = :user_id"
        ),
        {"user_id": user.id},
    )
    stored_access, stored_refresh = row.one()

    assert stored_access is not None
    assert stored_refresh is not None
    assert stored_access != "access-token-value"
    assert stored_refresh != "refresh-token-value"

    await db_session.refresh(user)
    assert user.spotify_access_token == "access-token-value"
    assert user.spotify_refresh_token == "refresh-token-value"


async def test_ensure_access_token_returns_plaintext(db_session, user_factory) -> None:
    user = await user_factory(is_active=True)

    await _save_tokens(
        db_session,
        user,
        access="plaintext-token",
        refresh="plaintext-refresh",
        scope="user-read-email",
        expires_in=7200,
    )

    token = await _ensure_access_token(db_session, user)

    assert token == "plaintext-token"

    raw = await db_session.execute(
        sa.text(
            "SELECT spotify_access_token FROM users WHERE id = :user_id"
        ),
        {"user_id": user.id},
    )
    stored_token = raw.scalar_one()
    assert stored_token != "plaintext-token"
