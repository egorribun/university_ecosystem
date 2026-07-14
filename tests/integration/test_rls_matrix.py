"""Integration tests verifying the Row-Level Security (RLS) policy matrix on the messages table.

This test inspects the database schema metadata, verifies PostgreSQL RLS status,
and asserts SELECT, INSERT, UPDATE, and DELETE operations across student,
teacher, admin, and anonymous roles under participant and non-participant scenarios.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
_PG_URL = os.getenv("DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN and _IS_PG),
        reason="Set RUN_INTEGRATION_TESTS=1 and DATABASE_URL=postgresql+asyncpg://... to run RLS matrix tests",
    ),
]


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_async_engine(_PG_URL, echo=False, future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_rls_role(pg_engine):
    async with pg_engine.connect() as conn:
        await conn.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rls_matrix_user') THEN
                    CREATE ROLE rls_matrix_user WITH LOGIN PASSWORD 'matrix_pass'; -- pragma: allowlist secret
                END IF;
            END
            $$;
        """)
        )
        await conn.execute(
            text(
                "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO rls_matrix_user"
            )
        )
        await conn.execute(
            text(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO rls_matrix_user"
            )
        )
        await conn.commit()


@pytest.fixture(scope="module")
def non_superuser_engine():
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(_PG_URL)
    netloc = f"rls_matrix_user:matrix_pass@{parsed.hostname}:{parsed.port}"
    test_url = urlunparse(parsed._replace(netloc=netloc))
    engine = create_async_engine(test_url, echo=False, future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest_asyncio.fixture
async def pg_session(non_superuser_engine) -> AsyncSession:
    async_session = sessionmaker(
        non_superuser_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def setup_matrix_users_and_chats(pg_session: AsyncSession):
    """Seed users with student, teacher, and admin roles, and create chats."""
    roles = ["student", "teacher", "admin"]
    users = {}

    # 1. Create a user of each role
    for role in roles:
        uid = str(uuid.uuid4())
        email = f"rls_{role}@test.com"
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
        users[role] = uid

    # 2. Create Chat A (contains student, teacher, admin as participants)
    chat_a_id = str(uuid.uuid4())
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": chat_a_id},
    )
    for role in roles:
        await pg_session.execute(
            text(
                "INSERT INTO chat_participants (chat_id, user_id) VALUES (:chat_id, :user_id)"
            ),
            {"chat_id": chat_a_id, "user_id": users[role]},
        )

    # 3. Create Chat B (empty / no participants from our main users)
    chat_b_id = str(uuid.uuid4())
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at) VALUES (:id, NOW(), NOW())"
        ),
        {"id": chat_b_id},
    )

    return users, chat_a_id, chat_b_id


