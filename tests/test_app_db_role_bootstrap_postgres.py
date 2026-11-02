"""Real psql bootstrap regressions on a lease-verified, disposable PG17 server.

No operator URL is accepted. Every case owns a fresh server because role changes
are cluster-global. The fixed image must already be present; no pull is allowed.
"""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import psycopg
import pytest

from tests.fixtures.owned_baseline_postgres import (
    OwnedPostgres,
    OwnedPostgresError,
    _docker_call,
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

pytestmark = [pytest.mark.integration, pytest.mark.timeout(300, method="signal")]
_SQL = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/postgres-roles/bootstrap-app-roles.sql"
)


@pytest.fixture
def role_server(request: pytest.FixtureRequest) -> Iterator[OwnedPostgres]:
    request.getfixturevalue("default_database_guard")
    with owned_postgres_server() as server:
        yield server


def _connect(server: OwnedPostgres) -> psycopg.Connection:
    server._lease.verify(server)
    return psycopg.connect(
        host=server.url.host,
        port=server.url.port,
        user=server.url.username,
        password=server.url.password,
        dbname=server.url.database,
        connect_timeout=5,
        options="-c lock_timeout=10s -c statement_timeout=60s",
        autocommit=True,
    )


def _bootstrap(server: OwnedPostgres) -> int:
    server._lease.verify(server)
    prelude = (
        "\\set db postgres\n"
        "\\getenv migrator_password ROLE_TEST_PASSWORD\n"
        "\\getenv app_password ROLE_TEST_PASSWORD\n"
        "\\getenv worker_password ROLE_TEST_PASSWORD\n"
    )
    source = (prelude + _SQL.read_text(encoding="utf-8")).encode("utf-8")
    filename = f"role-bootstrap-{uuid4().hex}.sql"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo(filename)
        member.size = len(source)
        member.mode = 0o600
        tar.addfile(member, io.BytesIO(source))
    client = server._lease.client
    assert _docker_call(
        lambda: client.put_archive(server.container_id, "/root", archive.getvalue()),
        "role bootstrap source staging",
    )
    server._lease.verify(server)
    execution = _docker_call(
        lambda: client.exec_create(
            server.container_id,
            cmd=[
                "psql",
                "-X",
                "--no-password",
                "--dbname=postgres",
                "--username=baseline_admin",
                f"--file=/root/{filename}",
            ],
            environment={
                "PGHOST": "/var/run/postgresql",
                "PGPORT": "5432",
                "PGCONNECT_TIMEOUT": "5",
                "ROLE_TEST_PASSWORD": uuid4().hex + uuid4().hex,
            },
            user="root",
        ),
        "role bootstrap exec creation",
    )
    execution_id = execution.get("Id")
    if (
        not isinstance(execution_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", execution_id) is None
    ):
        raise OwnedPostgresError("Owned role bootstrap exec identity unacknowledged")
    admitted = _docker_call(
        lambda: client.exec_inspect(execution_id), "role bootstrap exec admission"
    )
    if (
        admitted.get("ContainerID") != server.container_id
        or admitted.get("Running") is not False
    ):
        raise OwnedPostgresError("Owned role bootstrap exec identity mismatch")
    server._lease.verify(server)
    # Attached exec uses Docker SDK's unbounded stream reader. Detach instead:
    # each inspect is a bounded HTTP call and the scheduling deadline is explicit.
    _docker_call(
        lambda: client.exec_start(execution_id, detach=True),
        "role bootstrap detached execution",
    )
    return _wait_for_exec(server, execution_id)


def _wait_for_exec(server: OwnedPostgres, execution_id: str) -> int:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        server._lease.verify(server)
        result = _docker_call(
            lambda: server._lease.client.exec_inspect(execution_id),
            "role bootstrap exit inspection",
        )
        if result.get("ContainerID") != server.container_id:
            raise OwnedPostgresError("Owned role bootstrap exec identity changed")
        if result["Running"] is False:
            assert type(result["ExitCode"]) is int
            return result["ExitCode"]
        remaining = deadline - time.monotonic()
        if remaining > 0:
            # Bounded by the remaining 90-second execution deadline.
            time.sleep(min(0.1, remaining))
    # The caller's owned-server context removes the entire exact container with
    # -v, including any unfinished psql. A final bounded HTTP request may extend
    # the scheduling deadline; there is no attached socket read or log retrieval.
    raise OwnedPostgresError("Owned role bootstrap execution deadline exceeded")


@pytest.mark.parametrize("exit_code", [0, 3])
def test_exec_wait_returns_only_confirmed_exit_code(exit_code: int) -> None:
    server = Mock(spec=OwnedPostgres)
    server._lease = Mock()
    server.container_id = "owned-container"
    server._lease.client.exec_inspect.return_value = {
        "ContainerID": "owned-container",
        "Running": False,
        "ExitCode": exit_code,
    }
    assert _wait_for_exec(server, "owned-exec") == exit_code
    server._lease.verify.assert_called_once_with(server)
    server._lease.client.exec_inspect.assert_called_once_with("owned-exec")


def test_exec_wait_has_a_deadline_without_an_attached_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Mock(spec=OwnedPostgres)
    server._lease = Mock()
    server.container_id = "owned-container"
    server._lease.client.exec_inspect.return_value = {
        "ContainerID": "owned-container",
        "Running": True,
        "ExitCode": None,
    }
    ticks = iter([0.0, 0.0, 90.0, 90.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    with pytest.raises(OwnedPostgresError, match="execution deadline exceeded"):
        _wait_for_exec(server, "owned-exec")
    server._lease.verify.assert_called_once_with(server)
    server._lease.client.exec_inspect.assert_called_once_with("owned-exec")
    server._lease.client.exec_start.assert_not_called()


def test_exec_wait_refuses_another_container() -> None:
    server = Mock(spec=OwnedPostgres)
    server._lease = Mock()
    server.container_id = "owned-container"
    server._lease.client.exec_inspect.return_value = {
        "ContainerID": "unrelated-container",
        "Running": False,
        "ExitCode": 0,
    }
    with pytest.raises(OwnedPostgresError, match="exec identity changed"):
        _wait_for_exec(server, "owned-exec")


def test_exec_wait_polls_until_a_confirmed_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Mock(spec=OwnedPostgres)
    server._lease = Mock()
    server.container_id = "owned-container"
    server._lease.client.exec_inspect.side_effect = [
        {"ContainerID": "owned-container", "Running": True, "ExitCode": None},
        {"ContainerID": "owned-container", "Running": False, "ExitCode": 0},
    ]
    sleep = Mock()
    monkeypatch.setattr(time, "sleep", sleep)
    assert _wait_for_exec(server, "owned-exec") == 0
    assert server._lease.verify.call_count == 2
    assert server._lease.client.exec_inspect.call_count == 2
    sleep.assert_called_once_with(0.1)


def _role_snapshot(connection: psycopg.Connection) -> str:
    rows = connection.execute(
        "SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolcanlogin, "
        "rolreplication, rolbypassrls, rolpassword FROM pg_authid "
        "WHERE rolname IN ('ue_app', 'ue_worker', 'ue_rls_bypass', 'ue_migrator') "
        "ORDER BY rolname"
    ).fetchall()
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def test_bootstrap_scans_mixed_relation_kinds_without_wrong_object_type(
    role_server: OwnedPostgres,
) -> None:
    with _connect(role_server) as connection:
        connection.execute("CREATE TABLE public.kind_table (id bigint PRIMARY KEY)")
        connection.execute("CREATE SEQUENCE public.kind_sequence")
        connection.execute("CREATE VIEW public.kind_view AS SELECT 1 AS id")
        connection.execute(
            "CREATE MATERIALIZED VIEW public.kind_materialized AS SELECT 1 AS id"
        )
        connection.execute(
            "CREATE TABLE public.kind_partitioned (id bigint) PARTITION BY RANGE (id)"
        )
        connection.execute("CREATE TYPE public.kind_composite AS (id bigint)")
        kinds = connection.execute(
            "SELECT DISTINCT relkind FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relname LIKE 'kind_%'"
        ).fetchall()
        assert {kind for (kind,) in kinds} == {"r", "i", "S", "v", "m", "p", "c"}
        # Establish the exact PG17 error class the sequence predicate must avoid.
        with pytest.raises(psycopg.errors.WrongObjectType):
            connection.execute(
                "SELECT has_sequence_privilege(current_user, "
                "'public.kind_table'::regclass, 'UPDATE')"
            )
    assert _bootstrap(role_server) == 0
    assert _bootstrap(role_server) == 0


def test_bootstrap_converges_existing_and_future_dml_without_bypass(
    role_server: OwnedPostgres,
) -> None:
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        connection.execute("SET ROLE ue_migrator")
        connection.execute("CREATE TABLE public.role_probe (id bigint PRIMARY KEY)")
        connection.execute("CREATE SEQUENCE public.role_probe_sequence")
        connection.execute("RESET ROLE")
        connection.execute("GRANT ue_rls_bypass TO ue_app")
        connection.execute("ALTER ROLE ue_rls_bypass LOGIN SUPERUSER BYPASSRLS")
        connection.execute("GRANT ALL ON public.role_probe TO ue_app, ue_worker")
        connection.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator "
            "GRANT ALL ON TABLES TO ue_app, ue_worker"
        )
        connection.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public "
            "GRANT ALL ON SEQUENCES TO ue_app, ue_worker"
        )
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        connection.execute("SET ROLE ue_migrator")
        connection.execute("CREATE TABLE public.role_future (id bigint)")
        connection.execute("CREATE SEQUENCE public.role_future_sequence")
        connection.execute("RESET ROLE")
        roles = connection.execute(
            "SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
            "WHERE rolname IN ('ue_app', 'ue_worker', 'ue_rls_bypass') ORDER BY rolname"
        ).fetchall()
        assert roles == [
            ("ue_app", False, False, True),
            ("ue_rls_bypass", False, False, False),
            ("ue_worker", False, False, True),
        ]
        assert connection.execute(
            "SELECT pg_has_role('ue_app', 'ue_rls_bypass', 'MEMBER'), "
            "pg_has_role('ue_worker', 'ue_rls_bypass', 'MEMBER')"
        ).fetchone() == (False, True)
        assert connection.execute(
            "SELECT admin_option, inherit_option, set_option FROM pg_auth_members "
            "WHERE roleid = 'ue_rls_bypass'::regrole AND member = 'ue_worker'::regrole"
        ).fetchall() == [(False, True, False)]
        connection.execute("CREATE TABLE public.role_rows (id integer PRIMARY KEY)")
        connection.execute("INSERT INTO public.role_rows VALUES (1), (2)")
        connection.execute("ALTER TABLE public.role_rows ENABLE ROW LEVEL SECURITY")
        connection.execute("ALTER TABLE public.role_rows FORCE ROW LEVEL SECURITY")
        connection.execute(
            "CREATE POLICY role_scope ON public.role_rows USING "
            "(id = 1 OR pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER'))"
        )
        connection.execute("GRANT SELECT ON public.role_rows TO ue_app, ue_worker")
        connection.execute("SET ROLE ue_app")
        assert connection.execute(
            "SELECT id FROM public.role_rows ORDER BY id"
        ).fetchall() == [(1,)]
        connection.execute("RESET ROLE")
        connection.execute("SET SESSION AUTHORIZATION ue_worker")
        assert connection.execute(
            "SELECT id FROM public.role_rows ORDER BY id"
        ).fetchall() == [(1,), (2,)]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SET ROLE ue_rls_bypass")
        connection.execute("RESET SESSION AUTHORIZATION")
        for role in ("ue_app", "ue_worker"):
            for table in ("public.role_probe", "public.role_future"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    assert connection.execute(
                        "SELECT has_table_privilege(%s, %s, %s)",
                        (role, table, privilege),
                    ).fetchone() == (True,)
                assert connection.execute(
                    "SELECT has_table_privilege(%s, %s, "
                    "'TRUNCATE,REFERENCES,TRIGGER,MAINTAIN,SELECT WITH GRANT OPTION')",
                    (role, table),
                ).fetchone() == (False,)
            for sequence in (
                "public.role_probe_sequence",
                "public.role_future_sequence",
            ):
                assert connection.execute(
                    "SELECT has_sequence_privilege(%s, %s, 'UPDATE')",
                    (role, sequence),
                ).fetchone() == (False,)


@pytest.mark.parametrize(
    "drift",
    [
        "CREATE ROLE unexpected_parent; GRANT ue_rls_bypass TO unexpected_parent; "
        "GRANT unexpected_parent TO ue_app",
        "GRANT ue_migrator TO ue_app WITH INHERIT FALSE, SET TRUE",
        "CREATE ROLE unexpected_member; GRANT ue_worker TO unexpected_member",
        "GRANT ue_migrator TO ue_rls_bypass",
        "ALTER TABLE public.role_probe OWNER TO ue_app",
        "GRANT CREATE ON SCHEMA public TO PUBLIC",
        "GRANT TRUNCATE ON public.role_probe TO PUBLIC",
        "GRANT REFERENCES (id) ON public.role_probe TO PUBLIC",
        "CREATE SEQUENCE public.role_sequence; "
        "GRANT UPDATE ON public.role_sequence TO PUBLIC",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator "
        "GRANT TRUNCATE ON TABLES TO PUBLIC",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ue_migrator IN SCHEMA public "
        "GRANT UPDATE ON SEQUENCES TO ue_rls_bypass",
    ],
)
def test_bootstrap_refuses_unmanaged_authority_without_partial_changes(
    role_server: OwnedPostgres, drift: str
) -> None:
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        connection.execute("CREATE TABLE public.role_probe (id bigint)")
        connection.execute(drift)
        # A visible change before the guard must also roll back on refusal.
        connection.execute("ALTER ROLE ue_worker BYPASSRLS")
        before = _role_snapshot(connection)
    assert _bootstrap(role_server) != 0
    with _connect(role_server) as connection:
        assert _role_snapshot(connection) == before


def test_bootstrap_converges_direct_runtime_column_grants(
    role_server: OwnedPostgres,
) -> None:
    """A direct column grant to a managed runtime role is revoked, not refused.

    The bootstrap revokes all table-level runtime privileges first, and
    PostgreSQL clears column ACLs with that revoke. Only PUBLIC column grants,
    which the bootstrap cannot revoke, reach the refusal guard.
    """
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        connection.execute("CREATE TABLE public.role_probe (id bigint)")
        connection.execute("GRANT REFERENCES (id) ON public.role_probe TO ue_app")
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        assert connection.execute(
            "SELECT has_any_column_privilege('ue_app', 'public.role_probe', 'REFERENCES')"
        ).fetchone() == (False,)


_RUNTIME_TABLE_PRIVILEGES: dict[tuple[str, str], dict[str, bool]] = {
    ("ue_app", "public.data_access_logs"): {
        "INSERT": True,
        "SELECT": True,
        "DELETE": True,
        "UPDATE": False,
        "TRUNCATE": False,
    },
    ("ue_app", "public.data_access_logs_y2026m11"): {
        "INSERT": False,
        "SELECT": False,
        "UPDATE": False,
        "DELETE": False,
    },
    ("ue_app", "public.stored_events"): {
        "INSERT": True,
        "SELECT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    },
    ("ue_app", "public.tenants"): {
        "INSERT": True,
        "SELECT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    },
    ("ue_app", "public.alembic_version"): {
        "INSERT": False,
        "SELECT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    },
    ("ue_worker", "public.data_access_logs"): {
        "INSERT": True,
        "SELECT": True,
        "DELETE": True,
    },
    ("ue_worker", "public.stored_events"): {"INSERT": True, "SELECT": True},
    ("ue_worker", "public.tenants"): {
        "INSERT": False,
        "SELECT": True,
        "UPDATE": False,
        "DELETE": False,
    },
    ("ue_worker", "public.alembic_version"): {
        "INSERT": False,
        "UPDATE": False,
        "DELETE": False,
    },
}
_RUNTIME_COLUMN_PRIVILEGES: dict[tuple[str, str, str], bool] = {
    ("ue_app", "public.data_access_logs", "signature"): True,
    ("ue_app", "public.data_access_logs", "action"): False,
    ("ue_app", "public.stored_events", "processed_at"): True,
    ("ue_app", "public.stored_events", "status"): True,
    ("ue_app", "public.stored_events", "payload"): False,
}


def _create_runtime_tables(connection: psycopg.Connection) -> None:
    """Create the real table names the grants target, owned as Alembic owns them."""
    connection.execute("SET ROLE ue_migrator")
    connection.execute(
        "CREATE TABLE public.data_access_logs ("
        "id uuid NOT NULL, action text NOT NULL, signature text, "
        "created_at timestamptz NOT NULL, PRIMARY KEY (id, created_at)"
        ") PARTITION BY RANGE (created_at)"
    )
    connection.execute(
        "CREATE TABLE public.data_access_logs_y2026m11 PARTITION OF "
        "public.data_access_logs FOR VALUES FROM ('2026-11-01') TO ('2026-12-01')"
    )
    connection.execute(
        "CREATE TABLE public.stored_events (id uuid PRIMARY KEY, "
        "event_type text NOT NULL, payload jsonb NOT NULL, status text NOT NULL, "
        "processed_at timestamptz, error_count integer NOT NULL DEFAULT 0, "
        "last_error text)"
    )
    connection.execute(
        "CREATE TABLE public.tenants (id uuid PRIMARY KEY, name text NOT NULL, "
        "slug text NOT NULL, is_active boolean NOT NULL DEFAULT true)"
    )
    connection.execute(
        "INSERT INTO public.alembic_version (version_num) VALUES ('202611020000')"
    )
    connection.execute("RESET ROLE")


def _assert_runtime_privileges(connection: psycopg.Connection) -> None:
    for (role, table), expected in _RUNTIME_TABLE_PRIVILEGES.items():
        for privilege, granted in expected.items():
            assert connection.execute(
                "SELECT has_table_privilege(%s, %s, %s)", (role, table, privilege)
            ).fetchone() == (granted,), (role, table, privilege)
    for (role, table, column), granted in _RUNTIME_COLUMN_PRIVILEGES.items():
        assert connection.execute(
            "SELECT has_column_privilege(%s, %s, %s, 'UPDATE')",
            (role, table, column),
        ).fetchone() == (granted,), (role, table, column)


def test_first_bootstrap_owns_the_version_table_before_any_migration(
    role_server: OwnedPostgres,
) -> None:
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        assert connection.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class "
            "WHERE oid = 'public.alembic_version'::regclass"
        ).fetchone() == ("ue_migrator",)
        for role in ("ue_app", "ue_worker"):
            assert connection.execute(
                "SELECT has_table_privilege(%s, 'public.alembic_version', 'INSERT'), "
                "has_table_privilege(%s, 'public.alembic_version', 'UPDATE'), "
                "has_table_privilege(%s, 'public.alembic_version', 'DELETE')",
                (role, role, role),
            ).fetchone() == (False, False, False), role
        assert connection.execute(
            "SELECT has_table_privilege('ue_app', 'public.alembic_version', 'SELECT')"
        ).fetchone() == (True,)


def test_runtime_roles_can_only_write_the_rows_their_code_writes(
    role_server: OwnedPostgres,
) -> None:
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        _create_runtime_tables(connection)
    # The first start after the migrations reconverges tables the migration created.
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        _assert_runtime_privileges(connection)

        connection.execute("SET ROLE ue_app")
        connection.execute(
            "INSERT INTO public.data_access_logs VALUES "
            "('00000000-0000-4000-8000-000000000001', 'probe', NULL, "
            "'2026-11-03T00:00:00Z')"
        )
        # The signature write-back is the one UPDATE the backend performs.
        assert (
            connection.execute(
                "UPDATE public.data_access_logs SET signature = 'sig' "
                "WHERE action = 'probe'"
            ).rowcount
            == 1
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE public.data_access_logs SET action = 'tampered' "
                "WHERE action = 'probe'"
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM public.data_access_logs_y2026m11")
        # The backend's retention prune deletes through the parent table.
        connection.execute(
            "DELETE FROM public.data_access_logs WHERE created_at < '2000-01-01'"
        )

        connection.execute(
            "INSERT INTO public.stored_events (id, event_type, payload, status) "
            "VALUES ('00000000-0000-4000-8000-000000000002', 'e', '{}', 'pending')"
        )
        assert (
            connection.execute(
                "UPDATE public.stored_events SET processed_at = now(), "
                "error_count = 1, last_error = 'x', status = 'failed' "
                "WHERE id = '00000000-0000-4000-8000-000000000002'"
            ).rowcount
            == 1
        )
        assert (
            connection.execute(
                "SELECT id FROM public.stored_events FOR UPDATE SKIP LOCKED LIMIT 1"
            ).rowcount
            == 1
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE public.stored_events SET payload = '{}'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM public.stored_events")

        connection.execute("SELECT count(*) FROM public.tenants")
        connection.execute(
            "INSERT INTO public.tenants (id, name, slug) "
            "VALUES ('00000000-0000-4000-8000-000000000003', 'n', 's')"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE public.tenants SET name = 'x'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM public.tenants")

        assert connection.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchall() == [("202611020000",)]
        for statement in (
            "INSERT INTO public.alembic_version VALUES ('forged')",
            "UPDATE public.alembic_version SET version_num = 'forged'",
            "DELETE FROM public.alembic_version",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
        connection.execute("RESET ROLE")

        connection.execute("SET ROLE ue_worker")
        connection.execute("DELETE FROM public.data_access_logs WHERE false")
        connection.execute(
            "INSERT INTO public.stored_events (id, event_type, payload, status) "
            "VALUES ('00000000-0000-4000-8000-000000000004', 'e', '{}', 'pending')"
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE public.tenants SET name = 'x'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO public.tenants (id, name, slug) "
                "VALUES ('00000000-0000-4000-8000-000000000005', 'n', 's')"
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE public.alembic_version SET version_num = 'x'")
        connection.execute("RESET ROLE")


def test_bootstrap_reverts_widened_append_only_grants(
    role_server: OwnedPostgres,
) -> None:
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        _create_runtime_tables(connection)
        connection.execute(
            "GRANT ALL ON public.data_access_logs, public.stored_events, "
            "public.tenants, public.alembic_version TO ue_app, ue_worker"
        )
        connection.execute("GRANT UPDATE ON public.data_access_logs TO ue_app")
    assert _bootstrap(role_server) == 0
    with _connect(role_server) as connection:
        _assert_runtime_privileges(connection)
