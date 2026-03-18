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

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

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


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """Dedicated async engine pointing at the PostgreSQL test database."""
    engine = create_async_engine(_PG_URL, echo=False, future=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine) -> AsyncSession:
    """Fresh async session; rolled back after every test for isolation."""
    async_session = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            yield session
            # The transaction is rolled back automatically when the
            # begin() context exits without commit.
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
                "INSERT INTO users (id, email, hashed_password, role, is_active) "
                "VALUES (:id, :email, 'x', 'student', true)"
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
        text("INSERT INTO chats (id, created_at) VALUES (:id, NOW())"),
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

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at) "
            "VALUES (:id, :chat_id, :sender, 'hello', NOW())"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
    )

    # Activate RLS as user A
    await pg_session.execute(
        text("SET LOCAL app.current_user_id = :uid"), {"uid": user_a_id}
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
        text("INSERT INTO chats (id, created_at) VALUES (:id, NOW())"),
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
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at) "
            "VALUES (:id, :chat_id, :sender, 'secret', NOW())"
        ),
        {"id": msg_id, "chat_id": solo_chat_id, "sender": user_a_id},
    )

    # Activate RLS as user B (not a participant in solo_chat)
    await pg_session.execute(
        text("SET LOCAL app.current_user_id = :uid"), {"uid": user_b_id}
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

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at) "
            "VALUES (:id, :chat_id, :sender, 'private', NOW())"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
    )

    # Set RLS to empty string (simulates miscall with no user)
    await pg_session.execute(text("SET LOCAL app.current_user_id = ''"))
    result = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_id}
    )
    row = result.fetchone()
    assert row is None, "RLS with empty current_user_id must not expose any messages"


@pytest.mark.asyncio
async def test_rls_superuser_context_bypasses_policy(
    pg_session: AsyncSession,
    two_users_and_chat,
):
    """Without SET LOCAL, a superuser connection bypasses RLS entirely.

    This is the expected and necessary behaviour for admin/migration
    operations (e.g. Alembic, background cleanup jobs).  The test documents
    and asserts this intentional bypass rather than flagging it as a bug.
    """
    user_a_id, _user_b_id, chat_id = two_users_and_chat
    msg_id = str(uuid.uuid4())

    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at) "
            "VALUES (:id, :chat_id, :sender, 'admin-visible', NOW())"
        ),
        {"id": msg_id, "chat_id": chat_id, "sender": user_a_id},
    )

    # No SET LOCAL — superuser/backend connection sees all rows
    result = await pg_session.execute(
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
                text("SET LOCAL app.current_user_id = 'some-user-id'")
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
