"""A borrowed database session must retain the normal WS auth guarantees."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import make_transient_to_detached

from app.api.ws import auth, connection_manager
from app.core.nats_broker import broker
from app.models import ActiveSession, User


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dialect", "isolation", "allowed"),
    [
        ("postgresql", "READ COMMITTED", True),
        ("postgresql", "REPEATABLE READ", False),
        ("postgresql", "SERIALIZABLE", False),
        ("sqlite", "SERIALIZABLE", True),
    ],
)
async def test_borrowed_postgres_reads_require_read_committed(
    dialect: str, isolation: str, allowed: bool
) -> None:
    connection = SimpleNamespace(
        dialect=SimpleNamespace(name=dialect),
        get_isolation_level=AsyncMock(return_value=isolation),
    )
    session = SimpleNamespace(connection=AsyncMock(return_value=connection))

    if allowed:
        await auth.require_fresh_ws_reads(session)
    else:
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await auth.require_fresh_ws_reads(session)
    if dialect == "sqlite":
        connection.get_isolation_level.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing-session",
        "wrong-owner",
        "inactive-user",
        "revoked-session",
        "expired-session",
        "mfa-epoch",
        "tombstone",
        "revocation-unavailable",
        "database-unavailable",
    ],
)
async def test_borrowed_session_uses_current_scalar_auth_state_without_flushing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'auth.sqlite3').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, other_id = uuid.uuid4(), uuid.uuid4()
    session_owner = other_id if case == "wrong-owner" else user_id
    expires = datetime.now(UTC) + timedelta(hours=1)
    if case == "expired-session":
        expires = datetime.now(UTC) - timedelta(hours=1)
    revoked = datetime.now(UTC) if case == "revoked-session" else None
    user_epoch = 1 if case == "mfa-epoch" else 0
    is_active = case != "inactive-user"
    redis = SimpleNamespace(exists=AsyncMock(return_value=case == "tombstone"))
    if case == "revocation-unavailable":
        redis.exists.side_effect = OSError("revocation unavailable")
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=redis)
    )

    try:
        async with engine.begin() as connection:
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
                text(
                    "INSERT INTO users (id, is_active, mfa_epoch) VALUES (:id, :active, :epoch)"
                ),
                {"id": user_id.hex, "active": is_active, "epoch": user_epoch},
            )
            await connection.execute(
                text(
                    "INSERT INTO active_sessions (user_id, jti, expires_at, revoked_at, mfa_epoch) VALUES (:id, :jti, :expires, :revoked, 0)"
                ),
                {
                    "id": session_owner.hex,
                    "jti": "session",
                    "expires": expires.isoformat(),
                    "revoked": revoked.isoformat() if revoked else None,
                },
            )

        async with sessions() as session:
            # Deliberately stale ORM identity must not override the database row.
            stale = User(id=user_id, is_active=True, mfa_epoch=0)
            make_transient_to_detached(stale)
            cached = await session.merge(stale, load=False)
            stale_session = ActiveSession(
                id=uuid.uuid4(),
                user_id=user_id,
                jti="session",
                revoked_at=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                mfa_epoch=0,
            )
            make_transient_to_detached(stale_session)
            cached_session = await session.merge(stale_session, load=False)
            pending = User(id=uuid.uuid4(), is_active=True, mfa_epoch=0)
            session.add(pending)
            await session.execute(text("SELECT 1"))
            if case == "database-unavailable":
                monkeypatch.setattr(
                    session,
                    "execute",
                    AsyncMock(side_effect=SQLAlchemyError("unavailable")),
                )

            validator = getattr(auth, "validate_borrowed_ws_session", None)
            assert callable(validator), "borrowed session auth validator is missing"
            with (
                patch.object(session, "commit", wraps=session.commit) as commit,
                patch.object(session, "rollback", wraps=session.rollback) as rollback,
                patch.object(session, "close", wraps=session.close) as close,
            ):
                usable = await validator(
                    user_id,
                    "missing" if case == "missing-session" else "session",
                    session,
                    asyncio.Lock(),
                )
                commit.assert_not_awaited()
                rollback.assert_not_awaited()
                close.assert_not_awaited()

            assert usable is (case == "valid")
            assert session.in_transaction()
            assert pending in session.new
            assert cached.is_active is True
            assert cached.mfa_epoch == 0
            assert cached_session.revoked_at is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_borrowed_db_lock_is_released_before_socket_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'fanout.sqlite3').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    first_id, second_id, chat_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first, second = AsyncMock(), AsyncMock()
    first_started, second_sent, release_first = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )

    async def hold_first(_payload):
        first_started.set()
        await release_first.wait()

    async def send_second(_payload):
        await first_started.wait()
        second_sent.set()

    first.send_json.side_effect = hold_first
    second.send_json.side_effect = send_second
    monkeypatch.setattr(
        auth,
        "get_revocation_redis_client",
        AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=0))),
    )
    monkeypatch.setattr(broker, "publish_core", AsyncMock())
    manager = connection_manager.ConnectionManager()
    monkeypatch.setattr(
        manager, "_get_chat_participants", AsyncMock(return_value=[first_id, second_id])
    )

    try:
        async with engine.begin() as connection:
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
            for user_id, jti in ((first_id, "first"), (second_id, "second")):
                await connection.execute(
                    text(
                        "INSERT INTO users (id, is_active, mfa_epoch) VALUES (:id, 1, 0)"
                    ),
                    {"id": user_id.hex},
                )
                await connection.execute(
                    text(
                        "INSERT INTO active_sessions (user_id, jti, expires_at, revoked_at, mfa_epoch) VALUES (:id, :jti, :expires, NULL, 0)"
                    ),
                    {
                        "id": user_id.hex,
                        "jti": jti,
                        "expires": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    },
                )
        await manager.connect(first, first_id, session_jti="first")
        await manager.connect(second, second_id, session_jti="second")
        async with sessions() as session:
            task = asyncio.create_task(
                manager.broadcast_to_chat(
                    chat_id, {"type": "message"}, db_session=session
                )
            )
            try:
                await asyncio.wait_for(second_sent.wait(), timeout=2)
            finally:
                release_first.set()
                await asyncio.wait_for(task, timeout=2)
        first.send_json.assert_awaited_once()
        second.send_json.assert_awaited_once()
    finally:
        await engine.dispose()
