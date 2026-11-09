"""WebSocket fanout must not nest a DB checkout under pool saturation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.ws import auth, connection_manager
from app.core.nats_broker import broker
from app.models.chat import chat_participants
from app.repositories.chat_repository import ChatRepository
from app.services.chat import command_service


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["nats-only", "local", "local-auth"])
async def test_typing_at_pool_capacity_reaches_authorized_recipients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    database = tmp_path / "pool.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database.as_posix()}",
        pool_size=3,
        max_overflow=1,
        pool_timeout=0.3,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    chat_id, actor_id, recipient_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    actor = SimpleNamespace(id=actor_id, profile=None, email="actor@example.test")
    recipient = SimpleNamespace(id=recipient_id, is_active=True, mfa_epoch=0)
    active_session = SimpleNamespace(
        user_id=recipient_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=None,
        mfa_epoch=0,
    )
    ready, release = 0, asyncio.Event()

    class CheckedRepository(ChatRepository):
        async def check_participant(self, requested_chat_id, requested_user_id):
            nonlocal ready
            result = await super().check_participant(
                requested_chat_id, requested_user_id
            )
            ready += 1
            if ready == 4:
                release.set()
            await release.wait()
            return result

    class UserRepository:
        def __init__(self, session):
            self.session = session

        async def get(self, _user_id):
            await self.session.execute(text("SELECT 1"))
            return recipient

    class SessionRepository:
        def __init__(self, _session):
            pass

        async def get_by_jti(self, _jti):
            return active_session

    redis = SimpleNamespace(exists=AsyncMock(return_value=0))
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=redis)
    )
    monkeypatch.setattr(auth, "UserRepository", UserRepository)
    monkeypatch.setattr(auth, "SessionRepository", SessionRepository)
    monkeypatch.setattr(auth, "async_session", sessions)
    publish = AsyncMock()
    monkeypatch.setattr(broker, "publish_core", publish)
    manager = connection_manager.ConnectionManager(session_factory=sessions)
    monkeypatch.setattr(command_service, "ws_manager", manager)
    websocket = AsyncMock()

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE chat_participants (chat_id CHAR(32), user_id CHAR(32))"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE users (id CHAR(32) PRIMARY KEY, is_active BOOLEAN, mfa_epoch INTEGER)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE active_sessions (user_id CHAR(32), jti TEXT, expires_at DATETIME, revoked_at DATETIME, mfa_epoch INTEGER)"
                )
            )
            await connection.execute(
                text("INSERT INTO users (id, is_active, mfa_epoch) VALUES (:id, 1, 0)"),
                {"id": recipient_id.hex},
            )
            await connection.execute(
                text(
                    "INSERT INTO active_sessions (user_id, jti, expires_at, revoked_at, mfa_epoch) VALUES (:id, 'valid', :expires, NULL, 0)"
                ),
                {
                    "id": recipient_id.hex,
                    "expires": active_session.expires_at.isoformat(),
                },
            )
            await connection.execute(
                chat_participants.insert(),
                [
                    {"chat_id": chat_id, "user_id": user_id}
                    for user_id in (actor_id, recipient_id)
                ],
            )

        if mode != "nats-only":
            assert await manager.connect(websocket, recipient_id, session_jti="valid")
        if mode == "local-auth":
            # Isolate per-socket session checks after an already-resolved roster.
            monkeypatch.setattr(
                manager,
                "_get_chat_participants",
                AsyncMock(return_value=[actor_id, recipient_id]),
            )

        async def issue_typing() -> None:
            async with sessions() as request_session:
                repository = CheckedRepository(request_session)
                service = command_service.ChatMaintenanceService(
                    SimpleNamespace(chats=repository, session=request_session), None
                )
                await service.broadcast_typing(chat_id, actor, "en")

        outcomes = await asyncio.wait_for(
            asyncio.gather(*(issue_typing() for _ in range(4)), return_exceptions=True),
            timeout=3,
        )
        assert outcomes == [None] * 4
        assert publish.await_count == 4
        if mode != "nats-only":
            assert websocket.send_json.await_count == 4
    finally:
        await engine.dispose()
