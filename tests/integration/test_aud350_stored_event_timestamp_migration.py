"""PostgreSQL counterfactual for AUD-350's naive-UTC timestamp conversion.

This compares the exact frozen migration from HEAD with the one-line candidate,
using the existing disposable PostgreSQL CI service supplied through DATABASE_URL.
Each Alembic upgrade is invoked once in a separate schema. The target-only
Operations adapter intentionally scopes this regression to stored_events.created_at;
it does not exercise the whole revision or the full migration graph.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_MIGRATION_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "migrations"
    / "aud350"
    / "202603280001_reconcile_post_uuid_migration_drift_baseline.py.txt"
)
CANDIDATE_MIGRATION_PATH = (
    PROJECT_ROOT
    / "alembic"
    / "versions"
    / "202603280001_reconcile_post_uuid_migration_drift.py"
)
BASELINE_MIGRATION_SHA256 = (
    "f80590a5916188ec6795206c5302cceaac14c5ecd6305667580b5e8c0d35aeef"
)
BASELINE_EXPECTED_UTC = datetime(2026, 7, 1, 19, 34, 56, 123456, tzinfo=UTC)
CANDIDATE_EXPECTED_UTC = datetime(2026, 7, 1, 12, 34, 56, 123456, tzinfo=UTC)
LEGACY_NAIVE_UTC = datetime(2026, 7, 1, 12, 34, 56, 123456)
_RUN = os.environ.get("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


def _verify_frozen_baseline_and_candidate_delta() -> None:
    baseline_bytes = BASELINE_MIGRATION_PATH.read_bytes()
    actual_baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    if actual_baseline_sha256 != BASELINE_MIGRATION_SHA256:
        raise AssertionError("AUD-350 frozen baseline migration SHA-256 mismatch")

    candidate_bytes = CANDIDATE_MIGRATION_PATH.read_bytes()
    newline = b"\r\n" if b"\r\n" in baseline_bytes else b"\n"
    anchor = (
        b"        existing_nullable=False,"
        + newline
        + b"    )"
        + newline
        + b"    op.alter_column("
        + newline
        + b'        "user_preferences",'
    )
    replacement = (
        b"        existing_nullable=False,"
        + newline
        + b"        postgresql_using=\"created_at AT TIME ZONE 'UTC'\","
        + newline
        + b"    )"
        + newline
        + b"    op.alter_column("
        + newline
        + b'        "user_preferences",'
    )
    if BASELINE_EXPECTED_UTC - CANDIDATE_EXPECTED_UTC != timedelta(hours=7):
        raise AssertionError(
            "AUD-350 baseline and candidate expectations must differ by seven hours"
        )
    if LEGACY_NAIVE_UTC != CANDIDATE_EXPECTED_UTC.replace(tzinfo=None):
        raise AssertionError(
            "AUD-350 candidate expectation must preserve the legacy UTC wall time"
        )

    if baseline_bytes.count(anchor) != 1 or candidate_bytes != baseline_bytes.replace(
        anchor, replacement, 1
    ):
        raise AssertionError(
            "AUD-350 candidate must differ from the frozen source only by the UTC USING clause"
        )


def _load_migration(path: Path, module_name: str):
    # The historical baseline is stored as raw .py.txt data so ordinary Ruff
    # hooks do not rewrite the bytes this regression proves. Load it explicitly
    # as Python source when the counterfactual needs to execute it.
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = migration
    spec.loader.exec_module(migration)
    return migration


class _EmptyInspector:
    def get_columns(self, _table_name: str) -> list[dict[str, object]]:
        return []

    def get_table_names(self) -> list[str]:
        return []

    def get_foreign_keys(self, _table_name: str) -> list[dict[str, object]]:
        return []

    def get_unique_constraints(self, _table_name: str) -> list[dict[str, object]]:
        return []


class _TargetOnlyOperations:
    """Forward only the real target alter; ignore unrelated migration operations."""

    def __init__(self, operations: Operations, bind: sa.Connection) -> None:
        self._operations = operations
        self._bind = bind
        self.target_alter_count = 0

    def get_bind(self) -> sa.Connection:
        return self._bind

    def alter_column(self, table_name: str, column_name: str, *args, **kwargs):
        if (table_name, column_name) == ("stored_events", "created_at"):
            self.target_alter_count += 1
            return self._operations.alter_column(
                table_name, column_name, *args, **kwargs
            )
        return None

    def __getattr__(self, _name: str):
        return lambda *_args, **_kwargs: None


def _synchronous_postgres_url(database_url: str):
    """Adapt the repository's asyncpg URL for this synchronous Alembic probe."""
    try:
        url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from exc
    if url.drivername == "postgresql+asyncpg":
        return url.set(drivername="postgresql+psycopg")
    if url.drivername == "postgresql+psycopg":
        return url
    raise ValueError("DATABASE_URL must use a PostgreSQL asyncpg or psycopg driver")