@pytest.mark.asyncio
async def test_postgres_rls_enabled_on_messages(pg_session: AsyncSession):
    """Verify that PostgreSQL Row Level Security is active on the messages table."""
    result = await pg_session.execute(
        text("SELECT relrowsecurity FROM pg_class WHERE relname = 'messages'")
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is True, "RLS must be enabled on the messages table"


@pytest.mark.asyncio
async def test_rls_matrix_read_write(
    pg_session: AsyncSession,
    setup_matrix_users_and_chats,
):
    """Verify CRUD matrix for student, teacher, and admin roles."""
    users, chat_a_id, chat_b_id = setup_matrix_users_and_chats

    # Seed a message in Chat A and Chat B via Superuser bypass / raw insert
    msg_a_id = str(uuid.uuid4())
    msg_b_id = str(uuid.uuid4())

    # Switch RLS to student to insert in Chat A (since student is participant)
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["student"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'hello A', NOW(), false)"
        ),
        {"id": msg_a_id, "chat_id": chat_a_id, "sender": users["student"]},
    )

    # Temporary switch to superuser or bypass RLS to write to Chat B
    # Since pg_session uses non-superuser 'rls_matrix_user', we set config to a dummy participant
    # but wait! Chat B has no participants. Let's temporarily add student to Chat B, insert, and remove.
    await pg_session.execute(
        text(
            "INSERT INTO chat_participants (chat_id, user_id) VALUES (:chat_id, :user_id)"
        ),
        {"chat_id": chat_b_id, "user_id": users["student"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'hello B', NOW(), false)"
        ),
        {"id": msg_b_id, "chat_id": chat_b_id, "sender": users["student"]},
    )
    await pg_session.execute(
        text(
            "DELETE FROM chat_participants WHERE chat_id = :chat_id AND user_id = :user_id"
        ),
        {"chat_id": chat_b_id, "user_id": users["student"]},
    )

    # Test Matrix:
    # 1. Participants (student, teacher, admin) must read msg_a, but NOT msg_b
    for role in ["student", "teacher", "admin"]:
        await pg_session.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": users[role]},
        )

        # Read msg_a (Participant) -> SUCCESS
        res_a = await pg_session.execute(
            text("SELECT id FROM messages WHERE id = :id"), {"id": msg_a_id}
        )
        assert res_a.fetchone() is not None, (
            f"Role {role} (participant) must read msg_a"
        )

        # Read msg_b (Non-participant) -> SILENT EMPTY
        res_b = await pg_session.execute(
            text("SELECT id FROM messages WHERE id = :id"), {"id": msg_b_id}
        )
        assert res_b.fetchone() is None, (
            f"Role {role} (non-participant) must not read msg_b"
        )

        # Write to Chat A (Participant) -> SUCCESS
        new_msg_id = str(uuid.uuid4())
        await pg_session.execute(
            text(
                "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
                "VALUES (:id, :chat_id, :sender, 'ping', NOW(), false)"
            ),
            {"id": new_msg_id, "chat_id": chat_a_id, "sender": users[role]},
        )

        # Write to Chat B (Non-participant) -> FAILURE
        bad_msg_id = str(uuid.uuid4())
        with pytest.raises(DBAPIError):
            await pg_session.execute(
                text(
                    "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
                    "VALUES (:id, :chat_id, :sender, 'ping-bad', NOW(), false)"
                ),
                {"id": bad_msg_id, "chat_id": chat_b_id, "sender": users[role]},
            )
            # Flush is required to trigger constraint/RLS violation check in DB
            await pg_session.flush()

    # 2. Anonymous / Unauthenticated context -> cannot read or write anything
    await pg_session.execute(text("SELECT set_config('app.current_user_id', '', true)"))

    # Read A -> Empty
    res_anon_a = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_a_id}
    )
    assert res_anon_a.fetchone() is None

    # Write A -> Fail
    with pytest.raises(DBAPIError):
        await pg_session.execute(
            text(
                "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
                "VALUES (:id, :chat_id, :sender, 'anon msg', NOW(), false)"
            ),
            {"id": str(uuid.uuid4()), "chat_id": chat_a_id, "sender": users["student"]},
        )
        await pg_session.flush()


@pytest.mark.asyncio
async def test_rls_matrix_update_delete(
    pg_session: AsyncSession,
    setup_matrix_users_and_chats,
):
    """Verify UPDATE and DELETE boundaries for participant and owner roles."""
    users, chat_a_id, _chat_b_id = setup_matrix_users_and_chats

    # Seed messages
    msg_student_id = str(uuid.uuid4())
    msg_teacher_id = str(uuid.uuid4())

    # Write student's message in Chat A
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["student"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'student message', NOW(), false)"
        ),
        {"id": msg_student_id, "chat_id": chat_a_id, "sender": users["student"]},
    )

    # Write teacher's message in Chat A
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["teacher"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status) "
            "VALUES (:id, :chat_id, :sender, 'teacher message', NOW(), false)"
        ),
        {"id": msg_teacher_id, "chat_id": chat_a_id, "sender": users["teacher"]},
    )

    # 1. Student edits/deletes their OWN message -> SUCCESS
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["student"]},
    )
    await pg_session.execute(
        text("UPDATE messages SET content = 'student edited' WHERE id = :id"),
        {"id": msg_student_id},
    )
    res_update = await pg_session.execute(
        text("SELECT content FROM messages WHERE id = :id"), {"id": msg_student_id}
    )
    assert res_update.scalar() == "student edited"

    await pg_session.execute(
        text("DELETE FROM messages WHERE id = :id"), {"id": msg_student_id}
    )
    res_delete = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_student_id}
    )
    assert res_delete.fetchone() is None

    # 2. Student attempts to edit teacher's message -> FAILURE (silent no-op due to RLS filter on update/delete)
    # Note: RLS makes the row invisible to UPDATE/DELETE, so the statement runs but affects 0 rows.
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["student"]},
    )
    res_up_other = await pg_session.execute(
        text("UPDATE messages SET content = 'hacked' WHERE id = :id"),
        {"id": msg_teacher_id},
    )
    assert res_up_other.rowcount == 0, (
        "Student must not be able to update teacher's message"
    )

    res_del_other = await pg_session.execute(
        text("DELETE FROM messages WHERE id = :id"), {"id": msg_teacher_id}
    )
    assert res_del_other.rowcount == 0, (
        "Student must not be able to delete teacher's message"
    )
