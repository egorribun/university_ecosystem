from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.api.routes import _spotify_fallback_now_playing
from app.api.spotify import _fallback_now_playing
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


async def _login(async_client: AsyncClient, user: ModelUser, password: str) -> dict[str, str]:
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

    response = await async_client.get("/spotify/now-playing", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["is_playing"] is False
    assert body["track_id"] == "track-xyz"
    assert body["track_name"] == "Fallback Song"
    assert body["artists"] == ["Fallback Artist"]
