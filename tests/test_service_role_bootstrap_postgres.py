"""SpiceDB and Temporal login roles on a disposable PostgreSQL 17 server.

Each case owns a fresh server, because role and database changes are cluster-wide.
The real bootstrap SQL runs through psql, as the one-shot roles job does: the
application roles first, then the service roles. Every role logs in with its own
random password, so each assertion exercises a real authenticated session.
"""

from __future__ import annotations

import io
import re
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

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
from tests.test_app_db_role_bootstrap_postgres import (
    _connect,
    _wait_for_exec,
)

pytestmark = [pytest.mark.integration, pytest.mark.timeout(300)]

ROOT = Path(__file__).resolve().parents[1]
_ROLES_DIR = ROOT / "infrastructure" / "postgres-roles"
APP_DATABASE = "university_app"
SERVICE_DATABASES = {
    "spicedb": "ue_spicedb",
    "temporal": "ue_temporal",
    "temporal_visibility": "ue_temporal",
}
SERVICE_ROLES = ("ue_spicedb", "ue_temporal")
RUNTIME_ROLES = ("ue_app", "ue_worker", "ue_migrator")
_PASSWORD_VARIABLES = {
    "ue_migrator": "UE_MIGRATOR_DB_PASSWORD",
    "ue_app": "UE_APP_DB_PASSWORD",
    "ue_worker": "UE_WORKER_DB_PASSWORD",
    "ue_spicedb": "UE_SPICEDB_DB_PASSWORD",
    "ue_temporal": "UE_TEMPORAL_DB_PASSWORD",
}


@pytest.fixture
def service_server(request: pytest.FixtureRequest) -> Iterator[OwnedPostgres]:
    request.getfixturevalue("default_database_guard")
    with owned_postgres_server() as server:
        yield server


class BootstrapResult(NamedTuple):
    exit_code: int
    sqlstate: str


def _safe_bootstrap_sqlstate(output: str | None, exit_code: int) -> str:
    """Accept only the wrapper's exact, independently matched SQLSTATE record."""
    if output is None:
        return "UNKNOWN"
    match = re.fullmatch(
        r"\[postgres-roles-init\] phase=reconcile exit=([0-9]{1,3}) "
        r"sqlstate=([A-Z0-9]{5}|UNKNOWN)\n?",
        output,
    )
    if match is None or int(match.group(1)) != exit_code:
        return "UNKNOWN"
    return match.group(2)


