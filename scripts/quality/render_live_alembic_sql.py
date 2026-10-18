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
_DDL_STATEMENT = re.compile(
    r"^\s*(?:CREATE|ALTER|DROP|COMMENT|GRANT|REVOKE|TRUNCATE|RENAME|SET)\b",
    re.IGNORECASE,
)
_ADMIN_CONNECT_ATTEMPTS = 30


class LiveRenderError(RuntimeError):
    """Raised when the live rendering cannot complete."""


class _DdlRecorder:
    """Collects the DDL that executes while the recorder is active."""

    def __init__(self) -> None:
        self.active = False
        self.statements: list[str] = []

    def __call__(
        self,
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if self.active and _DDL_STATEMENT.match(statement):
            self.statements.append(statement.strip())


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
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{scratch}"')
        os.environ["DATABASE_URL"] = (
            make_url(database_url)
            .set(database=scratch)
            .render_as_string(hide_password=False)
        )
        event.listen(Engine, "before_cursor_execute", recorder)
        config = _alembic_config()
        if down_revision != "base":
            command.upgrade(config, down_revision)
        recorder.active = True
        command.upgrade(config, revision)
        recorder.active = False
    finally:
        event.remove(Engine, "before_cursor_execute", recorder)
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
        with admin.connect() as connection:
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'
            )
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
