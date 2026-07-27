"""Behavioral coverage closure for Spotify OAuth and playback endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import Response


def _user(*, spotify: bool = True):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.spotify = MagicMock() if spotify else None
    if spotify:
        user.spotify.access_token = "old-token"
        user.spotify.refresh_token = "refresh-token"
        user.spotify.token_expires_at = None
        user.spotify.is_connected = True
        user.spotify.scope = ""
        user.spotify.last_artist_name = None
        user.spotify.last_track_id = None
        user.spotify.last_track_name = None
        user.spotify.last_album_name = None
        user.spotify.last_album_image_url = None
        user.spotify.last_track_url = None
    return user


def _request() -> MagicMock:
    request = MagicMock()
    request.headers.get.return_value = "en"
    return request


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "spotify_oauth_state_secret": "state-secret",
        "spotify_client_id": "client-id",
        "spotify_client_secret": "client-secret",
        "spotify_redirect_uri": "http://localhost/callback",
        "spotify_scopes": "user-read-playback-state",
        "frontend_origin": "http://frontend/",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _breaker(*enter_values):
    breaker = MagicMock()
    breaker.__aenter__ = AsyncMock(side_effect=list(enter_values) or [None])
    breaker.__aexit__ = AsyncMock(return_value=None)
    return breaker


def test_spotify_token_helpers_cover_success_and_utc_normalization() -> None:
    from app.api import spotify

    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "encode", return_value="state-token") as encode,
    ):
        assert spotify._mint_state_token("user", expires_minutes=10) == "state-token"
    encode.assert_called_once()

    with patch.object(spotify, "settings", _settings(spotify_oauth_state_secret="")):
        with pytest.raises(ValueError, match="must be set"):
            spotify._mint_state_token("user", expires_minutes=10)

    naive = datetime(2025, 1, 1, 12, 0)
    aware = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
    assert spotify._ensure_utc(None) is None
    assert spotify._ensure_utc(naive).tzinfo is UTC
    assert spotify._ensure_utc(aware) is aware


def test_spotify_disconnect_and_fallback_payload_edges() -> None:
    from app.api import spotify

    no_spotify = _user(spotify=False)
    spotify._disconnect_user(no_spotify)
    assert spotify._fallback_now_playing(no_spotify).is_playing is False
    empty = _user()
    result = spotify._fallback_now_playing(empty)
    assert result.is_playing is False

    empty.spotify.last_artist_name = " , "
    assert spotify._fallback_now_playing(empty).is_playing is False
    empty.spotify.last_artist_name = " Artist One, , Artist Two "
    empty.spotify.last_track_id = "track"
    result = spotify._fallback_now_playing(empty)
    assert result.artists == ["Artist One", "Artist Two"]

    spotify._disconnect_user(empty, clear_refresh=False, clear_profile=False)
    assert empty.spotify.access_token is None


@pytest.mark.asyncio
async def test_save_tokens_creates_integration_and_preserves_refresh_when_omitted() -> (
    None
):
    from app.api import spotify

    user = _user(spotify=False)
    db = AsyncMock()
    with patch.object(spotify, "_now_utc", return_value=datetime.now(UTC)):
        await spotify._save_tokens(db, user, "access", None, None, "not-an-int")
    assert user.spotify.access_token == "access"
    assert user.spotify.refresh_token is None
    assert user.spotify.scope == ""
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_access_token_no_spotify_and_valid_unexpired_token() -> None:
    from app.api import spotify

    db = AsyncMock()
    assert await spotify._ensure_access_token(db, _user(spotify=False)) is None
    user = _user()
    user.spotify.token_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    assert await spotify._ensure_access_token(db, user) == "old-token"


@pytest.mark.asyncio
async def test_ensure_access_token_no_refresh_returns_none_or_unauthorized() -> None:
    from app.api import spotify

    db = AsyncMock()
    never_connected = _user()
    never_connected.spotify.access_token = None
    never_connected.spotify.refresh_token = None
    never_connected.spotify.is_connected = False
    assert await spotify._ensure_access_token(db, never_connected) is None

    connected = _user()
    connected.spotify.access_token = "old-token"
    connected.spotify.refresh_token = None
    with pytest.raises(HTTPException) as exc:
        await spotify._ensure_access_token(db, connected, locale="ru")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_ensure_access_token_refresh_success_and_circuit_open() -> None:
    from app.api import spotify
    from app.core.circuit_breaker import CircuitBreakerOpenError

    db = AsyncMock()
    user = _user()
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "access_token": "new-token",
        "scope": "user-read-playback-state",
        "expires_in": "120",
    }
    user.spotify.scope = "user-read-playback-state"
    with (
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(post=AsyncMock(return_value=response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
        patch.object(spotify, "_save_tokens", new=AsyncMock()) as save_tokens,
    ):
        assert await spotify._ensure_access_token(db, user) == "old-token"
    save_tokens.assert_awaited_once()

    open_user = _user()
    breaker = _breaker(
        CircuitBreakerOpenError("spotify", remaining_seconds=10, failure_count=3)
    )
    with patch.object(spotify, "_spotify_circuit_breaker", breaker):
        assert await spotify._ensure_access_token(db, open_user) is None

    empty_scope_user = _user()
    empty_scope_response = MagicMock(status_code=200)
    empty_scope_response.json.return_value = {
        "access_token": "new-token",
        "scope": "",
        "expires_in": 120,
    }
    with (
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(post=AsyncMock(return_value=empty_scope_response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
        patch.object(spotify, "_save_tokens", new=AsyncMock()),
    ):
        assert await spotify._ensure_access_token(db, empty_scope_user) == "old-token"


@pytest.mark.asyncio
async def test_ensure_access_token_rejects_missing_token_and_scope_downgrade() -> None:
    from app.api import spotify

    db = AsyncMock()
    missing_token_response = MagicMock(status_code=200)
    missing_token_response.json.return_value = {"expires_in": 120}
    missing_token_user = _user()
    with (
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(post=AsyncMock(return_value=missing_token_response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify._ensure_access_token(db, missing_token_user, locale="ru")
    assert exc.value.status_code == 401
    assert missing_token_user.spotify.access_token is None
    assert missing_token_user.spotify.refresh_token is None
    db.commit.assert_awaited_once()

    db.reset_mock()
    downgraded_response = MagicMock(status_code=200)
    downgraded_response.json.return_value = {
        "access_token": "new-token",
        "scope": "user-read-playback-state",
        "expires_in": 120,
    }
    downgraded_user = _user()
    downgraded_user.spotify.scope = "user-read-playback-state user-read-email"
    with (
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(post=AsyncMock(return_value=downgraded_response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
        patch.object(spotify, "_save_tokens", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify._ensure_access_token(db, downgraded_user, locale="ru")
    assert exc.value.status_code == 401
    assert downgraded_user.spotify.access_token is None
    assert downgraded_user.spotify.refresh_token is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_spotify_callback_rejects_missing_secret_invalid_state_and_missing_user() -> (
    None
):
    from app.api import spotify

    request = _request()
    db = AsyncMock()
    with patch.object(spotify, "settings", _settings(spotify_oauth_state_secret="")):
        with pytest.raises(HTTPException) as exc:
            await spotify.spotify_callback(request, code="code", state="state", db=db)
        assert exc.value.status_code == 503

    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", side_effect=spotify.jwt.PyJWTError("bad")),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.spotify_callback(request, code="code", state="bad", db=db)
        assert exc.value.status_code == 400

    db.get.return_value = None
    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", return_value={"sub": str(uuid.uuid4())}),
        patch.object(spotify, "ensure_exists"),
    ):
        with pytest.raises(ValueError, match="Unreachable") as exc:
            await spotify.spotify_callback(request, code="code", state="state", db=db)


@pytest.mark.asyncio
async def test_spotify_callback_handles_exchange_and_profile_circuit_branches() -> None:
    from app.api import spotify
    from app.core.circuit_breaker import CircuitBreakerOpenError

    user = _user()
    db = AsyncMock()
    db.get.return_value = user
    request = _request()
    state = str(user.id)
    response = MagicMock(status_code=400)
    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", return_value={"sub": state}),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(post=AsyncMock(return_value=response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.spotify_callback(request, code="code", state="state", db=db)
        assert exc.value.status_code == 400

    open_error = CircuitBreakerOpenError(
        "spotify", remaining_seconds=5, failure_count=3
    )
    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", return_value={"sub": state}),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker(open_error)),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.spotify_callback(request, code="code", state="state", db=db)
        assert exc.value.status_code == 503

    post = MagicMock(status_code=200)
    me = MagicMock(status_code=500)
    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", return_value={"sub": state}),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(
                post=AsyncMock(return_value=post), get=AsyncMock(return_value=me)
            ),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker(None, None)),
        patch.object(
            post,
            "json",
            return_value={"access_token": "access", "expires_in": 60},
        ),
        patch.object(spotify, "_save_tokens", new=AsyncMock()),
    ):
        response = await spotify.spotify_callback(
            request, code="code", state="state", db=db
        )
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_spotify_callback_profile_circuit_open_redirects_anyway() -> None:
    from app.api import spotify
    from app.core.circuit_breaker import CircuitBreakerOpenError

    user = _user()
    db = AsyncMock()
    db.get.return_value = user
    request = _request()
    state = str(user.id)
    post = MagicMock(status_code=200)
    breaker = _breaker(
        None,
        CircuitBreakerOpenError("spotify", remaining_seconds=5, failure_count=3),
    )
    client = SimpleNamespace(post=AsyncMock(return_value=post), get=AsyncMock())
    with (
        patch.object(spotify, "settings", _settings()),
        patch.object(spotify.jwt, "decode", return_value={"sub": state}),
        patch.object(spotify, "_spotify_http_client", client),
        patch.object(spotify, "_spotify_circuit_breaker", breaker),
        patch.object(
            post,
            "json",
            return_value={"access_token": "access", "expires_in": 60},
        ),
        patch.object(spotify, "_save_tokens", new=AsyncMock()),
    ):
        response = await spotify.spotify_callback(
            request, code="code", state="state", db=db
        )
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_now_playing_fallback_and_circuit_open_response_shapes() -> None:
    from app.api import spotify

    db = AsyncMock()
    request = _request()
    empty_user = _user()
    empty_user.spotify.access_token = None
    empty_user.spotify.refresh_token = None
    empty_user.spotify.is_connected = False
    with patch.object(
        spotify, "_ensure_access_token", new=AsyncMock(return_value=None)
    ):
        response = await spotify.now_playing(request, db=db, user=empty_user)
    assert response.status_code == 204

    track_user = _user()
    track_user.spotify.access_token = None
    track_user.spotify.refresh_token = None
    track_user.spotify.last_track_id = "cached-track"
    with patch.object(
        spotify, "_ensure_access_token", new=AsyncMock(return_value=None)
    ):
        result = await spotify.now_playing(request, db=db, user=track_user)
    assert result.track_id == "cached-track"

    circuit_user = _user()
    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_circuit_breaker",
            _breaker(
                spotify.CircuitBreakerOpenError(
                    "spotify", remaining_seconds=3, failure_count=3
                )
            ),
        ),
    ):
        response = await spotify.now_playing(request, db=db, user=circuit_user)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_now_playing_retries_after_unauthorized_and_succeeds() -> None:
    from app.api import spotify

    user = _user()
    db = AsyncMock()
    request = _request()
    first = Response(401)
    second = Response(
        200,
        json={
            "is_playing": True,
            "progress_ms": 10,
            "item": {
                "id": "id",
                "name": "name",
                "artists": [{"name": "artist"}],
                "album": {"name": "album", "images": []},
                "external_urls": {},
            },
        },
    )
    with (
        patch.object(
            spotify,
            "_ensure_access_token",
            new=AsyncMock(side_effect=["token", "refreshed"]),
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(side_effect=[first, second])),
        ),
    ):
        result = await spotify.now_playing(request, db=db, user=user)
    assert result.track_id == "id"
    assert result.artists == ["artist"]


@pytest.mark.asyncio
async def test_now_playing_retry_error_fallback_and_circuit_paths() -> None:
    from app.api import spotify
    from app.core.circuit_breaker import CircuitBreakerOpenError

    db = AsyncMock()
    user = _user()
    with (
        patch.object(
            spotify,
            "_ensure_access_token",
            new=AsyncMock(
                side_effect=["token", HTTPException(status_code=401, detail="retry")]
            ),
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(401))),
        ),
    ):
        with pytest.raises(HTTPException, match="retry"):
            await spotify.now_playing(_request(), db=db, user=user)

    fallback_user = _user()
    with (
        patch.object(
            spotify,
            "_ensure_access_token",
            new=AsyncMock(side_effect=["token", None]),
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(401))),
        ),
    ):
        response = await spotify.now_playing(_request(), db=db, user=fallback_user)
    assert response.status_code == 204

    circuit_user = _user()
    breaker = _breaker(
        None,
        CircuitBreakerOpenError("spotify", remaining_seconds=3, failure_count=3),
    )
    with (
        patch.object(
            spotify,
            "_ensure_access_token",
            new=AsyncMock(side_effect=["token", "refreshed"]),
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(401))),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", breaker),
    ):
        response = await spotify.now_playing(_request(), db=db, user=circuit_user)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_now_playing_second_unauthorized_disconnects() -> None:
    from app.api import spotify

    user = _user()
    db = AsyncMock()
    with (
        patch.object(
            spotify,
            "_ensure_access_token",
            new=AsyncMock(side_effect=["token", "refreshed"]),
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(side_effect=[Response(401), Response(401)])),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.now_playing(_request(), db=db, user=user)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_now_playing_late_unauthorized_branch_after_status_rechecks() -> None:
    from app.api import spotify

    class StatefulStatus:
        def __init__(self):
            self._results = iter([False, False, True])

        def __eq__(self, other):
            return next(self._results)

    user = _user()
    response = MagicMock(status_code=StatefulStatus())
    db = AsyncMock()
    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=response)),
        ),
        patch.object(spotify, "_spotify_circuit_breaker", _breaker()),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.now_playing(_request(), db=db, user=user)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_now_playing_204_invalid_rate_header_and_non_200() -> None:
    from app.api import spotify

    db = AsyncMock()
    user = _user()
    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(204))),
        ),
    ):
        response = await spotify.now_playing(_request(), db=db, user=user)
    assert response.status_code == 204

    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(
                get=AsyncMock(
                    return_value=Response(429, headers={"Retry-After": "bad"})
                )
            ),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.now_playing(_request(), db=db, user=user)
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "5"

    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(500))),
        ),
    ):
        response = await spotify.now_playing(_request(), db=db, user=user)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_list_playlists_reauth_and_api_error_paths() -> None:
    from app.api import spotify

    user = _user()
    db = AsyncMock()
    request = _request()
    with patch.object(
        spotify, "_ensure_access_token", new=AsyncMock(return_value=None)
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.list_playlists(request, db=db, user=user)
    assert exc.value.status_code == 401

    with (
        patch.object(
            spotify, "_ensure_access_token", new=AsyncMock(return_value="token")
        ),
        patch.object(
            spotify,
            "_spotify_http_client",
            SimpleNamespace(get=AsyncMock(return_value=Response(500))),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await spotify.list_playlists(request, db=db, user=user)
    assert exc.value.status_code == 500
