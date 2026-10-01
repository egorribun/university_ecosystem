"""Integration tests for PostgreSQL Row Level Security on the messages table.

MOD-02 (Wave 11): The ``messages`` table has RLS enabled so that
``current_setting('app.current_user_id', TRUE)`` gates which rows are
visible.  ``_set_rls_user()`` in ChatRepository issues
``SET LOCAL app.current_user_id = :uid`` scoped to the current transaction.

These tests REQUIRE a real PostgreSQL instance — RLS is a PostgreSQL feature
and cannot be tested against SQLite.  They are gated behind the
``RUN_INTEGRATION_TESTS=1`` env-var / ``integration`` pytest mark.

Run with:
    RUN_INTEGRATION_TESTS=1 DATABASE_URL=postgresql+asyncpg://... \\
        pytest tests/integration/test_rls_messages.py -v -m integration

RZ-W13-03 (audit 2026-03-17): First RLS regression tests — guards against a
future developer adding a chat endpoint without calling _set_rls_user(),
which would silently expose all messages to every authenticated user.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.events import EventBus, MessageEdited, MessageSent
from app.repositories.chat_repository import ChatRepository
from app.services import event_handlers

# ---------------------------------------------------------------------------
# Skip guard — these tests need PostgreSQL + explicit opt-in
# ---------------------------------------------------------------------------
_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
_PG_URL = os.getenv("DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN and _IS_PG),
        reason=(
            "Set RUN_INTEGRATION_TESTS=1 and DATABASE_URL=postgresql+asyncpg://... "
            "to run RLS integration tests"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine():
    """Dedicated async engine pointing at the PostgreSQL test database (superuser)."""
    engine = create_async_engine(_PG_URL, echo=False, future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_rls_role(pg_engine):
    """Create a temporary non-superuser role and grant necessary privileges for testing RLS."""
    async with pg_engine.connect() as conn:
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rls_test_user') THEN
                    CREATE ROLE rls_test_user WITH LOGIN PASSWORD 'test_pass'; -- pragma: allowlist secret
                END IF;
            END
            $$;
        """)
        )
        await conn.execute(
            text("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rls_test_user")
        )
        await conn.execute(
            text(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO rls_test_user"
            )
        )
        await conn.commit()


