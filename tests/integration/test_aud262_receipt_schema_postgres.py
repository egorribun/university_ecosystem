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
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.fixtures import owned_baseline_postgres as owned
from tests.fixtures.baseline_migration import BASELINE_DOWNGRADE_REASON

# These three overrides and their guard are module-local, never a global plugin.
initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"
_COMPLETED = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
_DIGEST = "a" * 64
_TABLE = "chat_send_receipts"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.timeout(
        300, method="signal", func_only=False, disable_debugger_detection=True
    ),
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest_asyncio.fixture
async def receipt_schema(
    request: pytest.FixtureRequest,
) -> AsyncIterator[SimpleNamespace]:
    """Commit only on the acknowledged disposable server, never the default DB."""
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        async_url = baseline.url.set(drivername="postgresql+asyncpg", query={})
        engine = create_async_engine(
            async_url,
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
            connect_args={"timeout": 5, "command_timeout": 65},
        )
        role = f"receipt_owner_{uuid4().hex}"
        member = f"receipt_member_{uuid4().hex}"
        owner, peer, outsider, chat, second_chat, message, tenant = (
            uuid4() for _ in range(7)
        )
        try:
            async with engine.begin() as connection:
                for statement in (
                    f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS',
                    f'CREATE ROLE "{member}" NOLOGIN NOSUPERUSER NOBYPASSRLS',
                    f'GRANT ue_rls_bypass TO "{member}"',
                    f'GRANT USAGE ON SCHEMA public TO "{role}", "{member}"',
                    "GRANT SELECT ON public.chats, public.chat_participants "
                    f'TO "{role}", "{member}"',
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    f'ON public.chat_send_receipts TO "{role}", "{member}"',
                    f'ALTER TABLE public.chat_send_receipts OWNER TO "{role}"',
                ):
                    await connection.execute(sa.text(statement))
                await connection.execute(
                    sa.text(
                        "INSERT INTO tenants (id, name, slug) "
                        "VALUES (:id, :name, :slug)"
                    ),
                    {"id": tenant, "name": "Receipt contract", "slug": uuid4().hex},
                )
                for user_id in (owner, peer, outsider):
                    await connection.execute(
                        sa.text(
                            "INSERT INTO users "
                            "(id, email, hashed_password, tenant_id) "
                            "VALUES (:id, :email, :credential, :tenant)"
                        ),
                        {
                            "id": user_id,
                            "email": f"{user_id}@example.invalid",
                            # Deliberately unusable, generated non-authentication seed.
                            "credential": f"!{uuid4()}",
                            "tenant": tenant,
                        },
                    )
                for chat_id in (chat, second_chat):
                    await connection.execute(
                        sa.text(
                            "INSERT INTO chats (id, tenant_id) VALUES (:id, :tenant)"
                        ),
                        {"id": chat_id, "tenant": tenant},
                    )
                for chat_id, user_id in (
                    (chat, owner),
                    (chat, peer),
                    (second_chat, owner),
                ):
                    await connection.execute(
                        sa.text(
                            "INSERT INTO chat_participants (chat_id, user_id) "
                            "VALUES (:chat, :user)"
                        ),
                        {"chat": chat_id, "user": user_id},
                    )
                await connection.execute(
                    sa.text(
                        "INSERT INTO messages "
                        "(id, content, sender_id, chat_id, tenant_id) "
                        "VALUES (:id, :content, :sender, :chat, :tenant)"
                    ),
                    {
                        "id": message,
                        "content": "Receipt contract",
                        "sender": owner,
                        "chat": chat,
                        "tenant": tenant,
                    },
                )
            async with engine.connect() as connection:
                await connection.begin()
                try:
                    yield SimpleNamespace(
                        connection=connection,
                        engine=engine,
                        schema="public",
                        role=role,
                        member=member,
                        migration=baseline.migration,
                        transaction_timeouts=baseline.transaction_timeouts,
                        owner=owner,
                        peer=peer,
                        outsider=outsider,
                        chat=chat,
                        second_chat=second_chat,
                        message=message,
                        tenant=tenant,
                    )
                finally:
                    if connection.in_transaction():
                        await connection.rollback()
        finally:
            await engine.dispose()


