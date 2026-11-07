"""Message notification fanout must not nest checkout under pool pressure."""

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

from app.api.ws import auth, connection_manager, presence
from app.core.nats_broker import broker
from app.models.chat import chat_participants
from app.services.chat import notification_service


@pytest.mark.asyncio
async def test_notification_at_pool_capacity_uses_its_borrowed_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "notification.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database.as_posix()}",
        pool_size=3,
        max_overflow=1,
        pool_timeout=0.3,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    chat_id, actor_id, recipient_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sender = SimpleNamespace(id=actor_id, profile=None)
    message = SimpleNamespace(
        id=uuid.uuid4(), chat_id=chat_id, sender_id=actor_id, content="hi"
    )
    barrier = asyncio.Barrier(4)

    class PresenceSessions:
        def __init__(self, session):
            self.session = session

        async def get_last_seen_map(self, _ids):
            await self.session.execute(text("SELECT 1"))
            return {}

    monkeypatch.setattr(
        "app.repositories.session_repository.SessionRepository", PresenceSessions
    )
    monkeypatch.setattr(presence, "async_session", sessions)
    monkeypatch.setattr(
        auth,
        "get_revocation_redis_client",
        AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=0))),
    )
    monkeypatch.setattr(
        notification_service, "serialize_message", lambda *_a, **_kw: {"content": "hi"}
    )
    publish = AsyncMock()
    monkeypatch.setattr(broker, "publish_core", publish)
    manager = connection_manager.ConnectionManager(session_factory=sessions)
    monkeypatch.setattr(notification_service, "ws_manager", manager)
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
                chat_participants.insert(),
                [
                    {"chat_id": chat_id, "user_id": user_id}
                    for user_id in (actor_id, recipient_id)
                ],
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
                    "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                },
            )
        assert await manager.connect(websocket, recipient_id, session_jti="valid")

        async def notify() -> None:
            async with sessions() as session:
                await session.execute(text("SELECT 1"))
                await barrier.wait()
                service = notification_service.ChatNotificationService(session)
                # Only sender in the notification list avoids unrelated push writes.
                await service.notify_new_message(message, [sender], sender)

        outcomes = await asyncio.wait_for(
            asyncio.gather(*(notify() for _ in range(4)), return_exceptions=True),
            timeout=3,
        )
        assert outcomes == [None] * 4
        assert publish.await_count == 4
        assert websocket.send_json.await_count == 4
    finally:
        await engine.dispose()