@pytest.fixture(scope="module")
def postgres_engine() -> sa.Engine:
    database_url = os.environ.get("DATABASE_URL", "")
    try:
        sync_url = _synchronous_postgres_url(database_url)
    except ValueError as exc:
        pytest.fail(f"AUD-350 integration requires a PostgreSQL DATABASE_URL: {exc}")
    engine = sa.create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                pytest.fail(
                    "AUD-350 integration DATABASE_URL must connect to PostgreSQL"
                )
            connection.execute(sa.text("SELECT 1"))
        yield engine
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("case_name", "migration_path", "expected_utc"),
    [
        ("baseline", BASELINE_MIGRATION_PATH, BASELINE_EXPECTED_UTC),
        ("candidate", CANDIDATE_MIGRATION_PATH, CANDIDATE_EXPECTED_UTC),
    ],
)
def test_upgrade_counterfactual_for_legacy_naive_utc_timestamp(
    case_name: str,
    migration_path: Path,
    expected_utc: datetime,
    postgres_engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The baseline shifts under LA; candidate preserves the original UTC instant."""
    _verify_frozen_baseline_and_candidate_delta()
    migration = _load_migration(
        migration_path, f"aud350_timestamp_{case_name}_{uuid4().hex}"
    )
    schema = f"aud350_{case_name}_{uuid4().hex}"

    with postgres_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        try:
            connection.execute(sa.text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
            connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            session_timezone = connection.execute(
                sa.text("SHOW TIME ZONE")
            ).scalar_one()
            assert session_timezone == "America/Los_Angeles"
            connection.execute(
                sa.text(
                    "CREATE TABLE stored_events "
                    "(created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL)"
                )
            )
            connection.execute(
                sa.text("INSERT INTO stored_events (created_at) VALUES (:created_at)"),
                {"created_at": LEGACY_NAIVE_UTC},
            )

            inspector = _EmptyInspector()
            monkeypatch.setattr(
                migration.sa,
                "inspect",
                lambda observed: inspector
                if observed is connection
                else pytest.fail("migration inspected an unexpected connection"),
            )
            real_operations = Operations(MigrationContext.configure(connection))
            target_operations = _TargetOnlyOperations(real_operations, connection)
            monkeypatch.setattr(migration, "op", target_operations)

            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

            assert target_operations.target_alter_count == 1
            actual_local = connection.execute(
                sa.text("SELECT created_at FROM stored_events")
            ).scalar_one()
            actual_utc_display = connection.execute(
                sa.text("SELECT created_at AT TIME ZONE 'UTC' FROM stored_events")
            ).scalar_one()
            postgres_type = connection.execute(
                sa.text("SELECT pg_typeof(created_at)::text FROM stored_events")
            ).scalar_one()
            assert connection.execute(sa.text("SHOW TIME ZONE")).scalar_one() == (
                "America/Los_Angeles"
            )
            assert isinstance(actual_local, datetime)
            assert actual_local.tzinfo is not None
            assert actual_local.utcoffset() == timedelta(hours=-7)
            assert actual_local.astimezone(UTC) == expected_utc
            assert isinstance(actual_utc_display, datetime)
            assert actual_utc_display.tzinfo is None
            assert actual_utc_display == expected_utc.replace(tzinfo=None)
            assert postgres_type == "timestamp with time zone"
        finally:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
