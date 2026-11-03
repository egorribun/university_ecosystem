"""Partition DDL and audit-leaf isolation on a disposable PostgreSQL 17 server.

Each case owns a fresh server because role changes are cluster-global, and runs
the real role bootstrap first so ue_app and ue_worker hold production grants.
The migrator and runtime logins are real password sessions. The partition
manager runs through an async engine opened as the login under test.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from app.services import partition_manager
from tests.fixtures.owned_baseline_postgres import (
    OwnedPostgres,
    owned_postgres_server,
)
from tests.fixtures.owned_baseline_postgres import (
    clean_database as clean_database,
)
from tests.fixtures.owned_baseline_postgres import (
    default_database_guard as default_database_guard,
)
from tests.fixtures.owned_baseline_postgres import (
    initialize_database_for_tests as initialize_database_for_tests,
)
from tests.fixtures.owned_baseline_postgres import (
    prepare_database as prepare_database,
)
from tests.test_app_db_role_bootstrap_postgres import _bootstrap, _connect

pytestmark = [pytest.mark.integration, pytest.mark.timeout(300, method="signal")]

_AUDIT_LEAF_PREFIX = "data_access_logs"
_PARENT_DDL = (
    "CREATE TABLE public.data_access_logs ("
    "id uuid NOT NULL, action text NOT NULL, signature text, "
    "created_at timestamptz NOT NULL, PRIMARY KEY (id, created_at)"
    ") PARTITION BY RANGE (created_at)"
)
_OTHER_PARENTS_DDL = (
    "CREATE TABLE public.notifications (id bigint, created_at timestamptz NOT NULL) "
    "PARTITION BY RANGE (created_at)",
    "CREATE TABLE public.notification_deliveries "
    "(id bigint, attempted_at timestamptz NOT NULL) PARTITION BY RANGE (attempted_at)",
)


@pytest.fixture
def isolation_server(request: pytest.FixtureRequest) -> Iterator[OwnedPostgres]:
    request.getfixturevalue("default_database_guard")
    with owned_postgres_server() as server:
        yield server


def _create_tables(server: OwnedPostgres, *leaves: tuple[str, str, str]) -> None:
    """Create the parents and any named leaves as the owner, as Alembic would."""
    with _connect(server) as admin:
        admin.execute("SET ROLE ue_migrator")
        admin.execute(_PARENT_DDL)
        for statement in _OTHER_PARENTS_DDL:
            admin.execute(statement)
        for leaf, start, end in leaves:
            admin.execute(
                f"CREATE TABLE public.{leaf} PARTITION OF public.data_access_logs "
                f"FOR VALUES FROM ('{start}') TO ('{end}')"
            )
        admin.execute("RESET ROLE")


def _provision_logins(server: OwnedPostgres) -> str:
    """Set known passwords for the two logins under test, after the last bootstrap.

    Every bootstrap run reapplies the role passwords, so this runs last.
    """
    password = uuid4().hex + uuid4().hex
    with _connect(server) as admin:
        for role in ("ue_migrator", "ue_app"):
            admin.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
    return password


def _login(server: OwnedPostgres, role: str, password: str) -> psycopg.Connection:
    server._lease.verify(server)
    return psycopg.connect(
        host=server.url.host,
        port=server.url.port,
        user=role,
        password=password,
        dbname=server.url.database,
        connect_timeout=5,
        options="-c lock_timeout=10s -c statement_timeout=60s",
        autocommit=True,
    )


def _run_ensure(
    server: OwnedPostgres,
    role: str,
    password: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    warmup_months: int = 0,
    strict: bool = False,
) -> bool:
    """Run the production partition path as the given login against the server."""
    settings = SimpleNamespace(
        partition_warmup_months=warmup_months, partition_retention_days=365
    )
    url = URL.create(
        "postgresql+asyncpg",
        username=role,
        password=password,
        host=server.url.host,
        port=server.url.port,
        database=server.url.database,
    )

    async def run() -> bool:
        engine = create_async_engine(url)
        monkeypatch.setattr(partition_manager, "engine", engine)
        try:
            return await partition_manager.ensure_partitions_exist(strict=strict)
        finally:
            await engine.dispose()

    with monkeypatch.context() as patched:
        patched.setattr("app.core.config.settings", settings)
        return asyncio.run(run())


def _leaves(server: OwnedPostgres) -> list[str]:
    with _connect(server) as admin:
        rows = admin.execute(
            "SELECT child.relname FROM pg_inherits AS inheritance "
            "JOIN pg_class AS child ON child.oid = inheritance.inhrelid "
            "WHERE inheritance.inhparent = 'public.data_access_logs'::regclass "
            "ORDER BY child.relname"
        ).fetchall()
    return [name for (name,) in rows]


def _table_privileges(
    connection: psycopg.Connection, role: str, relation: str
) -> tuple[bool, ...]:
    row = connection.execute(
        "SELECT has_table_privilege(%(role)s, %(rel)s, 'SELECT'), "
        "has_table_privilege(%(role)s, %(rel)s, 'INSERT'), "
        "has_table_privilege(%(role)s, %(rel)s, 'UPDATE'), "
        "has_table_privilege(%(role)s, %(rel)s, 'DELETE'), "
        "has_table_privilege(%(role)s, %(rel)s, 'TRUNCATE')",
        {"role": role, "rel": relation},
    ).fetchone()
    assert row is not None
    return tuple(bool(value) for value in row)


def _current_month_leaf() -> str:
    """The leaf that the maintenance step creates for the current month."""
    import rust_ext

    return str(rust_ext.get_partition_info(_AUDIT_LEAF_PREFIX, 0).name)


def test_maintenance_created_leaf_is_not_directly_writable_by_runtime(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server)
    password = _provision_logins(isolation_server)

    assert _run_ensure(isolation_server, "ue_migrator", password, monkeypatch) is True
    leaves = _leaves(isolation_server)
    assert leaves, "maintenance created no audit leaf"

    with _connect(isolation_server) as admin:
        for leaf in leaves:
            relation = f"public.{leaf}"
            parent = _table_privileges(admin, "ue_worker", "public.data_access_logs")
            # The worker keeps the parent's DML, so the leaf must match it.
            assert _table_privileges(admin, "ue_worker", relation) == parent
            assert _table_privileges(admin, "ue_app", relation) == (False,) * 5

    with _login(isolation_server, "ue_app", password) as app:
        # Routed statements through the parent still work for the runtime.
        app.execute(
            "INSERT INTO public.data_access_logs (id, action, signature, created_at) "
            "VALUES ('00000000-0000-4000-8000-000000000001', 'probe', NULL, now())"
        )
        assert app.execute(
            "SELECT count(*) FROM public.data_access_logs"
        ).fetchone() == (1,)
        for leaf in leaves:
            direct = sql.Identifier("public", leaf)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(
                    sql.SQL(
                        "INSERT INTO {} (id, action, signature, created_at) "
                        "VALUES ('00000000-0000-4000-8000-000000000002', 'x', NULL, now())"
                    ).format(direct)
                )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sql.SQL("UPDATE {} SET action = 'tampered'").format(direct))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(sql.SQL("DELETE FROM {}").format(direct))


def test_creation_alone_isolates_the_new_leaf_without_the_sweep(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guarantee holds in the CREATE transaction, not only in the later sweep."""
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server)
    password = _provision_logins(isolation_server)
    monkeypatch.setattr(
        partition_manager, "_isolate_audit_partitions", AsyncMock(return_value=None)
    )

    assert _run_ensure(isolation_server, "ue_migrator", password, monkeypatch) is True

    leaves = _leaves(isolation_server)
    assert leaves == [_current_month_leaf()]
    with _connect(isolation_server) as admin:
        assert _table_privileges(admin, "ue_app", f"public.{leaves[0]}") == (False,) * 5