def _run_roles_bootstrap(
    server: OwnedPostgres,
    passwords: dict[str, str],
    *,
    bootstrap_user: str = "baseline_admin",
) -> BootstrapResult:
    """Run the production wrapper in the disposable server with safe diagnostics."""
    server._lease.verify(server)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        directory = tarfile.TarInfo("bootstrap")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        tar.addfile(directory)
        for filename in (
            "bootstrap-from-environment.sql",
            "bootstrap-app-roles.sql",
            "bootstrap-service-roles.sql",
            "run-bootstrap.sh",
        ):
            source = (_ROLES_DIR / filename).read_bytes()
            member = tarfile.TarInfo(f"bootstrap/{filename}")
            member.size = len(source)
            member.mode = 0o600
            tar.addfile(member, io.BytesIO(source))
    client = server._lease.client
    assert _docker_call(
        lambda: client.put_archive(server.container_id, "/", archive.getvalue()),
        "service role bootstrap source staging",
    )
    diagnostic_path = (
        f"/var/lib/postgresql/service-role-bootstrap-{uuid4().hex}.diagnostic"
    )
    environment = {
        "PGHOST": "/var/run/postgresql",
        "PGPORT": "5432",
        "PGCONNECT_TIMEOUT": "5",
        "PGUSER": bootstrap_user,
        "PGPASSWORD": uuid4().hex,
        "POSTGRES_DB": APP_DATABASE,
    }
    for role, variable in _PASSWORD_VARIABLES.items():
        environment[variable] = passwords.get(role, uuid4().hex)
    execution = _docker_call(
        lambda: client.exec_create(
            server.container_id,
            cmd=[
                "sh",
                "-c",
                "umask 022; /bin/sh /bootstrap/run-bootstrap.sh "
                f">/dev/null 2>{diagnostic_path}; exit $?",
            ],
            environment=environment,
            user="root",
        ),
        "service role bootstrap exec creation",
    )
    execution_id = execution.get("Id")
    if (
        not isinstance(execution_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", execution_id) is None
    ):
        raise OwnedPostgresError("Service role bootstrap exec identity unacknowledged")
    admitted = _docker_call(
        lambda: client.exec_inspect(execution_id),
        "service role bootstrap exec admission",
    )
    if (
        admitted.get("ContainerID") != server.container_id
        or admitted.get("Running") is not False
    ):
        raise OwnedPostgresError("Service role bootstrap exec identity mismatch")
    server._lease.verify(server)
    _docker_call(
        lambda: client.exec_start(execution_id, detach=True),
        "service role bootstrap detached execution",
    )
    exit_code = _wait_for_exec(server, execution_id)
    if exit_code == 0:
        return BootstrapResult(exit_code, "UNKNOWN")
    # The production wrapper projects psql stderr to a SQLSTATE-only record.
    # Read a bounded prefix through PostgreSQL, and never expose unrecognized text.
    try:
        with _connect(server) as admin:
            row = admin.execute(
                "SELECT pg_read_file(%s, 0, 512, true)", (diagnostic_path,)
            ).fetchone()
    except psycopg.Error:
        row = None
    output = row[0] if row is not None and isinstance(row[0], str) else None
    return BootstrapResult(exit_code, _safe_bootstrap_sqlstate(output, exit_code))


def _create_databases(server: OwnedPostgres) -> None:
    """Create what postgres-databases-init creates, plus the application database."""
    with _connect(server) as admin:
        for database in (APP_DATABASE, *SERVICE_DATABASES):
            admin.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
            )


def _provision(server: OwnedPostgres) -> dict[str, str]:
    _create_databases(server)
    passwords = {role: uuid4().hex + uuid4().hex for role in _PASSWORD_VARIABLES}
    result = _run_roles_bootstrap(server, passwords)
    assert result.exit_code == 0, f"bootstrap failed: {result}"
    return passwords


def _login(
    server: OwnedPostgres, role: str, password: str, database: str
) -> psycopg.Connection:
    server._lease.verify(server)
    return psycopg.connect(
        host=server.url.host,
        port=server.url.port,
        user=role,
        password=password,
        dbname=database,
        connect_timeout=5,
        options="-c lock_timeout=10s -c statement_timeout=60s",
        autocommit=True,
    )


def test_service_roles_carry_no_superuser_bypass_or_membership(
    service_server: OwnedPostgres,
) -> None:
    _provision(service_server)
    with _connect(service_server) as admin:
        rows = admin.execute(
            "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls FROM pg_roles "
            "WHERE rolname = ANY(%s) ORDER BY rolname",
            (list(SERVICE_ROLES),),
        ).fetchall()
        memberships = admin.execute(
            "SELECT count(*) FROM pg_auth_members AS edge "
            "JOIN pg_roles AS member ON member.oid = edge.member "
            "JOIN pg_roles AS granted ON granted.oid = edge.roleid "
            "WHERE member.rolname = ANY(%s) OR granted.rolname = ANY(%s)",
            (list(SERVICE_ROLES), list(SERVICE_ROLES)),
        ).fetchone()
    assert rows == [
        ("ue_spicedb", True, False, False, False, False, False),
        ("ue_temporal", True, False, False, False, False, False),
    ]
    assert memberships == (0,)


def test_each_service_role_owns_only_its_databases(
    service_server: OwnedPostgres,
) -> None:
    _provision(service_server)
    with _connect(service_server) as admin:
        owners: dict[str, str] = dict(
            admin.execute(
                "SELECT datname, pg_get_userbyid(datdba) FROM pg_database "
                "WHERE datname = ANY(%s)",
                (list(SERVICE_DATABASES),),
            ).fetchall()
        )
    assert owners == {
        "spicedb": "ue_spicedb",
        "temporal": "ue_temporal",
        "temporal_visibility": "ue_temporal",
    }


