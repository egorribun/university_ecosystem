"""AUD-270: the UUID cutover must stop instead of truncating a child table.

Revision 202602010003 used to run ``TRUNCATE TABLE <child> CASCADE`` when the
referenced table had already been migrated. That also erased every table that
references the child. The helper below either leaves an empty child alone or
raises before any destructive statement runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202602010003_final_cutover_swap.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud270_cutover", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Bind:
    def __init__(self, has_rows: bool) -> None:
        self.has_rows = has_rows
        self.statements: list[str] = []

    def execute(self, statement: Any) -> SimpleNamespace:
        self.statements.append(" ".join(str(statement).split()))
        return SimpleNamespace(scalar=lambda: self.has_rows)


def test_cutover_source_has_no_truncate_statement() -> None:
    # The destructive cascade was the defect; the revision must not reintroduce it.
    source = MIGRATION.read_text(encoding="utf-8")
    assert "TRUNCATE TABLE" not in source.upper()
    assert 'TRUNCATE "' not in source.upper()


def test_empty_child_is_left_untouched_without_truncation() -> None:
    migration = _load_migration()
    bind = _Bind(has_rows=False)

    migration._refuse_unmappable_child(bind, "messages", "chats")

    assert bind.statements == ['SELECT EXISTS (SELECT 1 FROM "messages")']


def test_non_empty_child_stops_the_migration_before_any_destructive_sql() -> None:
    migration = _load_migration()
    bind = _Bind(has_rows=True)

    with pytest.raises(RuntimeError, match="refusing to map or truncate messages"):
        migration._refuse_unmappable_child(bind, "messages", "chats")

    assert bind.statements == ['SELECT EXISTS (SELECT 1 FROM "messages")']
    assert not any("TRUNCATE" in statement.upper() for statement in bind.statements)
