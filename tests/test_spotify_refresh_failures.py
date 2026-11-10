"""Preserve Spotify authorization on provider failures, revoke invalid grants."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

from app.api import spotify
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from app.models import SpotifyIntegration


@pytest.fixture
async def connected_spotify_user(db_session, user_factory):
    user = await user_factory()
    user.spotify.access_token = secrets.token_urlsafe(24)
    user.spotify.refresh_token = secrets.token_urlsafe(24)
    user.spotify.scope = "user-read-currently-playing"
    user.spotify.token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    user.spotify.is_connected = True
    user.spotify.is_playing = True
    user.spotify.spotify_user_id = f"synthetic-spotify-{user.id}"
    await db_session.commit()
    return user


@pytest.mark.parametrize(
    ("status", "body", "retry_after", "expected_status", "expected_retry"),
    [
        (429, '{"error":"invalid_grant"}', "10", 429, "10"),
        (429, "upstream busy", None, 429, "5"),
        (429, "upstream busy", "not-a-number", 429, "5"),
        (429, "upstream busy", "inf", 429, "5"),
        (429, "upstream busy", "-2", 429, "1"),
        (500, '{"error":"invalid_grant"}', None, 503, None),
        (502, "<html>Bad gateway</html>", None, 503, None),
        (503, '{"error":"temporarily_unavailable"}', None, 503, None),
        (504, "upstream timeout", None, 503, None),
        (400, '{"error":"invalid_client"}', None, 503, None),
        (401, '{"error":"invalid_client"}', None, 503, None),
        (400, "{}", None, 503, None),
        (400, "null", None, 503, None),
        (400, "[]", None, 503, None),
        (400, "not JSON", None, 503, None),
        (403, '{"error":"invalid_grant"}', None, 503, None),
    ],
)
async def test_refresh_failure_preserves_persisted_tokens_and_allows_recovery(
    db_session,
    connected_spotify_user,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: str,
    retry_after: str | None,
    expected_status: int,
    expected_retry: str | None,
) -> None:
    user = connected_spotify_user
    old_access = user.spotify.access_token
    old_refresh = user.spotify.refresh_token
    new_access = secrets.token_urlsafe(24)
    calls = 0

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.method == "POST"
        assert request.url == "https://accounts.spotify.com/api/token"
        calls += 1
        if calls == 1:
            headers = {"Retry-After": retry_after} if retry_after is not None else {}
            return httpx.Response(status, text=body, headers=headers)
        return httpx.Response(
            200,
            json={
                "access_token": new_access,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "user-read-currently-playing",
            },
        )

    monkeypatch.setattr(
        spotify,
        "_spotify_circuit_breaker",
        CircuitBreaker("synthetic-refresh", config=CircuitBreakerConfig()),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        monkeypatch.setattr(spotify, "_spotify_http_client", client)
        with pytest.raises(HTTPException) as caught:
            await spotify._ensure_access_token(db_session, user)
        assert caught.value.status_code == expected_status
        assert (caught.value.headers or {}).get("Retry-After") == expected_retry
        assert user.spotify.access_token == old_access
        assert user.spotify.refresh_token == old_refresh
        assert user.spotify.is_connected is True
        assert user.spotify.is_playing is True
        assert user.spotify.scope == "user-read-currently-playing"

        persisted = await db_session.get(
            SpotifyIntegration, user.id, populate_existing=True
        )
        assert persisted.access_token == old_access
        assert persisted.refresh_token == old_refresh
        assert persisted.is_connected is True

        assert await spotify._ensure_access_token(db_session, user) == new_access
        await db_session.refresh(persisted)
        assert persisted.access_token == new_access
        assert persisted.refresh_token == old_refresh
        assert persisted.is_connected is True
        assert calls == 2


@pytest.mark.parametrize("status", [400, 401])
async def test_invalid_grant_discards_persisted_tokens_and_requires_reauthorization(
    db_session,
    connected_spotify_user,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    user = connected_spotify_user

    def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "error": "invalid_grant",
                "error_description": "Refresh token expired",
            },
        )

    monkeypatch.setattr(
        spotify,
        "_spotify_circuit_breaker",
        CircuitBreaker("synthetic-invalid-grant", config=CircuitBreakerConfig()),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        monkeypatch.setattr(spotify, "_spotify_http_client", client)
        with pytest.raises(HTTPException) as caught:
            await spotify._ensure_access_token(db_session, user)
    assert caught.value.status_code == 401
    persisted = await db_session.get(
        SpotifyIntegration, user.id, populate_existing=True
    )
    assert persisted.access_token is None
    assert persisted.refresh_token is None
    assert persisted.scope is None
    assert persisted.token_expires_at is None
    assert persisted.is_connected is False
    assert persisted.is_playing is False
