"""Production-shaped runtime login for PostgreSQL row-level security tests.

The grants mirror infrastructure/postgres-roles/bootstrap-app-roles.sql for a
runtime login: table-wide DML, narrowed tenant and event tables, no DDL,
TRUNCATE, REFERENCES or TRIGGER, and no ue_rls_bypass membership. The hosted
integration database user is a superuser and bypasses RLS, so RLS tests must
connect as a role built here. Used by the integration RLS tests and by
tests/integration/test_chat_send_nosuperuser_rls_postgres.py.
"""

from __future__ import annotations

_ROLE_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"


def runtime_role_statements(role: str, password: str) -> tuple[str, ...]:
    """Return idempotent statements that (re)build the runtime login role.

    ``role`` and ``password`` are fixed test constants; the role name must be a
    plain identifier because it is interpolated without quoting.
    """
    if not role.isidentifier() or not role.islower():
        raise ValueError("runtime role name must be a lowercase identifier")
    if "'" in password:
        raise ValueError("runtime role password must not contain quotes")
    return (
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles "
        f"WHERE rolname = '{role}') THEN CREATE ROLE {role} {_ROLE_ATTRIBUTES} "
        f"PASSWORD '{password}'; END IF; END $$",
        f"ALTER ROLE {role} {_ROLE_ATTRIBUTES} PASSWORD '{password}'",
        # Revoke first, as the bootstrap does, so a privilege granted by an
        # earlier local run cannot survive into the production shape.
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}",
        f"GRANT USAGE ON SCHEMA public TO {role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
        f"REVOKE UPDATE, DELETE, TRUNCATE ON public.tenants FROM {role}",
        f"REVOKE UPDATE, DELETE, TRUNCATE ON public.stored_events FROM {role}",
        f"GRANT UPDATE (processed_at, error_count, last_error, status) "
        f"ON public.stored_events TO {role}",
    )


RUNTIME_ROLE_FLAGS_QUERY = (
    "SELECT rolsuper, rolbypassrls, "
    "pg_has_role(rolname, 'ue_rls_bypass', 'MEMBER') FROM pg_roles "
    "WHERE rolname = :role"
)
