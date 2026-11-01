"""Opt-in PostgreSQL proof of the tenant RLS revision (AUD-277, AUD-360, AUD-450).

Run only against an explicitly designated disposable PostgreSQL database. Two
identities are created by the database administrator before the test runs:

* AUD_TENANT_RLS_DISPOSABLE_PG_URL: a non-superuser, non-BYPASSRLS role that may
  create a schema. It owns the schema, so FORCE ROW LEVEL SECURITY applies to it
  as an ordinary application role.
* AUD_TENANT_RLS_BYPASS_PG_URL: a LOGIN role that is a member of the NOLOGIN
  ``ue_rls_bypass`` role. The administrator creates ``ue_rls_bypass`` ahead of
  time, as a deployment does before the migration runs.

The schema holds real tables. The two migrations under test run on them through
a minimal ``op`` adapter that executes the same SQL on a real connection. Plain
``CREATE INDEX`` replaces ``CREATE INDEX CONCURRENTLY``; policy and trigger DDL
is executed unchanged. Session wiring comes from the application's own
``set_pg_tenant_context`` listener.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, make_url

from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx

_ROOT = Path(__file__).resolve().parents[2]
_RLS_MIGRATION = _ROOT / "alembic/versions/202607230001_multi_tenant_rls.py"
_MESSAGE_MIGRATION = _ROOT / "alembic/versions/202603170003_enable_rls_on_messages.py"

_ORDINARY_URL = os.getenv("AUD_TENANT_RLS_DISPOSABLE_PG_URL", "")
_BYPASS_URL = os.getenv("AUD_TENANT_RLS_BYPASS_PG_URL", "")
_OPTED_IN = os.getenv("AUD_TENANT_RLS_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            _OPTED_IN
            and _ORDINARY_URL.startswith("postgresql+psycopg://")
            and _BYPASS_URL.startswith("postgresql+psycopg://")
        ),
        reason="Set AUD_TENANT_RLS_DISPOSABLE=1 and two postgresql+psycopg URLs",
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

# The policy as first shipped: a PERMISSIVE USING (true) plus a RESTRICTIVE tenant
# predicate that honours the app.bypass_rls GUC and NULL-tenant rows.
_HISTORICAL_POLICIES = (
    "ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
    "CREATE POLICY default_permissive_policy ON {table} AS PERMISSIVE "
    "USING (true) WITH CHECK (true)",
    "CREATE POLICY tenant_isolation_policy ON {table} AS RESTRICTIVE "
    "USING (current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id IS NULL "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)",
)


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"aud277_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ExecutingOp:
    """The subset of ``alembic.op`` these two migrations use, run for real."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_bind(self) -> Connection:
        return self._connection

    def execute(self, statement: Any) -> None:
        self._connection.execute(statement)

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        assert column.name == "tenant_id"
        self._connection.execute(
            sa.text(
                f"ALTER TABLE {table} ADD COLUMN tenant_id uuid "
                "REFERENCES tenants(id) ON DELETE CASCADE"
            )
        )

    def create_index(self, name: str, table: str, columns: list[str], **_: Any) -> None:
        self._connection.execute(
            sa.text(f"CREATE INDEX {name} ON {table} ({', '.join(columns)})")
        )

    def get_context(self) -> _ExecutingOp:
        return self

    def autocommit_block(self) -> contextlib.AbstractContextManager[None]:
        return contextlib.nullcontext()


def _run_migration(connection: Connection, module: ModuleType) -> None:
    with patch.object(module, "op", _ExecutingOp(connection)):
        module.upgrade()


def _engine(url: str, schema: str) -> sa.Engine:
    return sa.create_engine(url, connect_args={"options": f"-csearch_path={schema}"})


