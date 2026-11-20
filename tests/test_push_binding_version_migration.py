"""The push binding successor preserves data and the migration safety order."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "202611200001_push_binding_version.py"


def _migration() -> ModuleType:
    assert MIGRATION_PATH.is_file(), "The push binding successor is missing"
    spec = importlib.util.spec_from_file_location(
        "push_binding_successor", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render(operation: object) -> str:
    assert callable(operation)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        operation()
    return " ".join(output.getvalue().upper().split())


def test_successor_adds_nullable_generation_without_backfill() -> None:
    migration = _migration()
    assert migration.revision == "202611200001"
    assert migration.down_revision == "202611020000"
    sql = _render(migration.upgrade)
    ordered = (
        "SET LOCAL LOCK_TIMEOUT",
        "SET LOCAL STATEMENT_TIMEOUT",
        "LOCK TABLE PUBLIC.PUSH_SUBSCRIPTIONS IN ACCESS EXCLUSIVE MODE",
        "PG_CATALOG.PG_ATTRIBUTE",
        "RAISE EXCEPTION",
        "ADD COLUMN IF NOT EXISTS BINDING_VERSION BIGINT",
    )
    positions = [sql.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)
    assert "PG_CATALOG.PG_INDEX" in sql
    assert "INDISUNIQUE" in sql
    assert "PUBLIC.ALEMBIC_VERSION" in sql
    assert "VERSION_NUM" in sql
    assert "202611200001" in sql
    assert "NOT NULL" not in sql
    assert "DEFAULT" not in sql
    assert "UPDATE " not in sql


def test_downgrade_removes_only_the_added_column() -> None:
    sql = _render(_migration().downgrade)
    assert "ALTER TABLE PUBLIC.PUSH_SUBSCRIPTIONS DROP COLUMN BINDING_VERSION" in sql
    assert "DROP TABLE" not in sql
