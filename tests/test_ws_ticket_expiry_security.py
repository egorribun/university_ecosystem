"""Cross-service OTT expiry must be immutable, explicit and fail closed."""

from datetime import UTC, datetime, timedelta, tzinfo
from types import SimpleNamespace
from typing import Self
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request

from app.api.ws import auth, ticket


@pytest.mark.asyncio
async def test_issued_ticket_carries_true_session_expiry():
    user = SimpleNamespace(id=uuid4(), is_active=True)
    expiry = datetime.now(UTC) + timedelta(seconds=93, microseconds=123456)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.active_session = SimpleNamespace(
        user_id=user.id, jti="session-jti", revoked_at=None, expires_at=expiry
    )
    cache = AsyncMock()
    with patch.object(ticket, "get_cache_client", AsyncMock(return_value=cache)):
        result = await ticket.issue_ws_upgrade_ticket(request, user)
    cache.set.assert_awaited_once_with(
        f"ott:ws:{result.ticket}",
        f"{user.id}:session-jti:{int(expiry.timestamp())}",
        ex=result.expires_in,
    )
    assert result.expires_in == ticket._get_ticket_ttl()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_bytes", [True, False])
async def test_ticket_consumer_accepts_unexpired_three_field_contract(as_bytes):
    user_id = str(uuid4())
    user = object()
    expiry = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    payload = f"{user_id}:session-jti:{expiry}"
    cache = SimpleNamespace(
        getdel=AsyncMock(return_value=payload.encode() if as_bytes else payload)
    )
    resolve = AsyncMock(return_value=(user, "session-jti"))
    with (
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(auth, "_resolve_user_from_ids", resolve),
    ):
        assert await auth.get_user_from_ticket("a" * 64) == (user, "session-jti")
    resolve.assert_awaited_once_with(user_id, "session-jti")


@pytest.mark.asyncio
async def test_ticket_expiry_at_current_second_is_rejected_before_session_lookup() -> (
    None
):
    expired_at = datetime(2030, 1, 1, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            fixed = cls(2030, 1, 1, tzinfo=UTC)
            return fixed if tz is None else fixed.astimezone(tz)

    user_id = str(uuid4())
    cache = SimpleNamespace(
        getdel=AsyncMock(
            return_value=f"{user_id}:session-jti:{int(expired_at.timestamp())}"
        )
    )
    resolve = AsyncMock(return_value=(object(), "session-jti"))

    with (
        patch.object(auth, "datetime", FrozenDateTime),
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(auth, "_resolve_user_from_ids", resolve),
    ):
        result = await auth.get_user_from_ticket("d" * 64)

    assert result == (None, None)
    cache.getdel.assert_awaited_once()
    resolve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        ":",
        ":0",
        ":1",
        ":-1",
        ":+9999999999",
        ":09999999999",
        ":9999999999.0",
        ":1e20",
        ": 9999999999",
        ":9999999999 ",
        ":９９９９９９９９９９",
        ":9223372036854775808",
        ":9999999999:tenant",
    ],
)
async def test_ticket_consumer_rejects_legacy_expired_and_noncanonical_expiry(suffix):
    cache = SimpleNamespace(
        getdel=AsyncMock(return_value=f"{uuid4()}:session-jti{suffix}")
    )
    resolve = AsyncMock(return_value=(object(), "session-jti"))
    with (
        patch("app.deps.cache.get_cache_client", AsyncMock(return_value=cache)),
        patch.object(auth, "_resolve_user_from_ids", resolve),
    ):
        assert await auth.get_user_from_ticket("b" * 64) == (None, None)
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_issuer_rejects_session_whose_floored_cutoff_has_elapsed():
    from fastapi import HTTPException

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 1, 1, 12, 0, 0, 100000, tzinfo=UTC)

    user = SimpleNamespace(id=uuid4(), is_active=True)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.active_session = SimpleNamespace(
        user_id=user.id,
        jti="session-jti",
        revoked_at=None,
        expires_at=FixedDateTime(2030, 1, 1, 12, 0, 0, 900000, tzinfo=UTC),
    )
    cache = AsyncMock()
    with (
        patch.object(ticket, "datetime", FixedDateTime),
        patch.object(ticket, "get_cache_client", cache),
        pytest.raises(HTTPException) as error,
    ):
        await ticket.issue_ws_upgrade_ticket(request, user)
    assert error.value.status_code == 401
    cache.assert_not_awaited()
