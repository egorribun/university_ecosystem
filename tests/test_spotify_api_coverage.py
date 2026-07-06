import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import Response

from app.api.spotify import (
    _disconnect_user,
    _ensure_access_token,
    disconnect,
    list_playlists,
    now_playing,
    spotify_auth_url,
    spotify_callback,
    sync_playlists,
)
from app.models import SpotifyIntegration, User


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Mock commit and other sync-like async methods if needed
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.spotify = MagicMock(spec=SpotifyIntegration)
    user.spotify.access_token = "old_token"
    user.spotify.refresh_token = "refresh_token"
    user.spotify.token_expires_at = None
    user.spotify.is_connected = True
    user.spotify.last_artist_name = "Artist1, Artist2"
    user.spotify.last_track_id = "t1"
    return user


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.state.user = None
    req.headers.get.return_value = "ru"
    return req


@pytest.mark.asyncio
async def test_auth_url(mock_user):
    with patch("app.api.spotify._mint_state_token") as mock_create_token:
        mock_create_token.return_value = "state_token"
        response = await spotify_auth_url(user=mock_user)
        assert "url" in response
        assert "state=state_token" in response["url"]


@pytest.mark.asyncio
async def test_spotify_callback_success(mock_db, mock_request, mock_user, monkeypatch):
    """Test Spotify OAuth callback flow with mocked settings.

    Pydantic v2 BaseSettings singleton resists attribute mutation, so we
    replace the entire `settings` reference in the spotify module.
    """

    from app.core.config import settings

    # Build a proxy that delegates everything to the real settings but
    # overrides the four Spotify fields.
    overrides = {
        "spotify_oauth_state_secret": "test-state-secret",  # pragma: allowlist secret
        "spotify_client_id": "test-client-id",
        "spotify_client_secret": "test-client-secret",  # pragma: allowlist secret
        "spotify_redirect_uri": "http://localhost:8000/spotify/callback",
    }

    class _SettingsProxy:
        def __getattr__(self, name):
            if name in overrides:
                return overrides[name]
            return getattr(settings, name)

    monkeypatch.setattr("app.api.spotify.settings", _SettingsProxy())
    return await _run_spotify_callback_success(mock_db, mock_request, mock_user)


async def _run_spotify_callback_success(mock_db, mock_request, mock_user):
    with (
        patch("app.api.spotify.jwt.decode") as mock_decode,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        fixed_uuid = str(uuid.uuid4())
        mock_decode.return_value = {"sub": fixed_uuid}
        mock_db.get.return_value = mock_user

        mock_post.return_value = Response(
            200,
            json={
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
                "scope": "read",
            },
        )

        mock_get.return_value = Response(
            200, json={"id": "spotify_user", "display_name": "Spotify User"}
        )

        response = await spotify_callback(
            mock_request, code="code", state="state", db=mock_db
        )

        assert response.status_code == 302
        assert "spotify=connected" in response.headers["location"]
        assert mock_user.spotify.spotify_user_id == "spotify_user"


@pytest.mark.asyncio
async def test_now_playing_success(mock_db, mock_request, mock_user):
    with (
        patch(
            "app.api.spotify._ensure_access_token", new_callable=AsyncMock
        ) as mock_ensure,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_ensure.return_value = "valid_token"

        mock_get.return_value = Response(
            200,
            json={
                "is_playing": True,
                "item": {
                    "id": "track_id",
                    "name": "Track Name",
                    "artists": [{"name": "Artist"}],
                    "album": {"name": "Album", "images": [{"url": "img.jpg"}]},
                    "external_urls": {"spotify": "url"},
                    "preview_url": "preview",
                },
                "progress_ms": 1000,
            },
        )

        result = await now_playing(mock_request, db=mock_db, user=mock_user)

        assert result.is_playing is True
        assert result.track_name == "Track Name"


@pytest.mark.asyncio
async def test_list_playlists(mock_db, mock_request, mock_user):
    with (
        patch(
            "app.api.spotify._ensure_access_token", new_callable=AsyncMock
        ) as mock_ensure,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_ensure.return_value = "valid_token"
        mock_get.return_value = Response(200, json={"items": []})

        result = await list_playlists(mock_request, db=mock_db, user=mock_user)
        assert result == {"items": []}


@pytest.mark.asyncio
async def test_sync_playlists(mock_db, mock_request, mock_user):
    result = await sync_playlists(mock_request, db=mock_db, user=mock_user)
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_ensure_access_token_expired_refresh_fail(mock_db, mock_user):
    from datetime import UTC, datetime, timedelta

    mock_user.spotify.token_expires_at = datetime.now(UTC) - timedelta(hours=1)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(401, json={"error": "invalid_grant"})

        with pytest.raises(HTTPException) as exc:
            await _ensure_access_token(mock_db, mock_user)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_now_playing_rate_limited(mock_db, mock_request, mock_user):
    with (
        patch(
            "app.api.spotify._ensure_access_token", new_callable=AsyncMock
        ) as mock_ensure,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_ensure.return_value = "token"
        mock_get.return_value = Response(429, headers={"Retry-After": "10"})

        with pytest.raises(HTTPException) as exc:
            await now_playing(mock_request, db=mock_db, user=mock_user)
        assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_disconnect_full(mock_db, mock_user):
    result = await disconnect(mock_db, mock_user)
    assert result == {"ok": True}
    assert mock_user.spotify.is_connected is False
    assert mock_user.spotify.access_token is None


def test_disconnect_user_helper():
    user = MagicMock()
    user.spotify = MagicMock()
    _disconnect_user(user, clear_refresh=True, clear_profile=True)
    assert user.spotify.access_token is None
    assert user.spotify.refresh_token is None
    assert user.spotify.display_name is None


def test_legacy_spotify_auth_import_compat():
    """Ensure the compatibility shim app.auth.spotify can be imported and re-exports symbols."""
    import app.auth.spotify as legacy_spotify

    assert legacy_spotify.disconnect is disconnect
    assert legacy_spotify.now_playing is now_playing
    assert legacy_spotify.list_playlists is list_playlists
    assert legacy_spotify.sync_playlists is sync_playlists
    assert legacy_spotify.spotify_auth_url is spotify_auth_url
    assert legacy_spotify.spotify_callback is spotify_callback
