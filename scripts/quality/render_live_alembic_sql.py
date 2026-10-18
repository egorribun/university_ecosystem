"""Render the DDL one changed Alembic revision runs against live PostgreSQL.

Offline ``alembic upgrade --sql`` has no database inspector, so inspector-guarded
branches (drop guards) render nothing and Squawk cannot lint them (AUD-208). This
renderer migrates a throwaway database to the revision's parent, then records the
DDL that the revision itself executes against that live state. The database is
dropped afterwards, so the job's own database is never mutated.

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
from collections.abc import Callable
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


def _admin_engine(database_url: str) -> sa.Engine:
    url = make_url(database_url).set(drivername="postgresql+psycopg")
    return sa.create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )


def _connect_admin(database_url: str) -> sa.Engine:
    """Wait for the CI PostgreSQL service, which may still be starting."""

    engine = _admin_engine(database_url)
    last_error: sa.exc.OperationalError | None = None
    for _ in range(_ADMIN_CONNECT_ATTEMPTS):
        try:
            with engine.connect():
                return engine
        except sa.exc.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    engine.dispose()
    raise LiveRenderError(
        f"PostgreSQL admin connection failed: {last_error}"
    ) from last_error


def _alembic_config() -> Config:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return config


def render_revision_sql(migration: Path, database_url: str) -> str:
    """Return the DDL the revision in ``migration`` executes on a live database."""

    revision, down_revision = read_revision_metadata(migration)
    admin = _connect_admin(database_url)
    scratch = f"alembic_squawk_{uuid.uuid4().hex[:16]}"
    previous_url = os.environ.get("DATABASE_URL")
    recorder = _DdlRecorder()
    registered_listeners: list[tuple[str, Callable[..., object]]] = []
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{scratch}"')
        os.environ["DATABASE_URL"] = (
            make_url(database_url)
            .set(database=scratch)
            .render_as_string(hide_password=False)
        )
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
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            try:
                with admin.connect() as connection:
                    connection.exec_driver_sql(
                        f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'
                    )
            finally:
                admin.dispose()
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