@pytest.mark.parametrize(
    ("role", "database"),
    [
        ("ue_spicedb", "spicedb"),
        ("ue_temporal", "temporal"),
        ("ue_temporal", "temporal_visibility"),
    ],
)
def test_service_role_creates_tables_in_its_own_database(
    service_server: OwnedPostgres, role: str, database: str
) -> None:
    passwords = _provision(service_server)
    with _login(service_server, role, passwords[role], database) as session:
        session.execute("CREATE TABLE public.service_probe (id integer)")
        session.execute("DROP TABLE public.service_probe")


def test_temporal_visibility_can_install_its_trusted_extension(
    service_server: OwnedPostgres,
) -> None:
    """The visibility schema installs btree_gin, which needs CREATE on its database."""
    passwords = _provision(service_server)
    with _login(
        service_server, "ue_temporal", passwords["ue_temporal"], "temporal_visibility"
    ) as session:
        session.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
        extension_owner = session.execute(
            "SELECT extowner::regrole::text FROM pg_extension WHERE extname = 'btree_gin'"
        ).fetchone()
    assert extension_owner == ("ue_temporal",)


_DENIED = [
    ("ue_spicedb", "temporal"),
    ("ue_spicedb", "temporal_visibility"),
    ("ue_spicedb", APP_DATABASE),
    ("ue_spicedb", "postgres"),
    ("ue_temporal", "spicedb"),
    ("ue_temporal", APP_DATABASE),
    ("ue_temporal", "postgres"),
]


@pytest.mark.parametrize(("role", "database"), _DENIED)
def test_service_role_cannot_connect_to_another_database(
    service_server: OwnedPostgres, role: str, database: str
) -> None:
    passwords = _provision(service_server)
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        _login(service_server, role, passwords[role], database).close()


def test_runtime_application_login_still_reaches_the_application_database(
    service_server: OwnedPostgres,
) -> None:
    """Revoking PUBLIC CONNECT must not cut off the roles that the app grants name."""
    passwords = _provision(service_server)
    with _login(service_server, "ue_app", passwords["ue_app"], APP_DATABASE) as session:
        assert session.execute("SELECT current_user").fetchone() == ("ue_app",)
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        _login(service_server, "ue_app", passwords["ue_app"], "spicedb").close()


def test_service_login_is_not_a_superuser(service_server: OwnedPostgres) -> None:
    passwords = _provision(service_server)
    with _login(service_server, "ue_spicedb", passwords["ue_spicedb"], "spicedb") as s:
        assert s.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (False, False)


def test_legacy_service_relations_follow_the_database_owner(
    service_server: OwnedPostgres,
) -> None:
    """Relations created by the superuser before this change are reassigned."""
    _create_databases(service_server)
    # The superuser created these relations in the spicedb database before the
    # service roles existed, as on a pre-existing volume.
    with psycopg.connect(
        host=service_server.url.host,
        port=service_server.url.port,
        user=service_server.url.username,
        password=service_server.url.password,
        dbname="spicedb",
        autocommit=True,
    ) as legacy:
        legacy.execute("CREATE TABLE public.legacy_marker (id integer)")
        legacy.execute("CREATE SEQUENCE public.legacy_seq")
        legacy.execute('CREATE ROLE "unrelated_owner" NOLOGIN')
        legacy.execute('CREATE TABLE public."Unrelated Marker" (id integer)')
        legacy.execute(
            'ALTER TABLE public."Unrelated Marker" OWNER TO "unrelated_owner"'
        )
    passwords = {role: uuid4().hex + uuid4().hex for role in _PASSWORD_VARIABLES}
    result = _run_roles_bootstrap(service_server, passwords)
    assert result.exit_code == 0, f"bootstrap failed: {result}"
    with _login(service_server, "ue_spicedb", passwords["ue_spicedb"], "spicedb") as s:
        owners: dict[str, str] = dict(
            s.execute(
                "SELECT relname, pg_get_userbyid(relowner) FROM pg_class AS c "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND relname IN "
                "('legacy_marker', 'legacy_seq', 'Unrelated Marker') ORDER BY relname"
            ).fetchall()
        )
    assert owners == {
        "legacy_marker": "ue_spicedb",
        "legacy_seq": "ue_spicedb",
        "Unrelated Marker": "unrelated_owner",
    }


