from datetime import datetime, timezone

from app.api.spotify import _fallback_now_playing
from app.api.routes import _spotify_fallback_now_playing
from app.models.models import User


def _make_user(
    track_id: str | None = None,
    track_name: str | None = None,
    artists: str | None = None,
    album: str | None = None,
    album_image: str | None = None,
    track_url: str | None = None,
):
    user = User()
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
    assert out.fetched_at.tzinfo.utcoffset(out.fetched_at) == timezone.utc.utcoffset(None)


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