def _seed_legacy_rows(connection: Connection) -> None:
    connection.execute(
        sa.text("CREATE TABLE tenants (id uuid PRIMARY KEY, name text NOT NULL)")
    )
    connection.execute(
        sa.text("INSERT INTO tenants (id, name) VALUES (:a, 'A'), (:b, 'B')"),
        {"a": _TENANT_A, "b": _TENANT_B},
    )
    for table in _CORE_TABLES:
        connection.execute(
            sa.text(
                f"CREATE TABLE {table} (id integer PRIMARY KEY, chat_id uuid, body text)"
            )
        )
    connection.execute(
        sa.text(
            "CREATE TABLE chat_participants (chat_id uuid NOT NULL, user_id uuid NOT NULL)"
        )
    )
    connection.execute(
        sa.text("INSERT INTO chat_participants (chat_id, user_id) VALUES (:c, :u)"),
        {"c": _CHAT_A, "u": _USER_A},
    )
    # Rows written before the tenant column existed keep a NULL tenant.
    connection.execute(
        sa.text("INSERT INTO news (id, body) VALUES (1, 'a'), (2, 'b'), (3, 'null')")
    )
    connection.execute(
        sa.text(
            "INSERT INTO messages (id, chat_id, body) VALUES "
            "(11, :a, 'x'), (12, :a, 'x'), (13, :a, 'x'), (14, :b, 'x')"
        ),
        {"a": _CHAT_A, "b": _CHAT_B},
    )


@pytest.fixture(scope="module")
def rls_schema() -> Iterator[str]:
    """Create the schema, legacy rows and migrations once; each test rolls back."""
    schema = "aud277_" + uuid.uuid4().hex
    ordinary = _engine(_ORDINARY_URL, schema)
    bypass = _engine(_BYPASS_URL, schema)
    bypass_role = make_url(_BYPASS_URL).username
    try:
        with sa.create_engine(_ORDINARY_URL).begin() as admin_probe:
            role = admin_probe.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            ).one()
            assert tuple(role) == (False, False)
            admin_probe.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

        with ordinary.begin() as connection:
            _seed_legacy_rows(connection)
        with ordinary.begin() as connection:
            _run_migration(connection, _load(_MESSAGE_MIGRATION))
            _run_migration(connection, _load(_RLS_MIGRATION))
            connection.execute(
                sa.text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{bypass_role}"')
            )
            connection.execute(
                sa.text(
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" '
                    f'TO "{bypass_role}"'
                )
            )
        with bypass.begin() as connection:
            # Seeding as a bypass-role member places rows of both tenants and leaves
            # one NULL-tenant row deliberately: news 1 (A), 2 (B), 3 (NULL).
            connection.execute(
                sa.text("UPDATE news SET tenant_id = :a WHERE id = 1"), {"a": _TENANT_A}
            )
            connection.execute(
                sa.text("UPDATE news SET tenant_id = :b WHERE id = 2"), {"b": _TENANT_B}
            )
            # The participant policy still applies to messages, so seeding runs as
            # the chat-A participant: message 11 (A), 12 (B), 13 stays NULL.
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            connection.execute(
                sa.text("UPDATE messages SET tenant_id = :a WHERE id = 11"),
                {"a": _TENANT_A},
            )
            connection.execute(
                sa.text("UPDATE messages SET tenant_id = :b WHERE id = 12"),
                {"b": _TENANT_B},
            )
        yield schema
    finally:
        bypass.dispose()
        ordinary.dispose()
        with sa.create_engine(_ORDINARY_URL).begin() as cleanup:
            cleanup.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@contextlib.contextmanager
def _rolled_back(url: str, schema: str) -> Iterator[Connection]:
    """One transaction on a fresh connection, always rolled back."""
    engine = _engine(url, schema)
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
    return set(connection.execute(statement).scalars())


def test_no_permissive_true_policy_remains_on_core_tables(rls_schema: str) -> None:
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        policies = connection.execute(
            sa.text(
                "SELECT tablename, policyname, permissive, qual FROM pg_policies "
                "WHERE schemaname = current_schema()"
            )
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


def test_tenant_session_sees_only_its_rows_and_never_null_rows(rls_schema: str) -> None:
    """AUD-360: NULL-tenant rows are hidden, and another tenant's rows stay hidden."""
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news") == {1}
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == set()


def test_guc_bypass_cannot_expose_other_tenants_or_null_rows(rls_schema: str) -> None:
    """AUD-450: a hand-set app.bypass_rls GUC grants nothing, and the listener never sets it."""
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
            )
            assert _ids(connection, "news") == {1}
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
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


