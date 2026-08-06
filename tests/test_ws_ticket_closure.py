"""Closure test for NullCache degradation during WS ticket issuance."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.ws.ticket import WsTicketResponse, issue_ws_upgrade_ticket


@pytest.mark.asyncio
async def test_issue_ws_upgrade_ticket_returns_ticket_when_cache_is_unavailable():
    user_id = uuid4()
    jti = "session-jti"
    request = MagicMock()
    request.headers = {}

    with (
        patch(
            "app.api.ws.ticket.AuthTokenService.extract_and_decode_token",
            return_value={"sub": str(user_id), "jti": jti},
        ),
        patch(
            "app.api.ws.ticket.AuthTokenService.validate_payload",
            return_value=(user_id, jti),
        ),
        patch(
            "app.api.ws.ticket.get_cache_client",
            new=AsyncMock(side_effect=RuntimeError("NullCache active")),
        ),
        patch("app.api.ws.ticket.resolve_locale", return_value="en"),
    ):
        result = await issue_ws_upgrade_ticket(request=request, token=None)

    assert isinstance(result, WsTicketResponse)
    assert len(result.ticket) == 64
    assert result.expires_in == 15