@pytest.fixture(scope="module")
def non_superuser_engine():
    """Dedicated async engine connecting as the non-superuser rls_test_user."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(_PG_URL)
    netloc = f"rls_test_user:test_pass@{parsed.hostname}:{parsed.port}"
    test_url = urlunparse(parsed._replace(netloc=netloc))
    engine = create_async_engine(test_url, echo=False, future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest_asyncio.fixture
async def pg_session(non_superuser_engine) -> AsyncSession:
    """Fresh async session using the non-superuser connection; rolled back after every test."""
    async_session = sessionmaker(
        non_superuser_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def admin_session(pg_engine) -> AsyncSession:
    """Fresh async session using the superuser/admin connection; rolled back after every test."""
    async_session = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def two_users_and_chat(pg_session: AsyncSession):
    """Insert two users + a shared chat they are both participants of.

    Returns (user_a_id, user_b_id, chat_id) as UUID strings.
    """

    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())

    # Insert minimal User rows (bypass the full factory to avoid DI)
    for uid, email in [(user_a_id, "rls_a@test.com"), (user_b_id, "rls_b@test.com")]:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required) "
                "VALUES (:id, :email, 'x', 'student', true, false)"
            ),
            {"id": uid, "email": email},
        )
        await pg_session.execute(
            text(
                "INSERT INTO user_profiles (user_id, full_name) VALUES (:uid, 'Test')"
            ),
            {"uid": uid},
        )

    # Insert Chat
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": chat_id},
    )

    # Add both users as participants
    for uid in (user_a_id, user_b_id):
        await pg_session.execute(
            text(
                "INSERT INTO chat_participants (chat_id, user_id) "
                "VALUES (:chat_id, :user_id)"
            ),
            {"chat_id": chat_id, "user_id": uid},
        )

    return user_a_id, user_b_id, chat_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_allows_sender_to_read_own_message(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """User A can read their own message when RLS is set to user A."""
    user_a_id, _, chat_id = two_users_and_chat
    msg_id = str(uuid.uuid4())

    # Set GUC first so the insert is allowed under RLS policy for the non-superuser
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_a_id}
    )

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'hello', NOW(), false)"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
    )

    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    row = result.fetchone()
    assert row is not None, "User A must see their own message under RLS"


@pytest.mark.asyncio
async def test_rls_blocks_non_participant_from_reading_message(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """User B cannot read user A's message in a chat B is not part of.

    This creates a *separate* chat that only user A participates in,
    then activates RLS as user B — B must see 0 rows from that chat.
    """
    user_a_id, user_b_id, _ = two_users_and_chat

    # New chat with only user_a
    solo_chat_id = str(uuid.uuid4())
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": solo_chat_id},
    )
    await pg_session.execute(
        text(
            "INSERT INTO chat_participants (chat_id, user_id) "
            "VALUES (:chat_id, :user_id)"
        ),
        {"chat_id": solo_chat_id, "user_id": user_a_id},
    )

    msg_id = str(uuid.uuid4())
    # Set GUC as user_a first so we can insert the message in user_a's chat
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_a_id}
    )

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'secret', NOW(), false)"
        ),
        {"id": msg_id, "chat_id": solo_chat_id, "sender": user_a_id},
    )

    # Activate RLS as user B (not a participant in solo_chat)
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_b_id}
    )
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    row = result.fetchone()
    assert row is None, (
        "RLS must prevent user B from reading messages in chats they don't participate in"
    )


@pytest.mark.asyncio
async def test_rls_with_null_user_id_returns_no_messages(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """Setting app.current_user_id to an empty string returns zero message rows.

    This guards the case where _set_rls_user() is called with a NULL/empty
    user_id (e.g. an anonymous or unauthenticated path that accidentally
    reaches a query touching messages).
    """
    user_a_id, _, chat_id = two_users_and_chat
    msg_id = str(uuid.uuid4())

    # Set GUC first so the insert is allowed
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_a_id}
    )

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'private', NOW(), false)"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
    )

    # Set RLS to a random non-existent UUID (simulates miscall with no participant user)
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(uuid.uuid4())},
    )
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    row = result.fetchone()
    assert row is None, (
        "RLS with non-participant current_user_id must not expose any messages"
    )


@pytest.mark.asyncio
async def test_message_edit_event_handler_sets_membership_identity_before_forced_rls_read(
    monkeypatch,
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """The durable handler reads a committed message through the forced RLS policy."""
    user_a_id, _, chat_id = two_users_and_chat
    message_id = str(uuid.uuid4())

    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_a_id},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages "
            "(id, chat_id, sender_id, content, created_at, read_status, edited_at) "
            "VALUES (:id, :chat_id, :sender, 'committed via PG', NOW(), false, NOW())"
        ),
        {"id": message_id, "chat_id": chat_id, "sender": user_a_id},
    )

    @asynccontextmanager
    async def existing_transaction():
        yield pg_session

    monkeypatch.setattr(event_handlers, "async_session", existing_transaction)
    with patch(
        "app.api.ws.connection_manager.manager.broadcast_to_chat",
        new_callable=AsyncMock,
    ) as broadcast:
        await event_handlers.handle_message_edited(
            MessageEdited(message_id=uuid.UUID(message_id), chat_id=uuid.UUID(chat_id))
        )

    broadcast.assert_awaited_once()
    assert broadcast.await_args is not None
    assert broadcast.await_args.args[1]["content"] == "committed via PG"


@pytest.mark.asyncio
async def test_message_sent_outbox_dispatch_reads_forced_rls_row_on_postgres(
    monkeypatch,
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """String UUIDs rebuilt by the outbox reach the PostgreSQL handler as UUIDs."""
    from types import SimpleNamespace

    from app.models.domain_events import StoredEvent
    from app.workers import outbox as outbox_module

    user_a_id, _, chat_id = two_users_and_chat
    message_id = str(uuid.uuid4())
    stored_event_id = uuid.uuid4()

    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_a_id},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages "
            "(id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'synthetic outbox message', NOW(), false)"
        ),
        {"id": message_id, "chat_id": chat_id, "sender": user_a_id},
    )

    @asynccontextmanager
    async def existing_transaction():
        yield pg_session

    monkeypatch.setattr(event_handlers, "async_session", existing_transaction)
    # The integration fixture owns this transaction and rolls it back. Keep the
    # handler's commit from closing that fixture-owned transaction.
    monkeypatch.setattr(pg_session, "commit", AsyncMock())

    repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(participants=[], chat_type="dm", name=None)
        ),
        get_message_by_id=AsyncMock(return_value=None),
    )
    notification_service = SimpleNamespace(notify_new_message=AsyncMock())
    monkeypatch.setattr(
        "app.repositories.chat_repository.ChatRepository", lambda _: repo
    )
    monkeypatch.setattr(
        "app.services.chat.notification_service.ChatNotificationService",
        lambda _: notification_service,
    )

    bus = EventBus()
    bus.subscribe(MessageSent.EVENT_TYPE, event_handlers.handle_message_sent)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    worker = outbox_module.OutboxWorker()
    await worker._dispatch_event(
        StoredEvent(
            id=stored_event_id,
            event_type=MessageSent.EVENT_TYPE,
            aggregate_type="chat",
            aggregate_id=chat_id,
            payload={
                "message_id": message_id,
                "chat_id": chat_id,
                "sender_id": user_a_id,
                "content_preview": "synthetic outbox message",
            },
            metadata_={},
        )
    )

    notification_service.notify_new_message.assert_awaited_once()
    args = notification_service.notify_new_message.await_args.kwargs
    assert args["message"].id == uuid.UUID(message_id)
    assert args["message"].chat_id == uuid.UUID(chat_id)


@pytest.mark.asyncio
async def test_rls_superuser_context_bypasses_policy(
    admin_session: AsyncSession,
):
    """Without SET LOCAL, a superuser connection bypasses RLS entirely.

    This is the expected and necessary behaviour for admin/migration
    operations (e.g. Alembic, background cleanup jobs).  The test documents
    and asserts this intentional bypass rather than flagging it as a bug.
    """
    user_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    # Insert user
    await admin_session.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required) "
            "VALUES (:id, 'rls_super@test.com', 'x', 'student', true, false)"
        ),
        {"id": user_id},
    )
    # Insert Chat
    await admin_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": chat_id},
    )
    # Insert Message
    await admin_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'admin-visible', NOW(), false)"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_id},
    )

    # No SET LOCAL — superuser/backend connection sees all rows
    result = await admin_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    row = result.fetchone()
    assert row is not None, (
        "Superuser context (no SET LOCAL) must bypass RLS and see all messages"
    )


@pytest.mark.asyncio
async def test_rls_scoped_to_transaction(
    pg_engine,
):
    """app.current_user_id is reset after the transaction ends (SET LOCAL).

    This verifies the GUC is truly scoped to the transaction and not
    leaked to the connection pool's next consumer.
    """
    async_session = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_user_id', 'some-user-id', true)")
            )
            result = await session.execute(
                text("SELECT current_setting('app.current_user_id', TRUE)")
            )
            assert result.scalar() == "some-user-id"
        # Transaction committed — SET LOCAL must be cleared

        # Next statement on same connection (but outside the committed txn)
        result = await session.execute(
            text("SELECT current_setting('app.current_user_id', TRUE)")
        )
        value = result.scalar()
        assert value in ("", None), (
            f"SET LOCAL must be cleared after transaction commit, got {value!r}"
        )


@pytest.mark.asyncio
async def test_rls_blocks_writing_mismatched_sender_id(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """Writing a message with a sender_id different from the RLS current_user_id must fail."""
    user_a_id, user_b_id, chat_id = two_users_and_chat
    msg_id = str(uuid.uuid4())

    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": user_b_id}
    )

    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        await pg_session.execute(
            text(
                "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
                "VALUES (:id, :chat_id, :sender, 'imposter', NOW(), false)"
            ),
            {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
        )
        await pg_session.flush()


@pytest.mark.asyncio
async def test_rls_applies_to_professors_and_admins(
    pg_session: AsyncSession,
):
    """Verifies that RLS isolation works identically for professors and admins."""
    prof_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    # Insert users with different roles
    for uid, email, role in [
        (prof_id, "rls_prof@test.com", "teacher"),
        (admin_id, "rls_admin_user@test.com", "admin"),
        (student_id, "rls_stud@test.com", "student"),
    ]:
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required) "
                "VALUES (:id, :email, 'x', :role, true, false)"
            ),
            {"id": uid, "email": email, "role": role},
        )
        await pg_session.execute(
            text(
                "INSERT INTO user_profiles (user_id, full_name) VALUES (:uid, 'Test')"
            ),
            {"uid": uid},
        )

    # Create chat with professor and admin
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": chat_id},
    )
    for uid in (prof_id, admin_id):
        await pg_session.execute(
            text(
                "INSERT INTO chat_participants (chat_id, user_id) "
                "VALUES (:chat_id, :user_id)"
            ),
            {"chat_id": chat_id, "user_id": uid},
        )

    # Professor inserts message
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": prof_id}
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'hello from professor', NOW(), false)"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": prof_id},
    )

    # 1. Professor can read it
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    assert result.fetchone() is not None

    # 2. Admin (who is a participant) can read it
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": admin_id}
    )
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    assert result.fetchone() is not None

    # 3. Student (who is NOT a participant) cannot read it
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": student_id},
    )
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    assert result.fetchone() is None


@pytest.mark.asyncio
async def test_repository_message_lookup_sets_explicit_forced_rls_identity(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """A repository lookup sets identity per call and does not inherit session state."""
    user_a_id, _, chat_id = two_users_and_chat
    message_id = str(uuid.uuid4())

    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_a_id},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'owned row', NOW(), false)"
        ),
        {"id": message_id, "chat_id": chat_id, "sender": user_a_id},
    )
    await pg_session.execute(text("SELECT set_config('app.current_user_id', '', true)"))

    repo = ChatRepository(pg_session)
    found = await repo.get_message_by_id(
        uuid.UUID(message_id),
        user_id=uuid.UUID(user_a_id),
        chat_id=uuid.UUID(chat_id),
    )
    hidden_from_non_member = await repo.get_message_by_id(
        uuid.UUID(message_id),
        user_id=uuid.uuid4(),
        chat_id=uuid.UUID(chat_id),
    )

    assert found is not None
    assert hidden_from_non_member is None


@pytest.mark.asyncio
async def test_rls_revokes_group_message_history_and_metadata_after_member_removal(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """Removing a group participant hides existing messages and their metadata."""
    user_a_id, former_member_id, chat_id = two_users_and_chat
    message_id = str(uuid.uuid4())
    attachment_id = str(uuid.uuid4())
    reaction_id = str(uuid.uuid4())
    content = "synthetic group history retained after revocation"
    attachment_url = "https://example.test/rls-revocation-proof.png"
    attachment_filename = "rls-revocation-proof.png"
    reaction_emoji = "⭐"

    # Reuse the shared-chat fixture but make this a group before adding history.
    await pg_session.execute(
        text(
            "UPDATE chats SET chat_type = 'group', name = 'RLS revocation' WHERE id = :id"
        ),
        {"id": chat_id},
    )

    # Seed the message as a current participant, with attachment and reaction
    # rows that ChatRepository.get_messages loads as message history metadata.
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": user_a_id},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, :content, NOW(), false)"
        ),
        {
            "id": message_id,
            "chat_id": chat_id,
            "sender": user_a_id,
            "content": content,
        },
    )
    await pg_session.execute(
        text(
            "INSERT INTO attachments "
            "(id, message_id, url, file_type, filename, size) "
            "VALUES (:id, :message_id, :url, 'image', :filename, 1234)"
        ),
        {
            "id": attachment_id,
            "message_id": message_id,
            "url": attachment_url,
            "filename": attachment_filename,
        },
    )
    await pg_session.execute(
        text(
            "INSERT INTO message_reactions (id, message_id, user_id, emoji) "
            "VALUES (:id, :message_id, :user_id, :emoji)"
        ),
        {
            "id": reaction_id,
            "message_id": message_id,
            "user_id": former_member_id,
            "emoji": reaction_emoji,
        },
    )

    repo = ChatRepository(pg_session)
    former_member_before, has_more, next_cursor = await repo.get_messages(
        uuid.UUID(chat_id), None, 10, user_id=uuid.UUID(former_member_id)
    )
    assert not has_more
    assert next_cursor is None
    assert len(former_member_before) == 1

    # Revoke membership while the message and both metadata rows remain intact.
    await pg_session.execute(
        text(
            "DELETE FROM chat_participants "
            "WHERE chat_id = :chat_id AND user_id = :user_id"
        ),
        {"chat_id": chat_id, "user_id": former_member_id},
    )

    former_member_after, has_more, next_cursor = await repo.get_messages(
        uuid.UUID(chat_id), None, 10, user_id=uuid.UUID(former_member_id)
    )
    assert former_member_after == []
    assert not has_more
    assert next_cursor is None
    former_member_reactors = await repo.get_reactors(
        uuid.UUID(message_id), reaction_emoji, user_id=uuid.UUID(former_member_id)
    )
    assert former_member_reactors == []

    # The remaining member can still read the exact same stored history and
    # its attachment/reaction metadata after the membership change.
    remaining_member_history, has_more, next_cursor = await repo.get_messages(
        uuid.UUID(chat_id), None, 10, user_id=uuid.UUID(user_a_id)
    )
    remaining_member_reactors = await repo.get_reactors(
        uuid.UUID(message_id), reaction_emoji, user_id=uuid.UUID(user_a_id)
    )
    assert not has_more
    assert next_cursor is None
    assert [str(reactor.id) for reactor in remaining_member_reactors] == [
        former_member_id
    ]
    for visible_history in (former_member_before, remaining_member_history):
        assert len(visible_history) == 1
        message = visible_history[0]
        assert str(message.id) == message_id
        assert message.content == content
        assert [
            (
                str(attachment.id),
                attachment.url,
                attachment.file_type,
                attachment.filename,
                attachment.size,
            )
            for attachment in message.attachments
        ] == [
            (
                attachment_id,
                attachment_url,
                "image",
                attachment_filename,
                1234,
            )
        ]
        assert [
            (str(reaction.user_id), reaction.emoji) for reaction in message.reactions
        ] == [(former_member_id, reaction_emoji)]