def test_dedicated_bypass_role_member_sees_every_row(rls_schema: str) -> None:
    """AUD-450 positive control: only membership in ue_rls_bypass bypasses the policy."""
    with _rolled_back(_BYPASS_URL, rls_schema) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == {1, 2, 3}


def test_ordinary_writes_are_stamped_with_the_session_tenant(rls_schema: str) -> None:
    """AUD-360: an ORM-shaped INSERT that omits tenant_id is stamped by the trigger."""
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("INSERT INTO news (id, body) VALUES (20, 'orm')")
            )
            connection.execute(
                sa.text(
                    "INSERT INTO news (id, tenant_id, body) VALUES (21, NULL, 'null')"
                )
            )
            # Message inserts also need the participant context the ORM sets.
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO messages (id, chat_id, body) VALUES (22, :c, 'm')"
                ),
                {"c": _CHAT_A},
            )
            stamped = dict(
                connection.execute(
                    sa.text("SELECT id, tenant_id FROM news WHERE id IN (20, 21)")
                ).all()
            )
            assert stamped == {20: _TENANT_A, 21: _TENANT_A}
            assert (
                connection.execute(
                    sa.text("SELECT tenant_id FROM messages WHERE id = 22")
                ).scalar()
                == _TENANT_A
            )


def test_writes_cannot_target_another_tenant_or_escape_the_session(
    rls_schema: str,
) -> None:
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            with pytest.raises(sa.exc.DBAPIError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, tenant_id, body) VALUES (30, :b, 'x')"
                        ),
                        {"b": _TENANT_B},
                    )
            with pytest.raises(sa.exc.DBAPIError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text("UPDATE news SET tenant_id = :b WHERE id = 1"),
                        {"b": _TENANT_B},
                    )
            with pytest.raises(sa.exc.DBAPIError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text("UPDATE news SET tenant_id = NULL WHERE id = 1")
                    )
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        # Without a tenant context an INSERT is refused rather than stored unowned.
        with _application_context(connection, tenant=None):
            with pytest.raises(sa.exc.DBAPIError):
                with connection.begin_nested():
                    connection.execute(
                        sa.text("INSERT INTO news (id, body) VALUES (31, 'x')")
                    )


def test_messages_need_both_participation_and_the_session_tenant(
    rls_schema: str,
) -> None:
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            # Participant of chat A and tenant A: only 11. Row 12 is tenant B,
            # row 13 has a NULL tenant, and row 14 belongs to chat B.
            assert _ids(connection, "messages") == {11}


def test_historical_policy_cause_is_not_the_permissive_true_policy(
    rls_schema: str,
) -> None:
    """Establish the original AUD-277 cause on real tables, as an ordinary role.

    The historical USING (true) policy was PERMISSIVE and ANDed with a RESTRICTIVE
    tenant predicate, so it did not widen access by itself. The leaks came from the
    GUC bypass (AUD-450) and from NULL-tenant rows (AUD-360).
    """
    with _rolled_back(_ORDINARY_URL, rls_schema) as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE news_historical "
                "(id integer PRIMARY KEY, tenant_id uuid, body text)"
            )
        )
        for statement in _HISTORICAL_POLICIES:
            connection.execute(sa.text(statement.format(table="news_historical")))
        # The historical WITH CHECK honoured the GUC, which any session could set by
        # hand, so the seed sets it directly. The listener no longer writes it.
        connection.execute(sa.text("SELECT set_config('app.bypass_rls', 'on', true)"))
        connection.execute(
            sa.text(
                "INSERT INTO news_historical (id, tenant_id, body) "
                "VALUES (1, :a, 'a'), (2, :b, 'b'), (3, NULL, 'null')"
            ),
            {"a": _TENANT_A, "b": _TENANT_B},
        )
        # Clear the hand-set GUC before the tenant-scoped reads.
        connection.execute(sa.text("SELECT set_config('app.bypass_rls', '', true)"))
        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news_historical") == {1, 3}
            connection.execute(
                sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
            )
            assert _ids(connection, "news_historical") == {1, 2, 3}
