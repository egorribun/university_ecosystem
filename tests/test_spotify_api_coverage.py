import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import Response

from app.api.spotify import (
    _ensure_access_token,
    _save_tokens,
    disconnect,
    now_playing,
    spotify_auth_url,
    spotify_callback,
)
from app.models.models import SpotifyIntegration, User


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.spotify = MagicMock(spec=SpotifyIntegration)
    user.spotify.access_token = "old_token"
    user.spotify.refresh_token = "refresh_token"
    user.spotify.token_expires_at = None
    user.spotify.is_connected = True
    return user


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.state.user = None
    req.headers.get.return_value = None
    return req


@pytest.mark.asyncio
async def test_auth_url(mock_user):
    with patch(
        "app.api.spotify.create_access_token", new_callable=AsyncMock
    ) as mock_create_token:
        mock_create_token.return_value = "state_token"
        response = await spotify_auth_url(user=mock_user)
        assert "url" in response
        assert "state=state_token" in response["url"]


@pytest.mark.asyncio
async def test_spotify_callback_success(mock_db, mock_request, mock_user):
    with (
        patch("app.api.spotify.decode_token") as mock_decode,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        fixed_uuid = str(uuid.uuid4())
        mock_decode.return_value = {"sub": fixed_uuid}
        mock_db.get.return_value = mock_user

        # Token response
        mock_post.return_value = Response(
            200,
            json={
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
                "scope": "read",
            },
        )

        # Me response
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
async def test_spotify_callback_invalid_state(mock_request, mock_db):
    with patch("app.api.spotify.decode_token") as mock_decode:
        mock_decode.return_value = {}  # No sub
        with pytest.raises(HTTPException):
            await spotify_callback(mock_request, code="c", state="s", db=mock_db)


@pytest.mark.asyncio
async def test_now_playing_fallback(mock_db, mock_request, mock_user):
    # Case where access token retrieval fails -> fallback
    with patch(
        "app.api.spotify._ensure_access_token", new_callable=AsyncMock
    ) as mock_ensure:
        mock_ensure.return_value = None
        mock_user.spotify = None  # trigger fallback

        response = await now_playing(mock_request, db=mock_db, user=mock_user)
        # Should be 204 because fallback is empty
        assert response.status_code == 204


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
async def test_disconnect(mock_db, mock_user):
    result = await disconnect(db=mock_db, user=mock_user)
    assert result == {"ok": True}
    assert mock_user.spotify.access_token is None
    assert mock_user.spotify.is_connected is False


@pytest.mark.asyncio
async def test_save_tokens_create_integration(mock_db):
    user = MagicMock(spec=User)
    user.id = 1
    user.spotify = None  # No integration yet

    await _save_tokens(mock_db, user, "acc", "ref", "scope", 3600)

    assert user.spotify is not None
    assert user.spotify.user_id == 1
    assert user.spotify.access_token == "acc"


@pytest.mark.asyncio
async def test_ensure_access_token_refresh(mock_db, mock_user):
    from datetime import UTC, datetime, timedelta

    # Expires in past
    mock_user.spotify.token_expires_at = datetime.now(UTC) - timedelta(hours=1)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(
            200, json={"access_token": "refreshed_token", "expires_in": 3600}
        )

        token = await _ensure_access_token(mock_db, mock_user)

        assert token == "refreshed_token"
        assert mock_user.spotify.access_token == "refreshed_token"
