"""AUD-278: the event full-text GIN index survives revision db31ef5d7ea4.

Revision db31ef5d7ea4 used to drop ``ix_events_search_vector`` in its upgrade and
only recreated it in downgrade, so event search lost its index at head. These
tests render the real upgrade and check that the index is kept when present and
restored concurrently when absent.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "db31ef5d7ea4_add_trusted_devices.py"
)
GIN_INDEX_SQL = (
    "CREATE INDEX CONCURRENTLY ix_events_search_vector ON events "
    "USING gin (search_vector)"
)
REQUIRED_TABLES = {
    "event_attendance",
    "notification_deliveries",
    "notifications",
    "push_subscriptions",
    "user_push_topics",
    "users",
    "events",
}


class _Inspector:
    """Reports the required tables and a chosen set of events indexes only."""

    def __init__(self, event_indexes: set[str]) -> None:
        self.event_indexes = event_indexes

    def get_table_names(self) -> list[str]:
        return sorted(REQUIRED_TABLES)

    def has_table(self, table: str) -> bool:
        return table in REQUIRED_TABLES

    def get_indexes(self, table: str) -> list[dict[str, Any]]:
        if table == "events":
            return [{"name": name} for name in sorted(self.event_indexes)]
        return []

    def get_columns(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_foreign_keys(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_unique_constraints(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_check_constraints(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_pk_constraint(self, table: str) -> dict[str, Any]:
        return {"constrained_columns": []}


def _render_upgrade(monkeypatch: pytest.MonkeyPatch, event_indexes: set[str]) -> str:
    spec = importlib.util.spec_from_file_location("aud278_trusted", MIGRATION)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(module, "op", Operations(context))
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector(event_indexes))
    module.upgrade()
    return output.getvalue()


def test_upgrade_keeps_existing_event_search_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render_upgrade(monkeypatch, {"ix_events_search_vector"})

    assert "ix_events_search_vector" not in sql


def test_upgrade_restores_missing_event_search_index_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _render_upgrade(monkeypatch, set())

    normalized = " ".join(sql.split())
    assert GIN_INDEX_SQL in normalized
    # The concurrent build must run outside the migration transaction.
    assert normalized.index("COMMIT;") < normalized.index(GIN_INDEX_SQL)
    assert "DROP INDEX" not in normalized
