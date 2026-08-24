"""Security-boundary closure tests for WebSocket ticket issuance."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.ws.ticket import issue_ws_upgrade_ticket
from app.models import User


def _ticket_identity(
    *,
    user_id: UUID | None = None,
    session_user_id: UUID | None = None,
    active: bool = True,
    revoked: bool = False,
    expired: bool = False,
) -> tuple[MagicMock, User, SimpleNamespace]:
    resolved_user_id = user_id or uuid4()
    request = MagicMock()
    request.headers = {}
    request.state.active_session = SimpleNamespace(
        user_id=session_user_id or resolved_user_id,
        jti=str(uuid4()),
        revoked_at=datetime.now(UTC) if revoked else None,
        expires_at=datetime.now(UTC)
        + (timedelta(seconds=-1) if expired else timedelta(hours=1)),
    )
    user = cast(User, SimpleNamespace(id=resolved_user_id, is_active=active))
    return request, user, request.state.active_session


@pytest.mark.asyncio
async def test_issue_ws_upgrade_ticket_fails_closed_when_cache_is_unavailable() -> None:
    request, user, _session = _ticket_identity()

    with patch(
        "app.api.ws.ticket.get_cache_client",
        new=AsyncMock(side_effect=RuntimeError("NullCache active")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await issue_ws_upgrade_ticket(request=request, current_user=user)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_issue_ws_upgrade_ticket_normalizes_naive_session_expiry() -> None:
    request, user, session = _ticket_identity()
    session.expires_at = datetime.now() + timedelta(hours=1)
    cache_client = AsyncMock()

    with patch(
        "app.api.ws.ticket.get_cache_client",
        new=AsyncMock(return_value=cache_client),
    ):
        response = await issue_ws_upgrade_ticket(request=request, current_user=user)

    assert response.expires_in > 0
    cache_client.set.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("active", "revoked", "expired", "session_user_id", "case"),
    (
        (False, False, False, None, "inactive user"),
        (True, True, False, None, "revoked session"),
        (True, False, True, None, "expired session"),
        (True, False, False, uuid4(), "session/user mismatch"),
    ),
)
async def test_issue_ws_upgrade_ticket_rejects_invalid_identity_before_redis(
    active: bool,
    revoked: bool,
    expired: bool,
    session_user_id: UUID | None,
    case: str,
) -> None:
    request, user, _session = _ticket_identity(
        active=active,
        revoked=revoked,
        expired=expired,
        session_user_id=session_user_id,
    )
    cache_client = AsyncMock()

    with patch("app.api.ws.ticket.get_cache_client", new=cache_client):
        with pytest.raises(HTTPException) as exc_info:
            await issue_ws_upgrade_ticket(request=request, current_user=user)

    assert exc_info.value.status_code == 401, case
    cache_client.assert_not_awaited()
