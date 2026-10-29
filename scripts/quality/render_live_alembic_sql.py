"""Render the DDL one changed Alembic revision runs against live PostgreSQL.

Offline ``alembic upgrade --sql`` has no database inspector, so inspector-guarded
branches (drop guards) render nothing and Squawk cannot lint them (AUD-208). This
renderer migrates a throwaway database to the revision's parent, then records the
DDL that the revision itself executes against that live state. A fresh template0
database is dropped only after CREATE acknowledgement and identity confirmation.
The caller must supply an owned, quiescent CI service; uncertain ownership never
authorizes cleanup, and the limited catalog probe is not arbitrary-server admission.

Usage: ``python -m scripts.quality.render_live_alembic_sql MIGRATION OUTPUT_SQL``
with ``DATABASE_URL`` pointing at a PostgreSQL server the caller may create
databases on.
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

from alembic import command
from scripts.quality.read_alembic_revision import (
    RevisionMetadataError,
    read_revision_metadata,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SQL_OPERATION = re.compile(
    r"^(CREATE|ALTER|DROP|COMMENT|GRANT|REVOKE|TRUNCATE|RENAME|SET|LOCK|"
    r"INSERT|UPDATE|DELETE|MERGE)\b",
    re.IGNORECASE,
)
_DDL_OPERATIONS = {
    "CREATE",
    "ALTER",
    "DROP",
    "COMMENT",
    "GRANT",
    "REVOKE",
    "TRUNCATE",
    "RENAME",
    "SET",
}
_PARAMETERIZED_DML_NOTE = (
    "-- observed parameterized DML template; non-DDL observation only, "
    "Squawk does not analyze DML; bound values are intentionally omitted"
)
_ADMIN_CONNECT_ATTEMPTS = 30

_SCRATCH_IDENTITY_SQL = """
SELECT d.oid, d.datname, d.datdba, r.oid AS current_role_oid
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_roles AS r ON r.rolname = current_user
WHERE d.datname = :scratch
LIMIT 2
"""
_SCRATCH_CATALOG_SQL = """
WITH user_namespaces AS (
    SELECT oid, nspname
    FROM pg_catalog.pg_namespace
    WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
)
SELECT 'schema' AS kind, NULL::text AS nspname, nspname AS objname
FROM user_namespaces
UNION ALL
SELECT 'relation', n.nspname, c.relname
FROM pg_catalog.pg_class AS c
JOIN user_namespaces AS n ON n.oid = c.relnamespace
UNION ALL
SELECT 'routine', n.nspname, p.proname
FROM pg_catalog.pg_proc AS p
JOIN user_namespaces AS n ON n.oid = p.pronamespace
UNION ALL
SELECT 'type', n.nspname, t.typname
FROM pg_catalog.pg_type AS t
JOIN user_namespaces AS n ON n.oid = t.typnamespace
UNION ALL
SELECT 'extension', n.nspname, e.extname
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n ON n.oid = e.extnamespace
LIMIT 3
"""
_TEMPLATE0_CATALOG_BASELINE = frozenset(
    {("schema", None, "public"), ("extension", "pg_catalog", "plpgsql")}
)


class LiveRenderError(RuntimeError):
    """Raised when the live rendering cannot complete."""


class _DdlRecorder:
    """Collect lintable DDL and safety context from the active migration."""

    def __init__(self) -> None:
        self.active = False
        self.statements: list[str] = []

    @staticmethod
    def _first_operation(statement: str) -> str | None:
        """Return the first SQL verb after leading line or block comments."""
        remaining = statement
        while True:
            remaining = remaining.lstrip()
            if remaining.startswith("--"):
                newline = remaining.find("\n")
                if newline < 0:
                    return None
                remaining = remaining[newline + 1 :]
                continue
            if remaining.startswith("/*"):
                comment_end = remaining.find("*/", 2)
                if comment_end < 0:
                    return None
                remaining = remaining[comment_end + 2 :]
                continue
            match = _SQL_OPERATION.match(remaining)
            return match.group(1).upper() if match else None

    def _record_transaction_event(self, name: str, sql: str) -> None:
        if self.active:
            self.statements.append(
                "-- observed SQLAlchemy "
                f"{name} event; transaction-event representation, not cursor text\n"
                f"{sql}"
            )

    def _on_begin(self, _connection: object) -> None:
        self._record_transaction_event("begin", "BEGIN")

    def _on_commit(self, _connection: object) -> None:
        self._record_transaction_event("commit", "COMMIT")

    def _on_rollback(self, _connection: object) -> None:
        self._record_transaction_event("rollback", "ROLLBACK")

    def event_listeners(self) -> tuple[tuple[str, Callable[..., object]], ...]:
        """Return stable listener pairs for registration and cleanup."""
        return (
            ("before_cursor_execute", self),
            ("begin", self._on_begin),
            ("commit", self._on_commit),
            ("rollback", self._on_rollback),
        )

    def __call__(
        self,
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if not self.active:
            return

        operation = self._first_operation(statement)
        if operation is None:
            return

        if operation in _DDL_OPERATIONS or operation == "LOCK":
            self.statements.append(statement.strip())
            return

        if operation not in {"INSERT", "UPDATE", "DELETE", "MERGE"}:
            return

        compiled = getattr(context, "compiled", None)
        compiled_binds = getattr(compiled, "binds", {})
        has_bound_parameters = bool(compiled_binds) or bool(parameters) or executemany
        if not has_bound_parameters:
            # The heap-to-partitioned copy is a parameter-free INSERT. Keep it
            # executable in the lint stream so its actual order remains visible.
            self.statements.append(statement.strip())
            return

        statement_lines = statement.strip().splitlines()
        self.statements.append(
            _PARAMETERIZED_DML_NOTE
            + "\n"
            + "\n".join(f"-- {line}" for line in statement_lines)
        )


def _checked_database_url(database_url: str | sa.URL) -> sa.URL:
    try:
        url = make_url(database_url)
    except (sa.exc.ArgumentError, ValueError):
        raise LiveRenderError("PostgreSQL database URL is invalid") from None
    if url.get_backend_name() != "postgresql":
        raise LiveRenderError("PostgreSQL database URL is invalid")
    if "dbname" in url.query:
        raise LiveRenderError("PostgreSQL database URL cannot override dbname")
    return url


def _admin_engine(database_url: str) -> sa.Engine:
    url = _checked_database_url(database_url).set(drivername="postgresql+psycopg")
    try:
        return sa.create_engine(
            url,
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": 5},
        )
    except sa.exc.SQLAlchemyError:
        raise LiveRenderError("PostgreSQL admin connection failed") from None


def _connect_admin(database_url: str) -> sa.Engine:
    """Wait for the CI PostgreSQL service, which may still be starting."""

    engine = _admin_engine(database_url)
    connected = False
    try:
        for _ in range(_ADMIN_CONNECT_ATTEMPTS):
            try:
                with engine.connect():
                    pass
            except sa.exc.OperationalError:
                time.sleep(1)
            else:
                connected = True
                return engine
        raise LiveRenderError("PostgreSQL admin connection failed")
    except sa.exc.SQLAlchemyError:
        raise LiveRenderError("PostgreSQL admin connection failed") from None
    finally:
        if not connected:
            # The connection attempt already fails; never expose driver data.
            with suppress(sa.exc.SQLAlchemyError):
                engine.dispose()


def _scratch_identity(admin: sa.Engine, scratch: str) -> tuple[int, str, int, int]:
    try:
        with admin.connect() as connection:
            rows = (
                connection.execute(sa.text(_SCRATCH_IDENTITY_SQL), {"scratch": scratch})
                .mappings()
                .all()
            )
    except sa.exc.SQLAlchemyError:
        raise LiveRenderError("PostgreSQL scratch identity check failed") from None
    if len(rows) != 1:
        raise LiveRenderError("PostgreSQL scratch identity check failed")
    row = rows[0]
    if not isinstance(row, Mapping) or set(row) != {
        "oid",
        "datname",
        "datdba",
        "current_role_oid",
    }:
        raise LiveRenderError("PostgreSQL scratch identity check failed")
    oid, name = row["oid"], row["datname"]
    owner, role = row["datdba"], row["current_role_oid"]
    if (
        any(
            type(value) is not int or not 0 < value < 2**32
            for value in (oid, owner, role)
        )
        or not isinstance(name, str)
        or name != scratch
        or owner != role
    ):
        raise LiveRenderError("PostgreSQL scratch identity check failed")
    return oid, name, owner, role


def _assert_empty_scratch_catalog(database_url: str | sa.URL) -> None:
    """Check five catalog surfaces on an already-owned, quiescent scratch DB.

    The exact built-in pg_catalog/information_schema/pg_toast contents are
    trusted under the fresh template0 CI-service prerequisite. This is not
    pristine-catalog admission for arbitrary or compromised servers, nor a
    complete inventory of every PostgreSQL object class.
    """
    url = _checked_database_url(database_url).set(drivername="postgresql+psycopg")
    engine = None
    try:
        engine = sa.create_engine(
            url,
            isolation_level="AUTOCOMMIT",
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as connection:
            rows = connection.execute(sa.text(_SCRATCH_CATALOG_SQL)).mappings().all()
        entries: set[tuple[str, str | None, str]] = set()
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {
                "kind",
                "nspname",
                "objname",
            }:
                raise LiveRenderError("PostgreSQL scratch catalog check failed")
            kind, namespace, name = row["kind"], row["nspname"], row["objname"]
            if (
                not isinstance(kind, str)
                or not (namespace is None or isinstance(namespace, str))
                or not isinstance(name, str)
            ):
                raise LiveRenderError("PostgreSQL scratch catalog check failed")
            entries.add((kind, namespace, name))
        if len(rows) != 2 or entries != _TEMPLATE0_CATALOG_BASELINE:
            raise LiveRenderError("PostgreSQL scratch catalog check failed")
    except sa.exc.SQLAlchemyError:
        raise LiveRenderError("PostgreSQL scratch catalog check failed") from None
    finally:
        pending = sys.exception()
        if engine is not None:
            try:
                engine.dispose()
            except sa.exc.SQLAlchemyError:
                if pending is None:
                    raise LiveRenderError(
                        "PostgreSQL scratch catalog check failed"
                    ) from None


@contextmanager
def _owned_scratch_database(database_url: str) -> Iterator[str]:
    """Keep CREATE acknowledgement and confirmed server identity private."""
    url = _checked_database_url(database_url)
    admin = _connect_admin(database_url)
    scratch = f"alembic_squawk_{uuid.uuid4().hex[:16]}"
    created = False
    identity = None
    try:
        try:
            with admin.connect() as connection:
                connection.exec_driver_sql(
                    f'CREATE DATABASE "{scratch}" WITH TEMPLATE template0'
                )
        except sa.exc.SQLAlchemyError:
            raise LiveRenderError("PostgreSQL scratch creation failed") from None
        created = True
        identity = _scratch_identity(admin, scratch)
        scratch_url = url.set(database=scratch)
        _assert_empty_scratch_catalog(scratch_url)
        yield scratch_url.render_as_string(hide_password=False)
    finally:
        pending = sys.exception()
        cleanup_error = None
        try:
            if created and identity is not None:
                try:
                    # Quiescent owned CI is required: this is not a hostile
                    # concurrent-admin proof or authority inferred from a name.
                    if _scratch_identity(admin, scratch) != identity:
                        raise LiveRenderError("PostgreSQL scratch cleanup failed")
                    with admin.connect() as connection:
                        connection.exec_driver_sql(
                            f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'
                        )
                except (sa.exc.SQLAlchemyError, LiveRenderError):
                    cleanup_error = LiveRenderError("PostgreSQL scratch cleanup failed")
        finally:
            try:
                admin.dispose()
            except sa.exc.SQLAlchemyError:
                cleanup_error = LiveRenderError("PostgreSQL scratch cleanup failed")
        if cleanup_error is not None:
            if pending is None:
                raise cleanup_error from None
            # Preserve the original migration exception, including rollback.
            pending.add_note("PostgreSQL scratch cleanup failed")


def _alembic_config() -> Config:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return config


def render_revision_sql(migration: Path, database_url: str) -> str:
    """Return the DDL one revision executes on an owned scratch database."""

    revision, down_revision = read_revision_metadata(migration)
    with _owned_scratch_database(database_url) as scratch_url:
        previous_url = os.environ.get("DATABASE_URL")
        recorder = _DdlRecorder()
        registered_listeners: list[tuple[str, Callable[..., object]]] = []
        environment_changed = False
        try:
            os.environ["DATABASE_URL"] = scratch_url
            environment_changed = True
            for event_name, listener in recorder.event_listeners():
                event.listen(Engine, event_name, listener)
                registered_listeners.append((event_name, listener))
            config = _alembic_config()
            if down_revision != "base":
                command.upgrade(config, down_revision)
            recorder.active = True
            try:
                command.upgrade(config, revision)
            finally:
                # Keep the recorder active during Alembic's rollback on failure.
                recorder.active = False
        finally:
            recorder.active = False
            try:
                for event_name, listener in reversed(registered_listeners):
                    event.remove(Engine, event_name, listener)
            finally:
                if environment_changed:
                    if previous_url is None:
                        os.environ.pop("DATABASE_URL", None)
                    else:
                        os.environ["DATABASE_URL"] = previous_url
    return "".join(f"{statement};\n" for statement in recorder.statements)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        print(
            "usage: render_live_alembic_sql.py MIGRATION OUTPUT_SQL",
            file=sys.stderr,
        )
        return 2

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        print("error: DATABASE_URL must target PostgreSQL", file=sys.stderr)
        return 2

    try:
        sql = render_revision_sql(Path(arguments[0]), database_url)
    except (RevisionMetadataError, LiveRenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    Path(arguments[1]).write_text(sql, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
