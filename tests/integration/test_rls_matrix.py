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

from app.core.db.listeners import register_tenant_listeners
from app.core.tenant import get_bypass_rls, set_current_tenant, tenant_id_ctx
from tests.fixtures.rls_runtime_role import (
    RUNTIME_ROLE_FLAGS_QUERY,
    runtime_role_statements,
)

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


# Generated per run: the runtime login is built by this module, never reused.
_RUNTIME_PASSWORD = uuid.uuid4().hex + uuid.uuid4().hex


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_rls_role(pg_engine) -> None:
    """Build rls_matrix_user as NOSUPERUSER NOBYPASSRLS with production DML grants.

    The hosted integration database user is a superuser and bypasses RLS, so
    the matrix must run as this role.
    """
    async with pg_engine.connect() as conn:
        for statement in runtime_role_statements("rls_matrix_user", _RUNTIME_PASSWORD):
            await conn.exec_driver_sql(statement)
        flags = (
            await conn.execute(
                text(RUNTIME_ROLE_FLAGS_QUERY), {"role": "rls_matrix_user"}
            )
        ).one()
        assert tuple(flags) == (False, False, False), "runtime role must not bypass RLS"
        await conn.commit()


@pytest.fixture(scope="module")
def non_superuser_engine():
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(_PG_URL)
    netloc = f"rls_matrix_user:{_RUNTIME_PASSWORD}@{parsed.hostname}:{parsed.port}"
    test_url = urlunparse(parsed._replace(netloc=netloc))
    engine = create_async_engine(test_url, echo=False, future=True)
    yield engine
    engine.sync_engine.dispose()


@pytest_asyncio.fixture
async def owned_tenant_id(pg_engine):
    """Commit only a unique tenant; all dependent rows stay rollback-scoped."""
    tenant_id = str(uuid.uuid4())
    try:
        async with pg_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :slug)"),
                {"id": tenant_id, "name": "RLS fixture", "slug": f"rls-{tenant_id}"},
            )
        yield tenant_id
    finally:
        async with pg_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
            )


