"""Real PostgreSQL schema, RLS and lifecycle contracts for chat-send receipts."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import database
from tests.test_aud262_receipt_migration import _load_migration

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_COMPLETED = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_TABLE = "chat_send_receipts"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest_asyncio.fixture
async def receipt_schema(prepare_database: None) -> AsyncIterator[SimpleNamespace]:
    """Roll back every schema, role and row; never change shared fixture policies."""
    if (
        database.engine.dialect.name != "postgresql"
        or database.engine.dialect.driver != "asyncpg"
    ):
        pytest.fail("Receipt schema contracts require real PostgreSQL via asyncpg")
    migration = _load_migration()
    schema = f"aud262_receipts_{uuid4().hex}"
    role = f"aud262_receipts_{uuid4().hex}"
    owner, peer, outsider, chat, second_chat, message, tenant = (
        uuid4() for _ in range(7)
    )
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(sa.schema.CreateSchema(schema))
            await connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(
                sa.text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
            )
            await connection.execute(
                sa.text("CREATE TABLE users (id UUID PRIMARY KEY)")
            )
            await connection.execute(
                sa.text("CREATE TABLE chats (id UUID PRIMARY KEY, tenant_id UUID)")
            )
            await connection.execute(
                sa.text(
                    "CREATE TABLE messages "
                    "(id UUID PRIMARY KEY, "
                    "chat_id UUID REFERENCES chats(id) ON DELETE CASCADE)"
                )
            )
            await connection.execute(
                sa.text(
                    "CREATE TABLE chat_participants ("
                    "chat_id UUID REFERENCES chats(id) ON DELETE CASCADE, "
                    "user_id UUID REFERENCES users(id) ON DELETE CASCADE, "
                    "PRIMARY KEY (chat_id, user_id))"
                )
            )
            for user_id in (owner, peer, outsider):
                await connection.execute(
                    sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id}
                )
            for chat_id in (chat, second_chat):
                await connection.execute(
                    sa.text("INSERT INTO chats (id) VALUES (:id)"), {"id": chat_id}
                )
            for chat_id, user_id in ((chat, owner), (chat, peer), (second_chat, owner)):
                await connection.execute(
                    sa.text(
                        "INSERT INTO chat_participants (chat_id, user_id) "
                        "VALUES (:chat, :user)"
                    ),
                    {"chat": chat_id, "user": user_id},
                )
            await connection.execute(
                sa.text("INSERT INTO messages (id, chat_id) VALUES (:id, :chat)"),
                {"id": message, "chat": chat},
            )

            def upgrade(sync_connection: sa.Connection) -> None:
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()

            await connection.run_sync(upgrade)
            # Match the existing parent-chat tenant policy. The receipt policy
            # must consult visible parent rows rather than bypass this boundary.
            for statement in (
                "ALTER TABLE chats ENABLE ROW LEVEL SECURITY",
                "ALTER TABLE chats FORCE ROW LEVEL SECURITY",
                "CREATE POLICY default_permissive_policy ON chats AS PERMISSIVE "
                "USING (true) WITH CHECK (true)",
                "CREATE POLICY tenant_isolation_policy ON chats AS RESTRICTIVE "
                "USING (current_setting('app.bypass_rls', true) = 'on' "
                "OR tenant_id IS NULL "
                "OR tenant_id = "
                "NULLIF(current_setting('app.current_tenant', true), '')::uuid)",
                f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{role}"',
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f'IN SCHEMA "{schema}" TO "{role}"',
                f'ALTER TABLE chat_send_receipts OWNER TO "{role}"',
            ):
                await connection.execute(sa.text(statement))
            yield SimpleNamespace(
                connection=connection,
                schema=schema,
                role=role,
                migration=migration,
                owner=owner,
                peer=peer,
                outsider=outsider,
                chat=chat,
                second_chat=second_chat,
                message=message,
                tenant=tenant,
            )
        finally:
            await transaction.rollback()


async def _identity(state: SimpleNamespace, user_id: UUID | str) -> None:
    connection = state.connection
    await connection.execute(sa.text(f'SET LOCAL ROLE "{state.role}"'))
    bypass = await connection.scalar(
        sa.text(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    )
    assert bypass is False
    await connection.execute(
        sa.text("SELECT set_config('app.current_user_id', :user, true)"),
        {"user": str(user_id)},
    )
    await connection.execute(
        sa.text("SELECT set_config('app.bypass_rls', 'off', true)")
    )


async def _insert(
    state: SimpleNamespace,
    *,
    user_id: UUID | None = None,
    chat_id: UUID | None = None,
    message_id: UUID | None = None,
    digest: str = _DIGEST,
    completed_at: datetime = _COMPLETED,
    expires_at: datetime = _COMPLETED + timedelta(hours=24),
) -> UUID:
    receipt_id = uuid4()
    await state.connection.execute(
        sa.text(
            "INSERT INTO chat_send_receipts "
            "(id, chat_id, user_id, key_digest, message_id, completed_at, expires_at) "
            "VALUES (:id, :chat, :user, :digest, :message, :completed, :expires)"
        ),
        {
            "id": receipt_id,
            "chat": state.chat if chat_id is None else chat_id,
            "user": state.owner if user_id is None else user_id,
            "digest": digest,
            "message": message_id,
            "completed": completed_at,
            "expires": expires_at,
        },
    )
    return receipt_id


async def _visible(connection: AsyncConnection) -> list[UUID]:
    rows = await connection.scalars(
        sa.text("SELECT id FROM chat_send_receipts ORDER BY id")
    )
    return list(rows.all())


async def test_receipt_upgrade_creates_exact_catalog_and_forces_owner_rls(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    connection = state.connection

    def inspect_schema(sync_connection: sa.Connection) -> None:
        inspector = sa.inspect(sync_connection)
        columns = {
            item["name"]: item
            for item in inspector.get_columns(_TABLE, schema=state.schema)
        }
        assert set(columns) == {
            "id",
            "chat_id",
            "user_id",
            "key_digest",
            "message_id",
            "completed_at",
            "expires_at",
        }
        assert {name for name, item in columns.items() if item["nullable"]} == {
            "message_id"
        }
        assert columns["key_digest"]["type"].length == 64
        assert columns["completed_at"]["type"].timezone is True
        assert columns["expires_at"]["type"].timezone is True
        assert all(item["default"] is None for item in columns.values())
        assert inspector.get_pk_constraint(_TABLE, schema=state.schema)[
            "constrained_columns"
        ] == ["id"]
        assert {
            (item["name"], tuple(item["column_names"]))
            for item in inspector.get_unique_constraints(_TABLE, schema=state.schema)
        } == {
            (
                "uq_chat_send_receipts_chat_user_key",
                ("chat_id", "user_id", "key_digest"),
            )
        }
        assert {
            (
                tuple(item["constrained_columns"]),
                item["referred_table"],
                item["options"]["ondelete"],
            )
            for item in inspector.get_foreign_keys(_TABLE, schema=state.schema)
        } == {
            (("chat_id",), "chats", "CASCADE"),
            (("user_id",), "users", "CASCADE"),
            (("message_id",), "messages", "SET NULL"),
        }
        indexes = {
            item["name"]: item["column_names"]
            for item in inspector.get_indexes(_TABLE, schema=state.schema)
        }
        assert indexes["ix_chat_send_receipts_message_id"] == ["message_id"]
        assert indexes["ix_chat_send_receipts_user_id"] == ["user_id"]
        assert indexes["ix_chat_send_receipts_expires_at"] == ["expires_at", "id"]

    await connection.run_sync(inspect_schema)
    flags = await connection.execute(
        sa.text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'chat_send_receipts'::regclass"
        )
    )
    assert flags.one() == (True, True)
    assert await connection.scalar(sa.text("SHOW lock_timeout")) == "10s"
    assert await connection.scalar(sa.text("SHOW statement_timeout")) == "1min"
    await _identity(state, state.owner)
    receipt_id = await _insert(state)
    assert await _visible(connection) == [receipt_id]
    await _identity(state, state.peer)
    assert await _visible(connection) == []


@pytest.mark.parametrize("identity", ["empty", "peer", "outsider"])
async def test_receipt_rls_hides_other_owners_and_rejects_forged_writes(
    receipt_schema: SimpleNamespace, identity: str
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    receipt_id = await _insert(state)
    denied_identity = "" if identity == "empty" else getattr(state, identity)
    await _identity(state, denied_identity)
    assert await _visible(state.connection) == []
    with pytest.raises(sa.exc.DBAPIError) as denied:
        async with state.connection.begin_nested():
            await _insert(state, digest="b" * 64)
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"
    await _identity(state, state.owner)
    assert await _visible(state.connection) == [receipt_id]


async def test_receipt_rls_revokes_owner_access_after_membership_removal(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    await _insert(state)
    await state.connection.execute(sa.text("RESET ROLE"))
    await state.connection.execute(
        sa.text(
            "DELETE FROM chat_participants WHERE chat_id = :chat AND user_id = :user"
        ),
        {"chat": state.chat, "user": state.owner},
    )
    await _identity(state, state.owner)
    assert await _visible(state.connection) == []
    with pytest.raises(sa.exc.DBAPIError) as denied:
        async with state.connection.begin_nested():
            await _insert(state, digest="b" * 64)
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"


async def test_receipt_rls_inherits_parent_chat_tenant_visibility(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await state.connection.execute(
        sa.text("UPDATE chats SET tenant_id = :tenant WHERE id = :chat"),
        {"tenant": state.tenant, "chat": state.chat},
    )
    await _identity(state, state.owner)
    await state.connection.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(state.tenant)},
    )
    receipt_id = await _insert(state)
    await state.connection.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(uuid4())},
    )
    assert await _visible(state.connection) == []
    with pytest.raises(sa.exc.DBAPIError) as denied:
        async with state.connection.begin_nested():
            await _insert(state, digest="b" * 64)
    assert getattr(denied.value.orig, "sqlstate", None) == "42501"
    await state.connection.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(state.tenant)},
    )
    assert await _visible(state.connection) == [receipt_id]


async def test_receipt_unique_scope_allows_other_chat_and_sender(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    original = await _insert(state)
    with pytest.raises(sa.exc.IntegrityError):
        async with state.connection.begin_nested():
            await _insert(state)
    other_chat = await _insert(state, chat_id=state.second_chat)
    assert set(await _visible(state.connection)) == {original, other_chat}
    await _identity(state, state.peer)
    peer_receipt = await _insert(state, user_id=state.peer)
    assert await _visible(state.connection) == [peer_receipt]


async def test_expired_receipt_has_no_global_visibility_or_implicit_deletion(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    expired = await _insert(
        state,
        completed_at=datetime(2000, 1, 1, tzinfo=UTC),
        expires_at=datetime(2000, 1, 2, tzinfo=UTC),
    )
    with pytest.raises(sa.exc.IntegrityError):
        async with state.connection.begin_nested():
            await _insert(state)
    await _identity(state, state.peer)
    assert await _visible(state.connection) == []
    deleted = await state.connection.execute(
        sa.text(
            "DELETE FROM chat_send_receipts "
            "WHERE expires_at <= clock_timestamp() RETURNING id"
        )
    )
    assert deleted.scalars().all() == []
    await _identity(state, state.owner)
    assert await _visible(state.connection) == [expired]
    deleted = await state.connection.execute(
        sa.text(
            "DELETE FROM chat_send_receipts "
            "WHERE expires_at <= clock_timestamp() RETURNING id"
        )
    )
    assert deleted.scalars().all() == [expired]
    replacement = await _insert(state)
    assert await _visible(state.connection) == [replacement]


@pytest.mark.parametrize("parent", ["messages", "users", "chats"])
async def test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker(
    receipt_schema: SimpleNamespace, parent: str
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    receipt_id = await _insert(state, message_id=state.message)
    await state.connection.execute(sa.text("RESET ROLE"))
    statement, parent_id = {
        "messages": ("DELETE FROM messages WHERE id = :id", state.message),
        "users": ("DELETE FROM users WHERE id = :id", state.owner),
        "chats": ("DELETE FROM chats WHERE id = :id", state.chat),
    }[parent]
    await state.connection.execute(sa.text(statement), {"id": parent_id})
    rows = await state.connection.execute(
        sa.text("SELECT id, message_id FROM chat_send_receipts")
    )
    assert rows.all() == ([(receipt_id, None)] if parent == "messages" else [])


async def test_receipt_upgrade_and_downgrade_refuse_without_losing_history(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    receipt_id = await _insert(state)

    def refuse(sync_connection: sa.Connection) -> None:
        with Operations.context(MigrationContext.configure(sync_connection)):
            with pytest.raises(RuntimeError, match="require manual review"):
                state.migration.upgrade()
            with pytest.raises(
                RuntimeError, match="discard committed idempotency history"
            ):
                state.migration.downgrade()

    await state.connection.run_sync(refuse)
    assert await _visible(state.connection) == [receipt_id]
