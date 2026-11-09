"""Redis contracts exercised across the actual Python producer and consumer.

The in-memory Redis server keeps the tests hermetic; it does not stand in for
Go gateway or ws-hub execution. Those services have separate runtime tests.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi import Request

from app.api.ws import auth, ticket
from app.auth.redis_session import RedisSessionBackend


@pytest_asyncio.fixture
async def ws_ticket_boundary(monkeypatch: pytest.MonkeyPatch):
    """Share separate cache and revocation stores between production paths."""
    cache = FakeRedis(decode_responses=True)
    revocations = FakeRedis(decode_responses=True)
    user = SimpleNamespace(id=uuid4(), is_active=True, mfa_epoch=0)
    session = SimpleNamespace(
        user_id=user.id,
        jti=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=None,
        mfa_epoch=0,
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/ws/ticket",
            "headers": [],
            "query_string": b"",
        }
    )
    request.state.active_session = session

    monkeypatch.setattr(ticket, "get_cache_client", AsyncMock(return_value=cache))
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
    )
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=revocations)
    )

    @asynccontextmanager
    async def database_session():
        yield object()

    # The database is outside this Redis contract. Keep the production session
    # policy and verify that the consumer actually asks for the issued IDs.
    user_repo = SimpleNamespace(
        get=AsyncMock(side_effect=lambda user_id: user if user_id == user.id else None)
    )
    session_repo = SimpleNamespace(
        get_by_jti=AsyncMock(
            side_effect=lambda jti: session if jti == session.jti else None
        )
    )
    monkeypatch.setattr(auth, "async_session", database_session)
    monkeypatch.setattr(auth, "UserRepository", lambda _: user_repo)
    monkeypatch.setattr(auth, "SessionRepository", lambda _: session_repo)

    try:
        yield SimpleNamespace(
            cache=cache,
            revocations=revocations,
            user=user,
            session=session,
            request=request,
            user_repo=user_repo,
            session_repo=session_repo,
        )
    finally:
        await cache.aclose()
        await revocations.aclose()


@pytest.mark.asyncio
async def test_issued_ticket_is_consumed_once_with_session_expiry(ws_ticket_boundary):
    """An actual issued ticket crosses Redis and the WS auth consumer."""
    boundary = ws_ticket_boundary
    issued = await ticket.issue_ws_upgrade_ticket(boundary.request, boundary.user)

    assert re.fullmatch(r"[0-9a-f]{64}", issued.ticket)
    key = f"ott:ws:{issued.ticket}"
    assert await boundary.cache.get(key) == (
        f"{boundary.user.id}:{boundary.session.jti}:"
        f"{int(boundary.session.expires_at.timestamp())}"
    )
    assert 0 < await boundary.cache.ttl(key) <= issued.expires_in

    assert await auth.get_user_from_ticket(issued.ticket) == (
        boundary.user,
        boundary.session.jti,
    )
    boundary.user_repo.get.assert_awaited_once_with(boundary.user.id)
    boundary.session_repo.get_by_jti.assert_awaited_once_with(boundary.session.jti)
    assert await boundary.cache.get(key) is None
    assert await auth.get_user_from_ticket(issued.ticket) == (None, None)


@pytest.mark.asyncio
async def test_published_revocation_blocks_an_issued_ticket(ws_ticket_boundary):
    """The session producer writes a tombstone that WS auth actually reads."""
    boundary = ws_ticket_boundary
    backend = RedisSessionBackend(
        boundary.cache, revocation_redis_client=boundary.revocations
    )
    pubsub = boundary.revocations.pubsub()
    try:
        await pubsub.subscribe("session:revocations")
        subscribed = await pubsub.get_message(timeout=1)
        assert subscribed is not None and subscribed["type"] == "subscribe"
        await backend.register_session(
            str(boundary.user.id), boundary.session.jti, boundary.session.expires_at
        )
        assert await backend.is_session_valid(boundary.session.jti)
        issued = await ticket.issue_ws_upgrade_ticket(boundary.request, boundary.user)

        await backend.revoke_session(
            boundary.session.jti, expires_at=boundary.session.expires_at
        )

        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        assert message is not None
        assert message["channel"] == "session:revocations"
        assert message["data"] == boundary.session.jti
        assert (
            await boundary.revocations.get(f"revoked:jti:{boundary.session.jti}") == "1"
        )
        assert await boundary.cache.get(f"revoked:jti:{boundary.session.jti}") is None
        assert not await backend.is_session_valid(boundary.session.jti)
        assert await auth.get_user_from_ticket(issued.ticket) == (None, None)
        boundary.user_repo.get.assert_not_awaited()
        boundary.session_repo.get_by_jti.assert_not_awaited()
    finally:
        await pubsub.aclose()
