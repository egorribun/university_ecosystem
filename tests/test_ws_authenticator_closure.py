"""Closure tests for WebSocket origin and credential fallbacks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws.authenticator import WsAuthenticator, _get_allowed_ws_origins


def _websocket(
    *, origin: str | None = None, ticket: str | None = None, cookie: str | None = None
):
    websocket = MagicMock()
    websocket.headers = {"origin": origin} if origin is not None else {}
    websocket.query_params = {"ticket": ticket} if ticket is not None else {}
    websocket.cookies = {"access_token_v2": cookie} if cookie is not None else {}
    websocket.close = AsyncMock()
    return websocket


def test_allowed_origins_normalize_trailing_slash_and_empty_setting():
    with patch(
        "app.core.config.settings",
        SimpleNamespace(frontend_origins_list=["https://ui.example/"]),
    ):
        assert _get_allowed_ws_origins() == frozenset({"https://ui.example"})
    with patch("app.core.config.settings", SimpleNamespace(frontend_origins_list=[])):
        assert _get_allowed_ws_origins() == frozenset()


@pytest.mark.asyncio
async def test_rejects_invalid_origin_before_authentication():
    websocket = _websocket(origin="https://attacker.example", ticket="ticket")

    with (
        patch(
            "app.api.ws.authenticator._ALLOWED_WS_ORIGINS",
            frozenset({"https://ui.example"}),
        ),
        patch(
            "app.api.ws.authenticator.get_user_from_ticket", new=AsyncMock()
        ) as get_ticket,
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (None, None, None)
    websocket.close.assert_awaited_once_with(code=1008)
    get_ticket.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_ticket_without_cookie_returns_anonymous():
    websocket = _websocket(ticket="ticket")

    with (
        patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
        patch(
            "app.api.ws.authenticator.get_user_from_ticket",
            new=AsyncMock(return_value=(None, None)),
        ) as get_ticket,
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (None, None, None)
    get_ticket.assert_awaited_once_with("ticket")


@pytest.mark.asyncio
async def test_invalid_cookie_returns_anonymous():
    websocket = _websocket(cookie="invalid")

    with (
        patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
        patch(
            "app.api.ws.authenticator.get_user_from_cookie",
            new=AsyncMock(return_value=(None, None)),
        ) as get_cookie,
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (None, None, None)
    get_cookie.assert_awaited_once_with("invalid")


@pytest.mark.asyncio
async def test_successful_ticket_auth_skips_cookie_fallback():
    websocket = _websocket(ticket="ticket", cookie="stale-cookie")
    user = SimpleNamespace(id="user-1")

    with (
        patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
        patch(
            "app.api.ws.authenticator.get_user_from_ticket",
            new=AsyncMock(return_value=(user, "ticket-jti")),
        ) as get_ticket,
        patch(
            "app.api.ws.authenticator.get_user_from_cookie", new=AsyncMock()
        ) as get_cookie,
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (user, "ticket-jti", None)
    get_ticket.assert_awaited_once_with("ticket")
    get_cookie.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_cookie_auth_is_returned_when_ticket_is_absent():
    websocket = _websocket(cookie="access-token")
    user = SimpleNamespace(id="user-2")

    with (
        patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
        patch(
            "app.api.ws.authenticator.get_user_from_cookie",
            new=AsyncMock(return_value=(user, "cookie-jti")),
        ) as get_cookie,
    ):
        result = await WsAuthenticator().authenticate_upgrade(websocket)

    assert result == (user, "cookie-jti", None)
    get_cookie.assert_awaited_once_with("access-token")
