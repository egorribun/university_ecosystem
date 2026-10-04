"""Spotify linking requires the initiating account, session and one-time state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from httpx import Response

from app.api import spotify


def _request(session_id):
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "GET",
        }
    )
    request.state.active_session = SimpleNamespace(id=session_id)
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize("different", ["user", "session"])
async def test_oauth_state_cannot_transfer_between_accounts_or_sessions(different):
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    completing_user = SimpleNamespace(id=uuid4()) if different == "user" else user
    callback_request = _request(uuid4()) if different == "session" else request
    with patch.object(spotify._spotify_http_client, "post", AsyncMock()) as exchange:
        with pytest.raises(HTTPException) as error:
            await spotify.spotify_callback.__dishka_orig_func__(
                callback_request,
                AsyncMock(),
                code="code",
                state=state,
                user=completing_user,
            )
    assert error.value.status_code == 400
    exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_state_is_consumed_once_before_token_exchange():
    user = SimpleNamespace(id=uuid4(), spotify=SimpleNamespace(access_token="access"))
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    with (
        patch.object(
            spotify._spotify_http_client,
            "post",
            AsyncMock(return_value=Response(200, json={"access_token": "access"})),
        ) as exchange,
        patch.object(
            spotify._spotify_http_client, "get", AsyncMock(return_value=Response(503))
        ),
        patch.object(spotify, "_save_tokens", AsyncMock()),
    ):
        result = await spotify.spotify_callback.__dishka_orig_func__(
            request, AsyncMock(), code="code", state=state, user=user
        )
        assert result.status_code == 302
        with pytest.raises(HTTPException) as error:
            await spotify.spotify_callback.__dishka_orig_func__(
                request, AsyncMock(), code="second-code", state=state, user=user
            )
    assert error.value.status_code == 400
    exchange.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["issue", "consume"])
async def test_oauth_nonce_store_failure_fails_closed(operation):
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    with (
        patch.object(
            spotify,
            "get_revocation_redis_client",
            AsyncMock(side_effect=OSError("Redis unavailable")),
        ),
        patch.object(spotify._spotify_http_client, "post", AsyncMock()) as exchange,
        pytest.raises(HTTPException) as error,
    ):
        if operation == "issue":
            await spotify.spotify_auth_url(request=request, user=user)
        else:
            await spotify.spotify_callback.__dishka_orig_func__(
                request, AsyncMock(), code="code", state=state, user=user
            )
    assert error.value.status_code == 503
    exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_state_is_rejected_without_current_authenticated_session():
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    request.state.active_session = None
    with pytest.raises(HTTPException) as error:
        await spotify._consume_oauth_state(
            state, request=request, user=user, locale="en"
        )
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        await spotify.spotify_auth_url(request=request, user=user)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_oauth_replays_allow_only_one_code_exchange():
    import asyncio

    user = SimpleNamespace(id=uuid4(), spotify=SimpleNamespace(access_token="access"))
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    with (
        patch.object(
            spotify._spotify_http_client,
            "post",
            AsyncMock(return_value=Response(200, json={"access_token": "access"})),
        ) as exchange,
        patch.object(
            spotify._spotify_http_client, "get", AsyncMock(return_value=Response(503))
        ),
        patch.object(spotify, "_save_tokens", AsyncMock()),
    ):
        results = await asyncio.gather(
            *[
                spotify.spotify_callback.__dishka_orig_func__(
                    request, AsyncMock(), code=f"code-{index}", state=state, user=user
                )
                for index in range(2)
            ],
            return_exceptions=True,
        )
    assert sorted(result.status_code for result in results) == [302, 400]
    exchange.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_identity", [None, b"different:user", b"\xff"])
async def test_oauth_nonce_must_be_present_and_match_bound_identity(stored_identity):
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    client = SimpleNamespace(getdel=AsyncMock(return_value=stored_identity))
    with patch.object(
        spotify, "get_revocation_redis_client", AsyncMock(return_value=client)
    ):
        with pytest.raises(HTTPException) as error:
            await spotify._consume_oauth_state(
                state, request=request, user=user, locale="en"
            )
    assert error.value.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_spotify_callback_requires_app_authentication(async_client):
    with patch.object(spotify._spotify_http_client, "post", AsyncMock()) as exchange:
        response = await async_client.get(
            "/spotify/callback", params={"code": "code", "state": "state"}
        )
    assert response.status_code == 401
    exchange.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_nonce_collision_preserves_the_original_session_binding(
    mock_global_redis,
):
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    nonce = uuid4()
    with patch.object(spotify, "uuid4", return_value=nonce):
        original = await spotify.spotify_auth_url(request=request, user=user)
        with pytest.raises(HTTPException) as error:
            await spotify.spotify_auth_url(request=_request(uuid4()), user=user)

    assert error.value.status_code == 503
    assert "state" in parse_qs(urlsplit(original["url"]).query)
    assert await mock_global_redis.get(f"oauth:spotify:{nonce}") == (
        f"{user.id}:{request.state.active_session.id}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_claim", ["sub", "sid", "jti", "exp", "iat", "nbf"])
async def test_oauth_state_missing_required_claim_preserves_nonce(
    missing_claim, mock_global_redis
):
    user = SimpleNamespace(id=uuid4())
    request = _request(uuid4())
    state_url = await spotify.spotify_auth_url(request=request, user=user)
    original_state = parse_qs(urlsplit(state_url["url"]).query)["state"][0]
    payload = spotify.jwt.decode(
        original_state,
        spotify.settings.spotify_oauth_state_secret,
        algorithms=["HS256"],
    )
    nonce_key = f"oauth:spotify:{payload['jti']}"
    identity = f"{user.id}:{request.state.active_session.id}"
    del payload[missing_claim]
    incomplete_state = spotify.jwt.encode(
        payload, spotify.settings.spotify_oauth_state_secret, algorithm="HS256"
    )

    with pytest.raises(HTTPException) as error:
        await spotify._consume_oauth_state(
            incomplete_state, request=request, user=user, locale="en"
        )

    assert error.value.status_code == 400
    assert await mock_global_redis.get(nonce_key) == identity
    await spotify._consume_oauth_state(
        original_state, request=request, user=user, locale="en"
    )
    assert await mock_global_redis.get(nonce_key) is None