@pytest_asyncio.fixture
async def pg_session(non_superuser_engine, owned_tenant_id) -> AsyncSession:
    """Bind production tenant scope while retaining a rollback-only transaction."""
    register_tenant_listeners()
    token = set_current_tenant(owned_tenant_id)
    try:
        assert not get_bypass_rls()
        async_session = sessionmaker(
            non_superuser_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            async with session.begin():
                assert (
                    await session.scalar(
                        text("SELECT current_setting('app.current_tenant', TRUE)")
                    )
                    == owned_tenant_id
                )
                yield session
                await session.rollback()
    finally:
        tenant_id_ctx.reset(token)


@pytest_asyncio.fixture
async def setup_matrix_users_and_chats(pg_session: AsyncSession):
    """Seed users with student, teacher, and admin roles, and create chats."""
    roles = ["student", "teacher", "admin"]
    users = {}

    # 1. Create a user of each role
    for role in roles:
        uid = str(uuid.uuid4())
        email = f"rls_{role}_{uid}@example.test"
        await pg_session.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required, tenant_id) "
                "VALUES (:id, :email, 'x', :role, true, false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
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
            "INSERT INTO chats (id, created_at, updated_at, tenant_id) "
            "VALUES (:id, NOW(), NOW(), NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
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
            "INSERT INTO chats (id, created_at, updated_at, tenant_id) "
            "VALUES (:id, NOW(), NOW(), NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
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

    # Seed messages as a tenant-scoped participant, without privileged bypass.
    msg_a_id = str(uuid.uuid4())
    msg_b_id = str(uuid.uuid4())

    # Switch RLS to student to insert in Chat A (since student is participant)
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": users["student"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
            "VALUES (:id, :chat_id, :sender, 'hello A', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
        ),
        {"id": msg_a_id, "chat_id": chat_a_id, "sender": users["student"]},
    )

    # Positive control: the user who sent msg_a reads that row back.
    res_own = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_a_id}
    )
    assert res_own.fetchone() is not None, "sender must read its own message"

    # Temporarily join Chat B as student to seed its message, then revoke
    # membership before exercising every non-participant denial below.
    await pg_session.execute(
        text(
            "INSERT INTO chat_participants (chat_id, user_id) VALUES (:chat_id, :user_id)"
        ),
        {"chat_id": chat_b_id, "user_id": users["student"]},
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
            "VALUES (:id, :chat_id, :sender, 'hello B', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
        ),
        {"id": msg_b_id, "chat_id": chat_b_id, "sender": users["student"]},
    )
    # Positive control: while a participant, the student reads msg_b.
    res_b_member = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_b_id}
    )
    assert res_b_member.fetchone() is not None, "participant must read msg_b"
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
                "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
                "VALUES (:id, :chat_id, :sender, 'ping', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
            ),
            {"id": new_msg_id, "chat_id": chat_a_id, "sender": users[role]},
        )

        # Write to Chat B (Non-participant) -> FAILURE
        bad_msg_id = str(uuid.uuid4())
        with pytest.raises(DBAPIError, match="row-level security policy"):
            async with pg_session.begin_nested():
                await pg_session.execute(
                    text(
                        "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
                        "VALUES (:id, :chat_id, :sender, 'ping-bad', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
                    ),
                    {"id": bad_msg_id, "chat_id": chat_b_id, "sender": users[role]},
                )
                # Flush is required to trigger constraint/RLS violation check in DB
                await pg_session.flush()

    # 2. Anonymous / Unauthenticated context. The empty identity means no
    # identity: it reads zero rows and must not raise 22P02 (invalid input syntax
    # for type uuid). The NULLIF form of messages_participant_isolation makes this so.
    await pg_session.execute(text("SELECT set_config('app.current_user_id', '', true)"))

    # Read A -> zero rows, not an error
    res_anon_a = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_a_id}
    )
    assert res_anon_a.fetchone() is None

    # Write A -> Fail
    with pytest.raises(DBAPIError, match="row-level security policy"):
        async with pg_session.begin_nested():
            await pg_session.execute(
                text(
                    "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
                    "VALUES (:id, :chat_id, :sender, 'anon msg', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "chat_id": chat_a_id,
                    "sender": users["student"],
                },
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
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
            "VALUES (:id, :chat_id, :sender, 'student message', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
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
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
            "VALUES (:id, :chat_id, :sender, 'teacher message', NOW(), false, NULLIF(current_setting('app.current_tenant', TRUE), '')::uuid)"
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


@pytest.mark.asyncio
async def test_tenant_a_participant_is_denied_tenant_b_messages(
    pg_session: AsyncSession,
    setup_matrix_users_and_chats,
) -> None:
    """The tenant policy hides tenant B rows from a tenant A session, even for a participant.

    Participation alone would show a tenant B message to its participant. The
    RESTRICTIVE tenant_isolation_policy must also deny the read and the insert
    under tenant A's GUC. Tenant B is seeded inside this rolled-back transaction
    under its own tenant GUC, then the GUC is switched back to tenant A.
    """
    users, _chat_a_id, _chat_b_id = setup_matrix_users_and_chats
    student = users["student"]
    tenant_a = str(
        await pg_session.scalar(
            text("SELECT current_setting('app.current_tenant', TRUE)")
        )
    )
    tenant_b = str(uuid.uuid4())
    chat_b2 = str(uuid.uuid4())
    msg_b = str(uuid.uuid4())

    await pg_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug) VALUES (:id, 'RLS tenant B', :slug)"
        ),
        {"id": tenant_b, "slug": f"rls-b-{tenant_b}"},
    )
    # Seed tenant B under its own tenant GUC, with the student as participant.
    await pg_session.execute(
        text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": tenant_b},
    )
    await pg_session.execute(
        text(
            "INSERT INTO chats (id, created_at, updated_at, tenant_id) "
            "VALUES (:id, NOW(), NOW(), :tenant)"
        ),
        {"id": chat_b2, "tenant": tenant_b},
    )
    await pg_session.execute(
        text(
            "INSERT INTO chat_participants (chat_id, user_id) VALUES (:chat_id, :user_id)"
        ),
        {"chat_id": chat_b2, "user_id": student},
    )
    await pg_session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": student}
    )
    await pg_session.execute(
        text(
            "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
            "VALUES (:id, :chat_id, :sender, 'tenant B message', NOW(), false, :tenant)"
        ),
        {"id": msg_b, "chat_id": chat_b2, "sender": student, "tenant": tenant_b},
    )

    # Positive control: under tenant B, its participant reads the row.
    visible_in_b = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_b}
    )
    assert visible_in_b.fetchone() is not None, "tenant B participant must read msg_b"

    # Back to tenant A: the same student is a participant of chat_b2 but is denied.
    await pg_session.execute(
        text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": tenant_a},
    )
    hidden = await pg_session.execute(
        text("SELECT id FROM messages WHERE id = :id"), {"id": msg_b}
    )
    assert hidden.fetchone() is None, "tenant A must not read tenant B messages"
    count_b = await pg_session.scalar(
        text("SELECT count(*) FROM messages WHERE chat_id = :chat_id"),
        {"chat_id": chat_b2},
    )
    assert count_b == 0, "tenant A must see no tenant B rows in chat_b2"

    with pytest.raises(DBAPIError, match="row-level security policy"):
        async with pg_session.begin_nested():
            await pg_session.execute(
                text(
                    "INSERT INTO messages (id, chat_id, sender_id, content, created_at, read_status, tenant_id) "
                    "VALUES (:id, :chat_id, :sender, 'cross-tenant', NOW(), false, :tenant)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "chat_id": chat_b2,
                    "sender": student,
                    "tenant": tenant_b,
                },
            )
            await pg_session.flush()
