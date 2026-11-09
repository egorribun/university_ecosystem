"""Exercise session revalidation across the real WebSocket ASGI boundary."""

from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import Message

from app.api import websocket as websocket_api
from app.api.ws import auth, connection_manager
from app.api.ws.connection_manager import ConnectionManager
from app.api.ws.ticket import TICKET_KEY_PREFIX
from app.models import ActiveSession, User


async def _exercise_socket(
    direction: str,
    change: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
    *,
    bypass_revalidation: bool,
) -> None:
    """A valid upgraded session stops exchanging frames when its state changes."""
    user = await user_factory(hashed_password=secrets.token_urlsafe(32))
    user_id = user.id
    jti = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    db_session.add(ActiveSession(user_id=user_id, jti=jti, expires_at=expires_at))
    await db_session.commit()
    assert db_session.bind is not None
    monkeypatch.setattr(
        auth,
        "async_session",
        async_sessionmaker(db_session.bind, expire_on_commit=False),
    )

    ticket = secrets.token_hex(32)
    ticket_payload = f"{user_id}:{jti}:{int(expires_at.timestamp())}"
    ticket_store = {f"{TICKET_KEY_PREFIX}{ticket}": ticket_payload}
    revoked: set[str] = set()
    unavailable = False

    async def getdel(key: str) -> str | None:
        return ticket_store.pop(key, None)

    async def exists(key: str) -> int:
        if unavailable:
            raise OSError("revocation store unavailable")
        return int(key in revoked)

    cache = SimpleNamespace(getdel=getdel)
    revocation_store = SimpleNamespace(exists=exists)
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=cache)
    )
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=revocation_store)
    )
    manager = ConnectionManager()
    manager.broadcast_presence = AsyncMock(return_value=0)
    monkeypatch.setattr(websocket_api, "manager", manager)

    app = FastAPI()
    app.include_router(websocket_api.router)
    incoming: asyncio.Queue[Message] = asyncio.Queue()
    outgoing: asyncio.Queue[Message] = asyncio.Queue()
    await incoming.put({"type": "websocket.connect"})

    async def receive() -> Message:
        return await incoming.get()

    async def send(message: Message) -> None:
        await outgoing.put(message)
        if message["type"] == "websocket.close":
            await incoming.put(
                {"type": "websocket.disconnect", "code": message.get("code", 1000)}
            )

    scope: dict[str, Any] = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws/chat",
        "raw_path": b"/ws/chat",
        "query_string": f"ticket={ticket}".encode("ascii"),
        "headers": [],
        "client": ("127.0.0.1", 42001),
        "server": ("testserver", 80),
        "subprotocols": [],
        "state": {},
    }

    async def next_outgoing() -> Message:
        return await asyncio.wait_for(outgoing.get(), timeout=3)

    task = asyncio.create_task(app(scope, receive, send))
    try:
        assert (await next_outgoing())["type"] == "websocket.accept"
        assert not ticket_store

        nonce = secrets.token_hex(16)
        await incoming.put(
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": "heartbeat_ping", "nonce": nonce}),
            }
        )
        response = await next_outgoing()
        assert response["type"] == "websocket.send"
        assert json.loads(response["text"]) == {
            "type": "heartbeat_pong",
            "nonce": nonce,
        }
        assert await manager.send_to_user(user_id, {"type": "before"}) == 1
        response = await next_outgoing()
        assert response["type"] == "websocket.send"
        assert json.loads(response["text"]) == {"type": "before"}

        if change == "revoked":
            await db_session.execute(
                update(ActiveSession)
                .where(ActiveSession.jti == jti)
                .values(revoked_at=datetime.now(UTC))
            )
            await db_session.commit()
        elif change == "mfa_epoch":
            await db_session.execute(
                update(User).where(User.id == user_id).values(mfa_epoch=1)
            )
            await db_session.commit()
        elif change == "tombstone":
            revoked.add(f"revoked:jti:{jti}")
        else:
            unavailable = True

        if bypass_revalidation:
            resolver = AsyncMock(return_value=(user, jti))
            module = websocket_api if direction == "inbound" else connection_manager
            monkeypatch.setattr(module, "_resolve_user_from_ids", resolver)

        if direction == "inbound":
            await incoming.put(
                {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "heartbeat_ping", "nonce": nonce}),
                }
            )
        else:
            sent = await manager.send_to_user(user_id, {"type": "after"})
            assert sent == int(bypass_revalidation)

        response = await next_outgoing()
        if bypass_revalidation:
            assert response["type"] == "websocket.send"
            expected = (
                {"type": "heartbeat_pong", "nonce": nonce}
                if direction == "inbound"
                else {"type": "after"}
            )
            assert json.loads(response["text"]) == expected
            resolver.assert_awaited_once_with(str(user_id), jti)
            await incoming.put({"type": "websocket.disconnect", "code": 1000})
        else:
            assert response["type"] == "websocket.close"
            assert response["code"] == 4001
            assert response["reason"] == "Session expired or revoked"
        await asyncio.wait_for(task, timeout=3)
        assert not manager.is_online(user_id)
        assert outgoing.empty()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
@pytest.mark.parametrize("change", ["revoked", "mfa_epoch", "tombstone", "unavailable"])
async def test_real_asgi_socket_rechecks_session_before_frames(
    direction: str,
    change: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _exercise_socket(
        direction,
        change,
        db_session,
        user_factory,
        monkeypatch,
        bypass_revalidation=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["inbound", "outbound"])
async def test_bypassing_revalidation_exposes_revoked_frames(
    direction: str,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _exercise_socket(
        direction,
        "revoked",
        db_session,
        user_factory,
        monkeypatch,
        bypass_revalidation=True,
    )
