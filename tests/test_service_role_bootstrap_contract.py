"""Static contract for the SpiceDB and Temporal login roles and their bootstrap.

These are source contracts. The behavioural proof on a real PostgreSQL 17 server is
in test_service_role_bootstrap_postgres.py; these tests keep the SQL, the wrapper and
the psql variable wiring from drifting apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLES_DIR = ROOT / "infrastructure" / "postgres-roles"
SERVICE_SQL = ROLES_DIR / "bootstrap-service-roles.sql"
ENVIRONMENT_SQL = ROLES_DIR / "bootstrap-from-environment.sql"
WRAPPER = ROLES_DIR / "run-bootstrap.sh"

SERVICE_ROLES = ("ue_spicedb", "ue_temporal")
REQUIRED_ATTRIBUTES = {
    "LOGIN",
    "NOSUPERUSER",
    "NOCREATEDB",
    "NOCREATEROLE",
    "NOREPLICATION",
    "NOBYPASSRLS",
}
SERVICE_DATABASE_OWNERS = {
    "spicedb": "ue_spicedb",
    "temporal": "ue_temporal",
    "temporal_visibility": "ue_temporal",
}


def _service_sql() -> str:
    return SERVICE_SQL.read_text(encoding="utf-8")


def test_each_service_role_is_created_with_only_the_login_attributes() -> None:
    source = _service_sql()
    for role in SERVICE_ROLES:
        match = re.search(
            rf"ALTER ROLE {role} WITH ([A-Z ]+?) PASSWORD :'\w+';", source
        )
        assert match is not None, role
        attributes = set(match.group(1).split())
        assert attributes == REQUIRED_ATTRIBUTES, role
        assert "SUPERUSER" not in attributes - {"NOSUPERUSER"}, role
        assert "BYPASSRLS" not in attributes - {"NOBYPASSRLS"}, role


def test_service_roles_are_never_granted_membership_or_bypass() -> None:
    source = _service_sql()
    assert "GRANT ue_rls_bypass" not in source
    assert "ue_rls_bypass" not in source
    assert "GRANT ue_app" not in source
    assert "GRANT ue_migrator" not in source
    assert "GRANT ue_worker" not in source


def test_service_databases_are_owned_by_their_role_and_closed_to_public() -> None:
    source = _service_sql()
    for database, owner in SERVICE_DATABASE_OWNERS.items():
        assert f"('{database}', '{owner}')" in source, database
    assert "ALTER DATABASE %I OWNER TO %I" in source
    assert "REVOKE CONNECT ON DATABASE %I FROM PUBLIC" in source
    assert "GRANT ALL ON DATABASE %I TO %I" in source


def test_application_and_maintenance_databases_are_closed_to_public() -> None:
    source = _service_sql()
    assert 'REVOKE CONNECT ON DATABASE :"db" FROM PUBLIC;' in source
    assert "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;" in source


def test_missing_service_database_is_a_hard_error_not_a_skip() -> None:
    source = _service_sql()
    assert "RAISE EXCEPTION 'Service database %" in source
    assert (
        "IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = target.database_name)"
        in source
    )


def test_relation_ownership_is_reassigned_only_from_the_bootstrap_session() -> None:
    source = _service_sql()
    assert source.count(
        "class.relowner = (SELECT oid FROM pg_roles WHERE rolname = session_user)"
    ) == len(SERVICE_DATABASE_OWNERS)
    for database in SERVICE_DATABASE_OWNERS:
        assert f"\\c {database}\n" in source, database


@pytest.mark.parametrize(
    ("output", "exit_code", "expected"),
    [
        ("[postgres-roles-init] phase=reconcile exit=3 sqlstate=42704\n", 3, "42704"),
        ("[postgres-roles-init] phase=reconcile exit=3 sqlstate=P0001\n", 3, "P0001"),
        (
            "[postgres-roles-init] phase=reconcile exit=3 sqlstate=42704 extra\n",
            3,
            "UNKNOWN",
        ),
        (
            "[postgres-roles-init] phase=reconcile exit=3 sqlstate=42704\nprivate input",
            3,
            "UNKNOWN",
        ),
        ("[postgres-roles-init] phase=reconcile exit=2 sqlstate=42704\n", 3, "UNKNOWN"),
        (None, 3, "UNKNOWN"),
    ],
)
def test_bootstrap_diagnostic_accepts_only_matching_safe_sqlstate(
    output: str | None, exit_code: int, expected: str
) -> None:
    from tests.test_service_role_bootstrap_postgres import _safe_bootstrap_sqlstate

    assert _safe_bootstrap_sqlstate(output, exit_code) == expected


def test_service_file_runs_after_the_application_roles_in_the_same_session() -> None:
    environment = ENVIRONMENT_SQL.read_text(encoding="utf-8")
    app_include = environment.index("\\ir bootstrap-app-roles.sql")
    service_include = environment.index("\\ir bootstrap-service-roles.sql")
    assert app_include < service_include


def test_environment_script_reads_both_service_passwords() -> None:
    environment = ENVIRONMENT_SQL.read_text(encoding="utf-8")
    assert "\\getenv spicedb_password UE_SPICEDB_DB_PASSWORD" in environment
    assert "\\getenv temporal_password UE_TEMPORAL_DB_PASSWORD" in environment


def test_wrapper_loads_service_passwords_as_file_or_env_secrets() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "load_secret UE_SPICEDB_DB_PASSWORD" in wrapper
    assert "load_secret UE_TEMPORAL_DB_PASSWORD" in wrapper


def test_wrapper_projects_sqlstate_from_both_bootstrap_files() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "'psql:/bootstrap/bootstrap-'*'.sql:'*)" in wrapper
    assert "remainder=${record#psql:/bootstrap/bootstrap-*.sql:}" in wrapper


def test_password_sql_keeps_statement_logging_suppressed() -> None:
    source = _service_sql()
    for setting in (
        "SET LOCAL log_statement = 'none';",
        "SET LOCAL log_min_error_statement = 'panic';",
        "SET LOCAL log_parameter_max_length_on_error = 0;",
    ):
        assert setting in source
