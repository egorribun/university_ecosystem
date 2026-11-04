"""Actual MVP baseline tenant, role, message-participant and trigger enforcement."""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="signal", func_only=False),
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run",
    ),
]
_CORE_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)
_TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_USER_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
_CHAT_A = uuid.UUID("22222222-2222-4222-8222-222222222222")
_CHAT_B = uuid.UUID("33333333-3333-4333-8333-333333333333")
# Every baseline table that carries tenant_id under forced RLS and the stamping trigger.
_TENANT_TABLES = (
    "chats",
    "events",
    "groups",
    "messages",
    "news",
    "notifications",
    "schedule",
    "stories",
    "users",
)


def _engine(url: sa.URL) -> sa.Engine:
    return sa.create_engine(
        url,
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


@pytest.fixture(scope="module")
def rls_schema(request: pytest.FixtureRequest) -> Iterator[SimpleNamespace]:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Tenant RLS tests require --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        ordinary_role = "tenant_reader_" + uuid.uuid4().hex
        bypass_role = "tenant_member_" + uuid.uuid4().hex
        credential = uuid.uuid4().hex + uuid.uuid4().hex
        admin = _engine(baseline.url)
        try:
            with admin.begin() as connection:
                # Generated identifiers and hex credential belong only to this owned server.
                for role in (ordinary_role, bypass_role):
                    connection.exec_driver_sql(
                        f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD '{credential}'"
                    )
                    connection.exec_driver_sql(
                        f'GRANT USAGE ON SCHEMA public TO "{role}"'
                    )
                    connection.exec_driver_sql(
                        f'GRANT SELECT, INSERT, UPDATE, DELETE ON public.news, public.messages, public.notifications TO "{role}"'
                    )
                    connection.exec_driver_sql(
                        f'GRANT SELECT ON public.chat_participants TO "{role}"'
                    )
                connection.exec_driver_sql(f'GRANT ue_rls_bypass TO "{bypass_role}"')
                for table in _CORE_TABLES:
                    connection.exec_driver_sql(
                        f'ALTER TABLE public.{table} OWNER TO "{ordinary_role}"'
                    )
                for tenant, name in ((_TENANT_A, "a"), (_TENANT_B, "b")):
                    connection.execute(
                        sa.text(
                            "INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :name)"
                        ),
                        {"id": tenant, "name": name},
                    )
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, hashed_password, tenant_id) VALUES (:id, 'tenant@example.invalid', :credential, :tenant)"
                    ),
                    {
                        "id": _USER_A,
                        "credential": "!" + uuid.uuid4().hex,
                        "tenant": _TENANT_A,
                    },
                )
                for chat in (_CHAT_A, _CHAT_B):
                    connection.execute(
                        sa.text(
                            "INSERT INTO chats (id, tenant_id) VALUES (:id, :tenant)"
                        ),
                        {"id": chat, "tenant": _TENANT_A},
                    )
                connection.execute(
                    sa.text(
                        "INSERT INTO chat_participants (chat_id, user_id) VALUES (:c, :u)"
                    ),
                    {"c": _CHAT_A, "u": _USER_A},
                )
                for identifier, tenant in ((1, _TENANT_A), (2, _TENANT_B), (3, None)):
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, title, content, tenant_id) VALUES (:id, 'RLS', 'proof', :tenant)"
                        ),
                        {"id": uuid.UUID(int=identifier), "tenant": tenant},
                    )
                for identifier, tenant, chat in (
                    (11, _TENANT_A, _CHAT_A),
                    (12, _TENANT_B, _CHAT_A),
                    (13, None, _CHAT_A),
                    (14, _TENANT_A, _CHAT_B),
                ):
                    connection.execute(
                        sa.text(
                            "INSERT INTO messages (id, content, sender_id, chat_id, tenant_id) VALUES (:id, 'RLS proof', :u, :c, :tenant)"
                        ),
                        {
                            "id": uuid.UUID(int=identifier),
                            "u": _USER_A,
                            "c": chat,
                            "tenant": tenant,
                        },
                    )
            state = SimpleNamespace(
                ordinary=baseline.url.set(username=ordinary_role, password=credential),
                bypass=baseline.url.set(username=bypass_role, password=credential),
            )
            for url, member in ((state.ordinary, False), (state.bypass, True)):
                with _rolled_back(url) as connection:
                    assert tuple(
                        connection.execute(
                            sa.text(
                                "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') FROM pg_roles WHERE rolname = current_user"
                            )
                        ).one()
                    ) == (False, False, member)
                    assert (
                        connection.scalar(
                            sa.text("SELECT row_security_active('public.news')")
                        )
                        is True
                    )
            yield state
        finally:
            admin.dispose()


