"""Owned PostgreSQL proof for borrowed WebSocket authorization sessions.

Run only against the dedicated disposable database and restricted role
created by the private launcher after the resource coordinator grants a slot.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import make_transient_to_detached

from app.api.ws import auth, connection_manager, presence
from app.core.nats_broker import broker
from app.core.tenant import set_current_tenant, tenant_id_ctx
from app.models import ActiveSession, User
from app.models.chat import chat_participants
from app.repositories.chat_repository import ChatRepository
from app.services.chat import command_service

_RUN = os.getenv("AUD363_WS_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Requires owned AUD-363 disposable PostgreSQL"),
]


@pytest.fixture
async def owned_postgres() -> AsyncIterator[SimpleNamespace]:
    raw_url = os.environ.get("AUD363_WS_DISPOSABLE_PG_URL", "")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host != "127.0.0.1"
        or url.port is None
        or url.port == 5432
        or url.database != "audit_ws_borrowed"
        or url.username != "audit_ws_reader"
    ):
        pytest.fail("AUD-363 disposable PostgreSQL identity does not match")

    schema = "aud363_ws_" + uuid.uuid4().hex
    bootstrap = create_async_engine(url, pool_size=1, max_overflow=0)
    engine = None
    try:
        async with bootstrap.begin() as connection:
            role = (
                await connection.execute(
                    text("SELECT current_database(), current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
            ).one()
            assert tuple(role) == ("audit_ws_borrowed", "audit_ws_reader", False, False)
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        engine = create_async_engine(
            url,
            pool_size=3,
            max_overflow=1,
            pool_timeout=2,
            connect_args={"server_settings": {"search_path": schema}},
        )
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        actor_id, recipient_id, foreign_id, chat_id = (uuid.uuid4() for _ in range(4))
        expiry = datetime.now(UTC) + timedelta(hours=1)
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE users (id UUID PRIMARY KEY, is_active BOOLEAN NOT NULL, mfa_epoch INTEGER NOT NULL, tenant_id UUID NOT NULL)"))
            await connection.execute(text("CREATE TABLE active_sessions (user_id UUID NOT NULL, jti TEXT UNIQUE NOT NULL, expires_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ, mfa_epoch INTEGER NOT NULL)"))
            await connection.execute(text("CREATE TABLE chat_participants (chat_id UUID NOT NULL, user_id UUID NOT NULL)"))
            await connection.execute(
                text("INSERT INTO users (id, is_active, mfa_epoch, tenant_id) VALUES (:id, true, 0, :tenant)"),
                [
                    {"id": actor_id, "tenant": tenant_a},
                    {"id": recipient_id, "tenant": tenant_a},
                    {"id": foreign_id, "tenant": tenant_b},
                ],
            )
            await connection.execute(
                text("INSERT INTO active_sessions (user_id, jti, expires_at, revoked_at, mfa_epoch) VALUES (:id, :jti, :expiry, NULL, 0)"),
                [
                    {"id": recipient_id, "jti": "local-session", "expiry": expiry},
                    {"id": foreign_id, "jti": "foreign-session", "expiry": expiry},
                ],
            )
            await connection.execute(
                chat_participants.insert(),
                [{"chat_id": chat_id, "user_id": user_id} for user_id in (actor_id, recipient_id)],
            )
            await connection.execute(text("ALTER TABLE users ENABLE ROW LEVEL SECURITY"))
            await connection.execute(text("ALTER TABLE users FORCE ROW LEVEL SECURITY"))
            await connection.execute(text("CREATE POLICY tenant_scope ON users USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"))

        yield SimpleNamespace(
            engine=engine,
            sessions=async_sessionmaker(engine, expire_on_commit=False),
            tenant_a=tenant_a,
            tenant_b=tenant_b,
            actor_id=actor_id,
            recipient_id=recipient_id,
            foreign_id=foreign_id,
            chat_id=chat_id,
        )
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with bootstrap.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            await bootstrap.dispose()


def _revocation_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=0)))
    )


@pytest.mark.asyncio
async def test_read_committed_revalidation_respects_rls_and_preserves_dirty_uow(
    owned_postgres: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _revocation_store(monkeypatch)
    token = set_current_tenant(owned_postgres.tenant_a)
    try:
        async with owned_postgres.sessions() as session:
            assert await session.scalar(text("SELECT row_security_active('users')")) is True
            stale = User(id=owned_postgres.recipient_id, is_active=True, mfa_epoch=0)
            make_transient_to_detached(stale)
            cached_user = await session.merge(stale, load=False)
            stale_session = ActiveSession(
                id=uuid.uuid4(), user_id=owned_postgres.recipient_id, jti="local-session",
                expires_at=datetime.now(UTC) + timedelta(hours=1), revoked_at=None, mfa_epoch=0,
            )
            make_transient_to_detached(stale_session)
            cached_session = await session.merge(stale_session, load=False)
            pending = User(id=uuid.uuid4(), is_active=True, mfa_epoch=0)
            session.add(pending)
            with (
                patch.object(session, "commit", wraps=session.commit) as commit,
                patch.object(session, "rollback", wraps=session.rollback) as rollback,
                patch.object(session, "close", wraps=session.close) as close,
            ):
                assert await auth.validate_borrowed_ws_session(
                    owned_postgres.recipient_id, "local-session", session, asyncio.Lock()
                )
                assert not await auth.validate_borrowed_ws_session(
                    owned_postgres.foreign_id, "foreign-session", session, asyncio.Lock()
                )
                async with owned_postgres.sessions.begin() as writer:
                    await writer.execute(
                        text("UPDATE active_sessions SET revoked_at = now() WHERE jti = 'local-session'")
                    )
                assert not await auth.validate_borrowed_ws_session(
                    owned_postgres.recipient_id, "local-session", session, asyncio.Lock()
                )
                commit.assert_not_awaited()
                rollback.assert_not_awaited()
                close.assert_not_awaited()
            assert session.in_transaction()
            assert pending in session.new
            assert cached_user.is_active is True
            assert cached_session.revoked_at is None
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_repeatable_read_cannot_authorize_or_publish(
    owned_postgres: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _revocation_store(monkeypatch)
    publisher = AsyncMock()
    monkeypatch.setattr(broker, "publish_core", publisher)
    repeatable = owned_postgres.engine.execution_options(isolation_level="REPEATABLE READ")
    sessions = async_sessionmaker(repeatable, expire_on_commit=False)
    manager = connection_manager.ConnectionManager()
    token = set_current_tenant(owned_postgres.tenant_a)
    try:
        async with sessions() as session:
            assert not await auth.validate_borrowed_ws_session(
                owned_postgres.recipient_id, "local-session", session, asyncio.Lock()
            )
            with pytest.raises(RuntimeError, match="READ COMMITTED"):
                await manager.broadcast_to_chat(
                    owned_postgres.chat_id, {"type": "typing"}, db_session=session
                )
        publisher.assert_not_awaited()
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_typing_and_presence_progress_under_saturated_pool(
    owned_postgres: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _revocation_store(monkeypatch)
    sessions = owned_postgres.sessions
    monkeypatch.setattr(presence, "async_session", sessions)
    publisher = AsyncMock()
    monkeypatch.setattr(broker, "publish_core", publisher)
    manager = connection_manager.ConnectionManager(session_factory=sessions)
    monkeypatch.setattr(command_service, "ws_manager", manager)
    websocket = AsyncMock()
    await manager.connect(websocket, owned_postgres.recipient_id, session_jti="local-session")
    ready, all_checked = 0, asyncio.Event()

    class CheckedRepository(ChatRepository):
        async def check_participant(self, chat_id, user_id):
            nonlocal ready
            result = await super().check_participant(chat_id, user_id)
            ready += 1
            if ready == 4:
                all_checked.set()
            await all_checked.wait()
            return result

    async def fresh_session_validator(user_id, jti):
        # Presence uses the ordinary fresh-session path; keep the real scalar
        # validator and a real second pool checkout without requiring unrelated
        # ORM columns in this isolated schema.
        async with sessions() as session:
            valid = await auth.validate_borrowed_ws_session(user_id, jti, session, asyncio.Lock())
        return (SimpleNamespace(id=uuid.UUID(user_id)) if valid else None, jti)

    monkeypatch.setattr(connection_manager, "_resolve_user_from_ids", fresh_session_validator)
    user = SimpleNamespace(id=owned_postgres.actor_id, profile=None, email="actor@example.test")
    token = set_current_tenant(owned_postgres.tenant_a)
    try:
        async def issue_typing():
            async with sessions() as session:
                service = command_service.ChatMaintenanceService(
                    SimpleNamespace(chats=CheckedRepository(session), session=session), None
                )
                await service.broadcast_typing(owned_postgres.chat_id, user, "en")

        typing = [asyncio.create_task(issue_typing()) for _ in range(4)]
        await asyncio.wait_for(all_checked.wait(), timeout=5)
        presence_task = asyncio.create_task(
            manager.broadcast_presence(
                owned_postgres.actor_id, True, datetime.now(UTC), source="ping", force=True, publish=False
            )
        )
        await asyncio.wait_for(asyncio.gather(*typing, presence_task), timeout=10)
        assert publisher.await_count == 4
        assert websocket.send_json.await_count == 5
    finally:
        tenant_id_ctx.reset(token)
