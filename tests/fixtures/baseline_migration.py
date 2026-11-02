"""Record actual baseline calls without claiming PostgreSQL execution."""

from __future__ import annotations

import importlib.util
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "202611020000_mvp_baseline.py"
)
BASELINE_DOWNGRADE_REASON = (
    "The MVP baseline cannot be downgraded: reaching base or any earlier schema "
    "is not a supported recovery path. Restore a consistent backup set instead."
)
_CRON_PROBE = "SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron'"

_EXPECTED_FUNCTION_SQL = (
    (
        "CREATE FUNCTION public.notify_outbox_event() RETURNS trigger\n"
        "    LANGUAGE plpgsql\n"
        "    AS $$\n"
        "            BEGIN\n"
        "                PERFORM pg_notify('outbox_events', '');\n"
        "                RETURN NEW;\n"
        "            END;\n"
        "            $$"
    ),
    (
        "CREATE FUNCTION public.ue_rls_assign_session_tenant() RETURNS trigger\n"
        "    LANGUAGE plpgsql\n"
        "    AS $$ BEGIN IF NEW.tenant_id IS NULL THEN NEW.tenant_id := "
        "NULLIF(current_setting('app.current_tenant', true), '')::uuid; "
        "END IF; RETURN NEW; END $$"
    ),
)


def normalize_sql(statement: object) -> str:
    """Trim outer whitespace only; preserve SQL literals, bodies and comments."""
    return str(statement).strip()


class RecordingBind:
    def __init__(self, dialect: str) -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.reads: list[str] = []

    def execute(self, statement: object) -> SimpleNamespace:
        sql = normalize_sql(statement)
        self.reads.append(sql)
        assert sql == _CRON_PROBE, f"Unexpected baseline catalog read: {sql}"
        return SimpleNamespace(fetchone=lambda: None)


class RecordingOperations:
    def __init__(self, dialect: str) -> None:
        self.bind = RecordingBind(dialect)
        self.bind_requests = 0
        self.statements: list[str] = []

    def get_bind(self) -> RecordingBind:
        self.bind_requests += 1
        return self.bind

    def execute(self, statement: object) -> None:
        self.statements.append(normalize_sql(statement))


def bind_baseline(
    monkeypatch: pytest.MonkeyPatch, *, dialect: str = "postgresql"
) -> tuple[ModuleType, RecordingOperations]:
    spec = importlib.util.spec_from_file_location(
        "recorded_mvp_baseline_contract", BASELINE_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    operations = RecordingOperations(dialect)
    monkeypatch.setattr(migration, "op", operations)
    return migration, operations


def assert_baseline_operation_kinds(statements: list[str]) -> None:
    """Bound global commands; this is not a universal SQL/security validator."""
    assert [sql for sql in statements if sql.upper().startswith("SET ")] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    assert [sql for sql in statements if sql.upper().startswith("DO ")] == [
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
        "'ue_rls_bypass') THEN CREATE ROLE ue_rls_bypass NOLOGIN; END IF; END $$"
    ]
    assert Counter(
        sql for sql in statements if sql.upper().startswith("CREATE FUNCTION ")
    ) == Counter(_EXPECTED_FUNCTION_SQL)
    assert [
        sql for sql in statements if sql.upper().startswith("CREATE EXTENSION ")
    ] == [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public",
        "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public",
    ]
    assert all(
        ";" not in sql or sql.startswith("DO ") or sql in _EXPECTED_FUNCTION_SQL
        for sql in statements
    )
    ddl_prefixes = (
        "CREATE TABLE ",
        "CREATE INDEX ",
        "CREATE UNIQUE INDEX ",
        "CREATE FUNCTION ",
        "CREATE TYPE ",
        "CREATE SEQUENCE ",
        "CREATE EXTENSION IF NOT EXISTS ",
        "COMMENT ON EXTENSION ",
        "ALTER TABLE ",
        "CREATE TRIGGER ",
        "CREATE POLICY ",
        "SET ",
        "DO ",
    )
    sequence_owner = (
        "ALTER SEQUENCE public.dead_letter_jobs_id_seq "
        "OWNED BY public.dead_letter_jobs.id"
    )
    assert all(
        sql == sequence_owner or sql.startswith(ddl_prefixes) for sql in statements
    )


def capture_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModuleType, RecordingOperations]:
    migration, operations = bind_baseline(monkeypatch)
    migration.upgrade()
    assert_baseline_operation_kinds(operations.statements)
    assert operations.bind_requests == 1
    assert operations.bind.reads == [_CRON_PROBE]
    assert operations.statements[:2] == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]
    return migration, operations


def table_statements(statements: Iterable[str], *tables: str) -> list[str]:
    """Select every mention of each table, including extra unqualified DDL."""
    names = "|".join(re.escape(table) for table in tables)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?:{names})(?![A-Za-z0-9_])",
        re.ASCII | re.IGNORECASE,
    )
    return [sql for sql in statements if pattern.search(sql)]


def assert_exact_statements(actual: Iterable[str], expected: Iterable[str]) -> None:
    """Reject missing, additional, duplicate or changed statements."""
    assert Counter(actual) == Counter(normalize_sql(sql) for sql in expected)


def assert_downgrade_refuses(
    migration: ModuleType, operations: RecordingOperations
) -> None:
    assert migration.downgrade_policy == "irreversible"
    assert migration.downgrade_reason == BASELINE_DOWNGRADE_REASON
    with pytest.raises(RuntimeError) as failure:
        migration.downgrade()
    assert str(failure.value) == BASELINE_DOWNGRADE_REASON
    assert operations.bind_requests == 0
    assert operations.bind.reads == []
    assert operations.statements == []
