"""Tests for the WebSocket upgrade ticket system (RZ-W14-01, Wave 14).

Covers:
- POST /ws/ticket endpoint: auth, ticket generation, Redis storage
- get_user_from_ticket(): GETDEL semantics, single-use guarantee, invalid/expired tickets
- WsAuthenticator.authenticate_upgrade(): ticket path, cookie fallback, subprotocol rejection
"""

from __future__ import annotations

import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws.ticket import TICKET_KEY_PREFIX, WsTicketResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_active_session(
    user_id: uuid.UUID, jti: str, revoked: bool = False
) -> MagicMock:
    session = MagicMock()
    session.user_id = user_id
    session.jti = jti
    session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    session.revoked_at = datetime.now(UTC) if revoked else None
    return session


def _make_user(active: bool = True) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = active
    return user


# ---------------------------------------------------------------------------
# POST /ws/ticket  (unit tests via mocked dependencies)
# ---------------------------------------------------------------------------


class TestIssueWsUpgradeTicket:
    """Tests for app/api/ws/ticket.issue_ws_upgrade_ticket."""

    @pytest.mark.asyncio
    async def test_returns_ticket_and_ttl(self):
        """Successful ticket issuance returns a 64-char hex ticket with expires_in=15."""
        from app.api.ws.ticket import issue_ws_upgrade_ticket

        user_id = uuid.uuid4()
        jti = str(uuid.uuid4())

        mock_request = MagicMock()
        mock_request.cookies = {"access_token_v2": "dummy"}
        mock_request.headers = {}
        mock_request.state.active_session = _make_active_session(user_id, jti)
        mock_user = _make_user()
        mock_user.id = user_id

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with (
            patch(
                "app.api.ws.ticket.get_cache_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("app.api.ws.ticket.resolve_locale", return_value="en"),
        ):
            result = await issue_ws_upgrade_ticket(
                request=mock_request, current_user=mock_user
            )

        assert isinstance(result, WsTicketResponse)
        assert len(result.ticket) == 64
        assert result.expires_in == 15

    @pytest.mark.asyncio
    async def test_redis_set_called_with_correct_key_and_ttl(self):
        """Ticket stored under 'ott:ws:{ticket}' with ex=15."""
        from app.api.ws.ticket import issue_ws_upgrade_ticket

        user_id = uuid.uuid4()
        jti = str(uuid.uuid4())

        mock_request = MagicMock()
        mock_request.headers = {"X-Tenant-ID": "00000000-0000-0000-0000-000000000999"}
        mock_request.state.active_session = _make_active_session(user_id, jti)
        mock_user = _make_user()
        mock_user.id = user_id
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with (
            patch(
                "app.api.ws.ticket.get_cache_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("app.api.ws.ticket.resolve_locale", return_value="en"),
        ):
            result = await issue_ws_upgrade_ticket(
                request=mock_request, current_user=mock_user
            )

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key_arg = call_args[0][0]
        value_arg = call_args[0][1]

        assert key_arg == f"{TICKET_KEY_PREFIX}{result.ticket}"
        assert value_arg == f"{user_id}:{jti}"
        assert call_args[1]["ex"] == 15

    @pytest.mark.asyncio
    async def test_ticket_entropy_is_unique(self):
        """Each call generates a distinct ticket (256-bit collision resistance)."""
        from app.api.ws.ticket import issue_ws_upgrade_ticket

        user_id = uuid.uuid4()
        jti = str(uuid.uuid4())
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state.active_session = _make_active_session(user_id, jti)
        mock_user = _make_user()
        mock_user.id = user_id
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        tickets = set()
        for _ in range(5):
            with (
                patch(
                    "app.api.ws.ticket.get_cache_client",
                    new=AsyncMock(return_value=mock_redis),
                ),
                patch("app.api.ws.ticket.resolve_locale", return_value="en"),
            ):
                result = await issue_ws_upgrade_ticket(
                    request=mock_request, current_user=mock_user
                )
            tickets.add(result.ticket)

        assert len(tickets) == 5, "Each call must generate a unique ticket"


# ---------------------------------------------------------------------------
# get_user_from_ticket
# ---------------------------------------------------------------------------


class TestGetUserFromTicket:
    """Tests for app/api/ws/auth.get_user_from_ticket."""

    @pytest.mark.asyncio
    async def test_valid_ticket_returns_user_and_jti(self):
        """A valid ticket consumed via GETDEL resolves to the user."""
        from app.api.ws.auth import get_user_from_ticket

        user_id = uuid.uuid4()
        jti = str(uuid.uuid4())
        ticket = secrets.token_hex(32)
        stored_value = f"{user_id}:{jti}"

        mock_user = _make_user()
        mock_user.id = user_id
        mock_session = _make_active_session(user_id, jti)

        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(return_value=stored_value)
        mock_redis.exists = AsyncMock(return_value=0)

        @asynccontextmanager
        async def mock_db_session():
            yield MagicMock()

        with (
            patch(
                "app.deps.cache.get_cache_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("app.api.ws.ticket.TICKET_KEY_PREFIX", TICKET_KEY_PREFIX),
            patch(
                "app.api.ws.auth.async_session",
                return_value=mock_db_session(),
            ),
            patch(
                "app.api.ws.auth.UserRepository",
            ) as MockUserRepo,
            patch(
                "app.api.ws.auth.SessionRepository",
            ) as MockSessionRepo,
        ):
            mock_user_repo = AsyncMock()
            mock_user_repo.get = AsyncMock(return_value=mock_user)
            MockUserRepo.return_value = mock_user_repo

            mock_session_repo = AsyncMock()
            mock_session_repo.get_by_jti = AsyncMock(return_value=mock_session)
            MockSessionRepo.return_value = mock_session_repo

            result_user, result_jti = await get_user_from_ticket(ticket)

        assert result_user is mock_user
        assert result_jti == jti

    @pytest.mark.asyncio
    async def test_missing_ticket_returns_none(self):
        """GETDEL returns None (ticket expired / not found) → (None, None)."""
        from app.api.ws.auth import get_user_from_ticket

        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(return_value=None)

        with patch(
            "app.deps.cache.get_cache_client", new=AsyncMock(return_value=mock_redis)
        ):
            result = await get_user_from_ticket(secrets.token_hex(32))

        assert result == (None, None)

    @pytest.mark.asyncio
    async def test_ticket_is_single_use(self):
        """Second call with the same ticket gets None (GETDEL deleted it on first use)."""
        from app.api.ws.auth import get_user_from_ticket

        ticket = secrets.token_hex(32)
        # First call: GETDEL returns value; second call: None (already deleted)
        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(side_effect=["some-uid:some-jti", None])
        mock_redis.exists = AsyncMock(return_value=0)

        # First call — we expect it to attempt user resolution; short-circuit on invalid UUID
        with patch(
            "app.deps.cache.get_cache_client", new=AsyncMock(return_value=mock_redis)
        ):
            await get_user_from_ticket(ticket)  # consume
            result = await get_user_from_ticket(ticket)  # replay attempt

        assert result == (None, None), "Second use of the same ticket must be rejected"

    @pytest.mark.asyncio
    async def test_malformed_ticket_no_colon(self):
        """Ticket payload without ':' separator returns (None, None) without crashing."""
        from app.api.ws.auth import get_user_from_ticket

        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(return_value="nodivider")

        with patch(
            "app.deps.cache.get_cache_client", new=AsyncMock(return_value=mock_redis)
        ):
            result = await get_user_from_ticket(secrets.token_hex(32))

        assert result == (None, None)

    @pytest.mark.asyncio
    async def test_ticket_payload_with_tenant_segment_is_rejected(self):
        """The canonical OTT payload is exactly ``user_id:jti``."""
        from app.api.ws.auth import get_user_from_ticket

        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(
            return_value=f"{uuid.uuid4()}:{uuid.uuid4()}:{uuid.uuid4()}"
        )

        with patch(
            "app.deps.cache.get_cache_client", new=AsyncMock(return_value=mock_redis)
        ):
            result = await get_user_from_ticket(secrets.token_hex(32))

        assert result == (None, None)

    @pytest.mark.asyncio
    async def test_revoked_session_returns_none(self):
        """Even with a valid ticket, a revoked session results in (None, None)."""
        from app.api.ws.auth import get_user_from_ticket

        user_id = uuid.uuid4()
        jti = str(uuid.uuid4())
        ticket = secrets.token_hex(32)

        mock_redis = AsyncMock()
        mock_redis.getdel = AsyncMock(return_value=f"{user_id}:{jti}")
        # Simulate Redis revocation key present
        mock_redis.exists = AsyncMock(return_value=1)

        with patch(
            "app.deps.cache.get_cache_client", new=AsyncMock(return_value=mock_redis)
        ):
            result = await get_user_from_ticket(ticket)

        assert result == (None, None)


# ---------------------------------------------------------------------------
# WsAuthenticator.authenticate_upgrade
# ---------------------------------------------------------------------------


class TestWsAuthenticatorTicketPath:
    """Tests for WsAuthenticator.authenticate_upgrade with ticket flow."""

    def _make_websocket(
        self,
        ticket: str | None = None,
        cookie: str | None = None,
        origin: str | None = None,
    ) -> MagicMock:
        ws = MagicMock()
        ws.headers = {}
        if origin:
            ws.headers["origin"] = origin
        ws.cookies = {}
        if cookie:
            ws.cookies["access_token_v2"] = cookie
        ws.query_params = {}
        if ticket:
            ws.query_params["ticket"] = ticket
        ws.close = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_ticket_path_succeeds(self):
        """Valid ?ticket= query param authenticates successfully."""
        from app.api.ws.authenticator import WsAuthenticator

        mock_user = _make_user()
        jti = str(uuid.uuid4())
        ticket = secrets.token_hex(32)

        ws = self._make_websocket(ticket=ticket)

        with (
            patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
            patch(
                "app.api.ws.authenticator.get_user_from_ticket",
                new=AsyncMock(return_value=(mock_user, jti)),
            ),
        ):
            auth = WsAuthenticator()
            user, session_jti, subproto = await auth.authenticate_upgrade(ws)

        assert user is mock_user
        assert session_jti == jti
        assert subproto is None  # subprotocol always None after RZ-W14-01

    @pytest.mark.asyncio
    async def test_cookie_fallback_when_no_ticket(self):
        """Cookie auth is used when no ticket query param is present."""
        from app.api.ws.authenticator import WsAuthenticator

        mock_user = _make_user()
        jti = str(uuid.uuid4())

        ws = self._make_websocket(cookie="some-jwt-value")

        with (
            patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
            patch(
                "app.api.ws.authenticator.get_user_from_cookie",
                new=AsyncMock(return_value=(mock_user, jti)),
            ),
        ):
            auth = WsAuthenticator()
            user, session_jti, _ = await auth.authenticate_upgrade(ws)

        assert user is mock_user
        assert session_jti == jti

    @pytest.mark.asyncio
    async def test_invalid_ticket_falls_through_to_cookie(self):
        """An invalid ticket causes the authenticator to try the cookie fallback."""
        from app.api.ws.authenticator import WsAuthenticator

        mock_user = _make_user()
        jti = str(uuid.uuid4())
        ticket = secrets.token_hex(32)

        ws = self._make_websocket(ticket=ticket, cookie="some-jwt-value")

        with (
            patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
            patch(
                "app.api.ws.authenticator.get_user_from_ticket",
                new=AsyncMock(return_value=(None, None)),
            ),
            patch(
                "app.api.ws.authenticator.get_user_from_cookie",
                new=AsyncMock(return_value=(mock_user, jti)),
            ),
        ):
            auth = WsAuthenticator()
            user, _session_jti, _ = await auth.authenticate_upgrade(ws)

        assert user is mock_user

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none_user(self):
        """No ticket and no cookie → user is None."""
        from app.api.ws.authenticator import WsAuthenticator

        ws = self._make_websocket()  # no ticket, no cookie

        with patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()):
            auth = WsAuthenticator()
            user, session_jti, _ = await auth.authenticate_upgrade(ws)

        assert user is None
        assert session_jti is None

    @pytest.mark.asyncio
    async def test_sec_websocket_protocol_header_is_ignored(self):
        """The old Sec-WebSocket-Protocol JWT header is no longer accepted."""
        from app.api.ws.authenticator import WsAuthenticator

        ws = self._make_websocket()
        # Simulate a client sending the old-style header
        ws.headers["sec-websocket-protocol"] = (
            "access_token, eyJhbGciOiJIUzI1NiJ9.test.sig"
        )

        with (
            patch("app.api.ws.authenticator._ALLOWED_WS_ORIGINS", frozenset()),
            patch(
                "app.api.ws.authenticator.get_user_from_cookie",
                new=AsyncMock(return_value=(None, None)),
            ),
        ):
            auth = WsAuthenticator()
            user, _, _ = await auth.authenticate_upgrade(ws)

        assert user is None, (
            "Sec-WebSocket-Protocol JWT must be ignored after RZ-W14-01 fix"
        )