def test_quoted_bootstrap_login_reassigns_only_its_own_service_relations(
    service_server: OwnedPostgres,
) -> None:
    """Mixed-case and punctuation in the actual login must not change authority."""
    _create_databases(service_server)
    bootstrap_user = "Bootstrap-Owner"
    with _connect(service_server) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN SUPERUSER").format(
                sql.Identifier(bootstrap_user)
            )
        )
    for database in SERVICE_DATABASES:
        with psycopg.connect(
            host=service_server.url.host,
            port=service_server.url.port,
            user=service_server.url.username,
            password=service_server.url.password,
            dbname=database,
            autocommit=True,
        ) as legacy:
            legacy.execute('CREATE TABLE public."Quoted Owner Table" (id integer)')
            legacy.execute('CREATE SEQUENCE public."Quoted Owner Sequence"')
            legacy.execute("CREATE TABLE public.unrelated_owner_marker (id integer)")
            for relation_type, name in (
                ("TABLE", "Quoted Owner Table"),
                ("SEQUENCE", "Quoted Owner Sequence"),
            ):
                legacy.execute(
                    sql.SQL("ALTER {} public.{} OWNER TO {}").format(
                        sql.SQL(relation_type),
                        sql.Identifier(name),
                        sql.Identifier(bootstrap_user),
                    )
                )
    passwords = {role: uuid4().hex + uuid4().hex for role in _PASSWORD_VARIABLES}
    result = _run_roles_bootstrap(
        service_server, passwords, bootstrap_user=bootstrap_user
    )
    assert result.exit_code == 0, f"bootstrap failed: {result}"
    for database, owner in SERVICE_DATABASES.items():
        with _login(service_server, owner, passwords[owner], database) as session:
            owners: dict[str, str] = dict(
                session.execute(
                    "SELECT relname, pg_get_userbyid(relowner) FROM pg_class AS c "
                    "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND relname IN "
                    "('Quoted Owner Table', 'Quoted Owner Sequence', "
                    "'unrelated_owner_marker')"
                ).fetchall()
            )
        assert owners == {
            "Quoted Owner Table": owner,
            "Quoted Owner Sequence": owner,
            "unrelated_owner_marker": "baseline_admin",
        }


def test_rerun_restores_the_owner_database_privilege(
    service_server: OwnedPostgres,
) -> None:
    """A database ACL stripped of CREATE is repaired by the next reconciliation."""
    passwords = _provision(service_server)
    with _connect(service_server) as admin:
        admin.execute("REVOKE CREATE ON DATABASE temporal_visibility FROM ue_temporal")
    result = _run_roles_bootstrap(service_server, passwords)
    assert result.exit_code == 0, f"bootstrap failed: {result}"
    with _login(
        service_server, "ue_temporal", passwords["ue_temporal"], "temporal_visibility"
    ) as session:
        session.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")


def test_missing_service_database_fails_closed(service_server: OwnedPostgres) -> None:
    """The reconciliation never skips a service database; it stops with an error."""
    passwords = _provision(service_server)
    with _connect(service_server) as admin:
        admin.execute("DROP DATABASE temporal_visibility")
    result = _run_roles_bootstrap(service_server, passwords)
    assert result.exit_code != 0
    assert result.sqlstate == "P0001"
    with _connect(service_server) as admin:
        admin.execute("CREATE DATABASE temporal_visibility")
    result = _run_roles_bootstrap(service_server, passwords)
    assert result.exit_code == 0, f"bootstrap failed: {result}"