def test_runtime_has_no_audit_update_even_with_a_legacy_column_grant(
    isolation_server: OwnedPostgres,
) -> None:
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server)
    with _connect(isolation_server) as admin:
        # A volume bootstrapped by the retired revision still carries this grant.
        admin.execute("GRANT UPDATE (signature) ON public.data_access_logs TO ue_app")
    assert _bootstrap(isolation_server) == 0
    password = _provision_logins(isolation_server)

    with _connect(isolation_server) as admin:
        assert admin.execute(
            "SELECT has_table_privilege('ue_app', 'public.data_access_logs', 'UPDATE'), "
            "has_any_column_privilege('ue_app', 'public.data_access_logs', 'UPDATE')"
        ).fetchone() == (False, False)
    with _login(isolation_server, "ue_app", password) as app:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("UPDATE public.data_access_logs SET signature = 'sig'")


def test_maintenance_isolates_a_leaf_created_outside_the_maintenance_path(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A baseline-style leaf for a month the maintenance step never creates.
    # Created after the last bootstrap, as a migration does on a fresh volume: the
    # bootstrap's narrowing has not seen it, so only maintenance can isolate it.
    leaf = "data_access_logs_y2030m01"
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server, (leaf, "2030-01-01", "2030-02-01"))
    password = _provision_logins(isolation_server)
    with _connect(isolation_server) as admin:
        # Before maintenance the default-privilege grant reaches this leaf.
        assert admin.execute(
            "SELECT has_table_privilege('ue_app', %s, 'INSERT')", (f"public.{leaf}",)
        ).fetchone() == (True,)

    assert _run_ensure(isolation_server, "ue_migrator", password, monkeypatch) is True

    with _connect(isolation_server) as admin:
        assert _table_privileges(admin, "ue_app", f"public.{leaf}") == (False,) * 5
    with _login(isolation_server, "ue_app", password) as app:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute(
                sql.SQL(
                    "INSERT INTO {} (id, action, signature, created_at) "
                    "VALUES ('00000000-0000-4000-8000-000000000003', 'x', NULL, "
                    "'2030-01-15T00:00:00Z')"
                ).format(sql.Identifier("public", leaf))
            )


