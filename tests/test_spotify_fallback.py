import typing
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.api.spotify import _ensure_access_token, _fallback_now_playing, _save_tokens
from app.auth.security import get_password_hash
from app.models import SpotifyIntegration
from app.models import User as ModelUser

_spotify_fallback_now_playing = _fallback_now_playing


def _make_user(
    track_id: str | None = None,
    track_name: str | None = None,
    artists: str | None = None,
    album: str | None = None,
    album_image: str | None = None,
    track_url: str | None = None,
):
    user = ModelUser()
    # Create SpotifyIntegration relationship
    user.spotify = SpotifyIntegration(
        last_track_id=track_id,
        last_track_name=track_name,
        last_artist_name=artists,
        last_album_name=album,
        last_album_image_url=album_image,
        last_track_url=track_url,
    )
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
    assert out.fetched_at.tzinfo.utcoffset(out.fetched_at) == UTC.utcoffset(None)


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
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_returns_204_when_user_has_no_track(
    async_client: AsyncClient, user_factory
) -> None:
    password = "SpotifyP@ss1"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 204


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_uses_last_known_track_from_fallback(
    async_client: AsyncClient, user_factory, db_session
) -> None:
    password = "SpotifyP@ss2"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify.last_track_id = "track-xyz"
    user.spotify.last_track_name = "Fallback Song"
    user.spotify.last_artist_name = "Fallback Artist"
    user.spotify.last_track_url = "https://open.spotify.com/track/track-xyz"
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


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_returns_401_when_refresh_fails(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss3"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify.access_token = "expired"
    user.spotify.refresh_token = "refresh"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=5)
    user.spotify.is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class DummyResponse:
        status_code = 400
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
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
    assert user.spotify.is_connected is False
    assert user.spotify.access_token is None


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_refreshes_when_access_token_missing(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss4"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify.access_token = None
    user.spotify.refresh_token = "refresh"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    user.spotify.is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class RefreshResponse:
        status_code = 200
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {"access_token": "fresh", "expires_in": 120}

    class NowPlayingResponse:
        status_code = 204
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
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
    headers.update(
        {
            "Accept-Language": "ru",
            # PostgreSQL's RLS transaction context plus the token-refresh and
            # now-playing persistence commits are eight statements in this
            # intentionally stateful path. Keep the query trip-wire enabled
            # with an explicit, scenario-specific ceiling instead of disabling it.
            "X-Query-Budget": "8",
        }
    )

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 204
    assert refresh_called is True

    await db_session.refresh(user)
    assert user.spotify.access_token == "fresh"
    assert user.spotify.is_connected is True


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_retries_after_unauthorized_response(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss4b"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify.access_token = "valid"
    user.spotify.refresh_token = "refresh"
    user.spotify.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
    user.spotify.is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class UnauthorizedResponse:
        status_code = 401
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {"error": {"status": 401, "message": "The access token expired"}}

    class EmptyResponse:
        status_code = 204
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {}

    class RefreshResponse:
        status_code = 200
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "access_token": "fresh",
                "refresh_token": "refresh-new",
                "expires_in": 1800,
            }

    refresh_called = False
    get_calls = 0

    original_get = httpx.AsyncClient.get
    original_post = httpx.AsyncClient.post

    async def fake_get(self, url, *args, **kwargs):
        nonlocal get_calls
        if str(url) == "https://api.spotify.com/v1/me/player/currently-playing":
            get_calls += 1
            if get_calls == 1:
                return UnauthorizedResponse()
            return EmptyResponse()
        return await original_get(self, url, *args, **kwargs)

    async def fake_post(self, url, *args, **kwargs):
        nonlocal refresh_called
        if str(url) == "https://accounts.spotify.com/api/token":
            refresh_called = True
            return RefreshResponse()
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 204
    assert refresh_called is True
    assert get_calls == 2

    await db_session.refresh(user)
    assert user.spotify.access_token == "fresh"
    assert user.spotify.refresh_token == "refresh-new"
    assert user.spotify.is_connected is True


@pytest.mark.asyncio(loop_scope="session")
async def test_now_playing_disconnects_on_unauthorized_response(
    async_client: AsyncClient, user_factory, db_session, monkeypatch
) -> None:
    password = "SpotifyP@ss5"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    user.spotify.access_token = "valid"
    user.spotify.refresh_token = "refresh"
    user.spotify.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
    user.spotify.is_connected = True
    await db_session.commit()
    await db_session.refresh(user)

    class UnauthorizedResponse:
        status_code = 401
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {"error": {"status": 401, "message": "The access token expired"}}

    class RefreshResponse:
        status_code = 200
        headers: typing.ClassVar[dict[str, typing.Any]] = {}

        def json(self) -> dict[str, Any]:
            return {
                "access_token": "another-token",
                "refresh_token": "another-refresh",
                "expires_in": 1200,
            }

    original_get = httpx.AsyncClient.get
    original_post = httpx.AsyncClient.post

    get_calls = 0
    refresh_called = False

    async def fake_get(self, url, *args, **kwargs):
        nonlocal get_calls
        if str(url) == "https://api.spotify.com/v1/me/player/currently-playing":
            get_calls += 1
            return UnauthorizedResponse()
        return await original_get(self, url, *args, **kwargs)

    async def fake_post(self, url, *args, **kwargs):
        nonlocal refresh_called
        if str(url) == "https://accounts.spotify.com/api/token":
            refresh_called = True
            return RefreshResponse()
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    headers = await _login(async_client, user, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Требуется переподключить Spotify"
    assert get_calls == 2
    assert refresh_called is True

    await db_session.refresh(user)
    assert user.spotify.is_connected is False
    assert user.spotify.access_token is None
    assert user.spotify.refresh_token is None


@pytest.mark.asyncio(loop_scope="session")
async def test_spotify_tokens_are_encrypted_in_database(
    db_session, user_factory
) -> None:
    user = await user_factory(is_active=True)

    await _save_tokens(
        db_session,
        user,
        access="access-token-value",
        refresh="refresh-token-value",
        scope="user-read-currently-playing",
        expires_in=3600,
    )

    from app.models import SpotifyIntegration

    # Query raw columns while using ORM for filtering to ensure UUID compatibility.
    stmt = (
        sa.select(sa.text("access_token"), sa.text("refresh_token"))
        .select_from(SpotifyIntegration)
        .where(SpotifyIntegration.user_id == user.id)
    )
    result = await db_session.execute(stmt)
    stored_access, stored_refresh = result.one()

    assert stored_access is not None
    assert stored_refresh is not None
    assert stored_access != "access-token-value"
    assert stored_refresh != "refresh-token-value"

    await db_session.refresh(user)
    assert user.spotify.access_token == "access-token-value"
    assert user.spotify.refresh_token == "refresh-token-value"


@pytest.mark.asyncio(loop_scope="session")
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

    from app.models import SpotifyIntegration

    stmt = (
        sa.select(sa.text("access_token"))
        .select_from(SpotifyIntegration)
        .where(SpotifyIntegration.user_id == user.id)
    )
    result = await db_session.execute(stmt)
    stored_token = result.scalar_one()
    assert stored_token != "plaintext-token"