@contextlib.contextmanager
def _rolled_back(url: sa.URL) -> Iterator[Connection]:
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


@contextlib.contextmanager
def _application_context(
    connection: Connection, *, tenant: uuid.UUID | None, bypass: bool = False
) -> Iterator[None]:
    """Apply the application's own session wiring for the given request scope."""
    tenant_token = tenant_id_ctx.set(str(tenant) if tenant else "")
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        set_pg_tenant_context(None, None, connection)
        yield
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


def _ids(connection: Connection, table: str) -> set[int]:
    statement = sa.select(sa.column("id")).select_from(sa.table(table))
    return {value.int for value in connection.execute(statement).scalars()}


def test_no_permissive_true_policy_remains_on_core_tables(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        policies = connection.execute(
            sa.text(
                "SELECT tablename, policyname, permissive, qual FROM pg_policies "
                "WHERE schemaname = current_schema() AND tablename = ANY(:tables)"
            ),
            {"tables": list(_CORE_TABLES)},
        ).all()
    assert not [row for row in policies if row.qual == "true"]
    assert not [
        row for row in policies if row.policyname == "default_permissive_policy"
    ]
    tenant = {
        row.tablename: row.permissive
        for row in policies
        if row.policyname == "tenant_isolation_policy"
    }
    assert set(tenant) == set(_CORE_TABLES)
    assert tenant["messages"] == "RESTRICTIVE"
    assert {tenant[t] for t in _CORE_TABLES if t != "messages"} == {"PERMISSIVE"}


def test_tenant_session_sees_only_its_rows_and_never_null_rows(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: NULL-tenant rows are hidden, and another tenant's rows stay hidden."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news") == {1}
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == set()


def test_guc_bypass_cannot_expose_other_tenants_or_null_rows(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-450: a hand-set app.bypass_rls GUC grants nothing, and the listener never sets it."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
            )
            assert _ids(connection, "news") == {1}
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None, bypass=True):
            # The listener's bypass flag writes no GUC, so the setting stays unset.
            assert (
                connection.execute(
                    sa.text(
                        "SELECT coalesce(current_setting('app.bypass_rls', true), '')"
                    )
                ).scalar()
                == ""
            )
            assert _ids(connection, "news") == set()


def test_dedicated_bypass_role_member_sees_every_row(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-450 positive control: only membership in ue_rls_bypass bypasses the policy."""
    with _rolled_back(rls_schema.bypass) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == {1, 2, 3}


def test_ordinary_writes_are_stamped_with_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: an ORM-shaped INSERT that omits tenant_id is stamped by the trigger."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text(
                    "INSERT INTO news (id, title, content) VALUES ('00000000-0000-0000-0000-000000000014', 'stamp', 'orm')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO news (id, tenant_id, title, content) VALUES ('00000000-0000-0000-0000-000000000015', NULL, 'stamp', 'null')"
                )
            )
            # Message inserts also need the participant context the ORM sets.
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO messages (id, chat_id, sender_id, content) VALUES ('00000000-0000-0000-0000-000000000016', :c, :u, 'm')"
                ),
                {"c": _CHAT_A, "u": _USER_A},
            )
            stamped = dict(
                connection.execute(
                    sa.text(
                        "SELECT id, tenant_id FROM news WHERE id IN ('00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000015')"
                    )
                ).all()
            )
            assert stamped == {
                uuid.UUID(int=20): _TENANT_A,
                uuid.UUID(int=21): _TENANT_A,
            }
            assert (
                connection.execute(
                    sa.text(
                        "SELECT tenant_id FROM messages WHERE id = '00000000-0000-0000-0000-000000000016'"
                    )
                ).scalar()
                == _TENANT_A
            )


def test_writes_cannot_target_another_tenant_or_escape_the_session(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, tenant_id, title, content) VALUES ('00000000-0000-0000-0000-00000000001e', :b, 'deny', 'x')"
                        ),
                        {"b": _TENANT_B},
                    )
            assert rejected.value.orig.sqlstate == "42501"
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "UPDATE news SET tenant_id = :b WHERE id = '00000000-0000-0000-0000-000000000001'"
                        ),
                        {"b": _TENANT_B},
                    )
            assert rejected.value.orig.sqlstate == "42501"
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "UPDATE news SET tenant_id = NULL WHERE id = '00000000-0000-0000-0000-000000000001'"
                        )
                    )
            assert rejected.value.orig.sqlstate == "42501"
    with _rolled_back(rls_schema.ordinary) as connection:
        # Without a tenant context an INSERT is refused rather than stored unowned.
        with _application_context(connection, tenant=None):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, title, content) VALUES ('00000000-0000-0000-0000-00000000001f', 'deny', 'x')"
                        )
                    )

            assert rejected.value.orig.sqlstate == "42501"


def test_messages_need_both_participation_and_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            # Participant of chat A and tenant A: only 11. Row 12 is tenant B,
            # row 13 has a NULL tenant, and row 14 belongs to chat B.
            assert _ids(connection, "messages") == {11}


def test_every_tenant_table_forces_rls_and_stamps_unowned_inserts(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: each tenant-scoped table is forced under RLS and fills NULL tenants."""
    with _rolled_back(rls_schema.ordinary) as connection:
        rows = connection.execute(
            sa.text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = c.oid "
                "AND t.tgname = 'ue_rls_assign_tenant' AND NOT t.tgisinternal "
                "AND t.tgenabled = 'O') AS stamps "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
            ),
            {"tables": list(_TENANT_TABLES)},
        ).all()
    assert {row.relname for row in rows} == set(_TENANT_TABLES)
    assert all(
        row.relrowsecurity and row.relforcerowsecurity and row.stamps for row in rows
    )


def test_notification_producer_rows_are_owned_by_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: a producer insert without tenant is stamped; an unscoped one is refused."""
    notification = uuid.UUID(int=40)
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at) "
                    "VALUES (:id, :u, 'stamp', false, now())"
                ),
                {"id": notification, "u": _USER_A},
            )
            assert (
                connection.execute(
                    sa.text("SELECT tenant_id FROM notifications WHERE id = :id"),
                    {"id": notification},
                ).scalar()
                == _TENANT_A
            )
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO notifications (id, user_id, title, read, created_at) "
                            "VALUES (:id, :u, 'deny', false, now())"
                        ),
                        {"id": uuid.UUID(int=41), "u": _USER_A},
                    )
            assert rejected.value.orig.sqlstate == "42501"


def test_worker_bypass_producer_must_write_its_tenant_explicitly(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: under bypass no session tenant exists, so the producer's tenant_id is the owner."""
    explicit, unowned = uuid.UUID(int=42), uuid.UUID(int=43)
    with _rolled_back(rls_schema.bypass) as connection:
        with _application_context(connection, tenant=None, bypass=True):
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at, tenant_id) "
                    "VALUES (:id, :u, 'owned', false, now(), :t)"
                ),
                {"id": explicit, "u": _USER_A, "t": _TENANT_B},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at) "
                    "VALUES (:id, :u, 'orphan', false, now())"
                ),
                {"id": unowned, "u": _USER_A},
            )
            owners = dict(
                connection.execute(
                    sa.text(
                        "SELECT id, tenant_id FROM notifications WHERE id = ANY(:ids)"
                    ),
                    {"ids": [explicit, unowned]},
                ).all()
            )
    assert owners[explicit] == _TENANT_B
    # Recorded residual: a bypass write without tenant_id stays unowned, and the
    # tenant-scoped policy hides it from every tenant. Producers must write it.
    assert owners[unowned] is None
