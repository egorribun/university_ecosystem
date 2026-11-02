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
        "GRANT REFERENCES (id) ON public.role_probe TO ue_app",
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