async def _identity(state: SimpleNamespace, user_id: UUID | str) -> None:
    connection = state.connection
    await connection.execute(sa.text(f'SET LOCAL ROLE "{state.role}"'))
    assert await connection.scalar(sa.text("SELECT current_user")) == state.role
    bypass = await connection.scalar(
        sa.text(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    )
    assert bypass is False
    assert (
        await connection.scalar(
            sa.text("SELECT pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER')")
        )
        is False
    )
    await connection.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(state.tenant)},
    )
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
            "SELECT relrowsecurity, relforcerowsecurity, "
            "pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid = 'chat_send_receipts'::regclass"
        )
    )
    assert flags.one() == (True, True, state.role)
    # These are observed while actual baseline.upgrade() is executing. SET
    # LOCAL does not survive commit; server defaults independently bound clients.
    assert state.transaction_timeouts == ("10s", "1min")
    assert await connection.scalar(sa.text("SHOW lock_timeout")) == "10s"
    assert await connection.scalar(sa.text("SHOW statement_timeout")) == "1min"
    await _identity(state, state.owner)
    receipt_id = await _insert(state)
    assert await _visible(connection) == [receipt_id]
    await _identity(state, state.peer)
    assert await _visible(connection) == []
    await connection.execute(sa.text("RESET ROLE"))
    flags = await connection.execute(
        sa.text(
            "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles "
            "WHERE rolname = 'ue_rls_bypass'"
        )
    )
    assert flags.one() == (False, False, False)
    await connection.execute(sa.text(f'SET LOCAL ROLE "{state.member}"'))
    assert await connection.scalar(sa.text("SELECT current_user")) == state.member
    assert (
        await connection.scalar(
            sa.text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        )
        is False
    )
    assert (
        await connection.scalar(
            sa.text("SELECT pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER')")
        )
        is True
    )
    await connection.execute(
        sa.text("SELECT set_config('app.current_user_id', :user, true)"),
        {"user": str(state.owner)},
    )
    await connection.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant, true)"),
        {"tenant": str(uuid4())},
    )
    # Membership, not a forged GUC or native BYPASSRLS, bypasses the parent
    # tenant boundary. The receipt's owner/participant policy still applies.
    assert await _visible(connection) == [receipt_id]


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
    assert (
        await state.connection.scalar(
            sa.text("SELECT count(*) FROM chats WHERE tenant_id IS NULL")
        )
        == 0
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
    await state.connection.execute(
        sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
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


async def test_receipt_baseline_downgrade_refuses_without_losing_committed_history(
    receipt_schema: SimpleNamespace,
) -> None:
    state = receipt_schema
    await _identity(state, state.owner)
    receipt_id = await _insert(state)
    await state.connection.commit()

    async def snapshot(connection: AsyncConnection) -> tuple[object, object]:
        def catalog(sync_connection: sa.Connection) -> object:
            inspector = sa.inspect(sync_connection)
            return (
                inspector.get_columns(_TABLE, schema="public"),
                inspector.get_pk_constraint(_TABLE, schema="public"),
                inspector.get_unique_constraints(_TABLE, schema="public"),
                inspector.get_foreign_keys(_TABLE, schema="public"),
                inspector.get_indexes(_TABLE, schema="public"),
            )

        rows = await connection.execute(
            sa.text("SELECT * FROM chat_send_receipts ORDER BY id")
        )
        return tuple(rows.all()), repr(await connection.run_sync(catalog))

    async with state.engine.connect() as observer:
        await observer.begin()
        observed = SimpleNamespace(**vars(state))
        observed.connection = observer
        await _identity(observed, state.owner)
        assert await _visible(observer) == [receipt_id]
        before = await snapshot(observer)

        def refuse(sync_connection: sa.Connection) -> None:
            statements: list[str] = []

            def record(
                _connection, _cursor, statement, _parameters, _context, _many
            ) -> None:
                statements.append(statement)

            sa.event.listen(sync_connection, "before_cursor_execute", record)
            try:
                with Operations.context(MigrationContext.configure(sync_connection)):
                    with pytest.raises(RuntimeError) as refused:
                        state.migration.downgrade()
                assert str(refused.value) == BASELINE_DOWNGRADE_REASON
            finally:
                sa.event.remove(sync_connection, "before_cursor_execute", record)
            assert statements == []

        await observer.run_sync(refuse)
        assert await _visible(observer) == [receipt_id]
        assert await snapshot(observer) == before
        await observer.rollback()

    # A second fresh transaction observes the same committed row after refusal.
    async with state.engine.connect() as observer:
        observed.connection = observer
        await _identity(observed, state.owner)
        assert await _visible(observer) == [receipt_id]
        assert await snapshot(observer) == before
        await observer.rollback()


async def test_receipt_owned_fixture_never_uses_default_database(
    request: pytest.FixtureRequest,
) -> None:
    """Subprocess controls execute the real autouse graph without starting Docker."""
    assert request.getfixturevalue("default_database_guard") == []
    watchdog = request.node.get_closest_marker("timeout")
    assert watchdog is not None
    assert watchdog.args == (300,)
    assert watchdog.kwargs == {
        "method": "signal",
        "func_only": False,
        "disable_debugger_detection": True,
    }