def test_runtime_login_is_refused_before_partition_ddl_and_cannot_prune(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired = "data_access_logs_y2000m01"
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server, (expired, "2000-01-01", "2000-02-01"))
    password = _provision_logins(isolation_server)
    before = _leaves(isolation_server)
    assert expired in before

    with _connect(isolation_server) as admin:
        assert admin.execute(
            "SELECT has_schema_privilege('ue_app', 'public', 'CREATE')"
        ).fetchone() == (False,)

    # Any call that reaches a partition DDL helper fails this test.
    lock = AsyncMock(side_effect=AssertionError("partition DDL attempted as runtime"))
    monkeypatch.setattr(partition_manager, "_lock_partition_ddl", lock)
    assert _run_ensure(isolation_server, "ue_app", password, monkeypatch) is False
    lock.assert_not_called()
    assert _leaves(isolation_server) == before


def test_privileged_maintenance_prunes_an_expired_leaf(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired = "data_access_logs_y2000m01"
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server, (expired, "2000-01-01", "2000-02-01"))
    assert _bootstrap(isolation_server) == 0
    password = _provision_logins(isolation_server)

    assert _run_ensure(isolation_server, "ue_migrator", password, monkeypatch) is True

    # Maintenance drops the expired leaf and still creates the current month.
    assert _leaves(isolation_server) == [_current_month_leaf()]


def test_strict_maintenance_surfaces_a_failed_creation_after_isolation(
    isolation_server: OwnedPostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A creation that cannot succeed must fail the maintenance step, not be skipped.

    The partition name is already taken by a table that is not a partition, so
    the CREATE fails on every run without touching the leaf that already exists.
    """
    assert _bootstrap(isolation_server) == 0
    _create_tables(isolation_server)
    password = _provision_logins(isolation_server)
    with _connect(isolation_server) as admin:
        admin.execute("SET ROLE ue_migrator")
        admin.execute(f"CREATE TABLE public.{_current_month_leaf()} (id int)")
        admin.execute("RESET ROLE")

    with pytest.raises(partition_manager.PartitionMaintenanceError):
        _run_ensure(
            isolation_server,
            "ue_migrator",
            password,
            monkeypatch,
            warmup_months=0,
            strict=True,
        )
