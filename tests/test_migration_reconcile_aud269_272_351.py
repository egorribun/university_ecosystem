"""Characterize historical reconciliation SQL without running the migration.

The synthetic inspector describes the catalog branches exercised below.  These
tests do not assert that a particular deployed database had those objects, nor
do they execute the historical revision against populated PostgreSQL data.
"""

from __future__ import annotations

import importlib.util
import io
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def _load_revision(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"audit_{filename[:-3]}", VERSIONS / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EmptyInspector:
    """Model only catalog lookups, keeping Alembic's real SQL generator."""

    def has_table(self, table: str) -> bool:
        return False

    def get_table_names(self) -> list[str]:
        return []

    def get_columns(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_indexes(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_foreign_keys(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_unique_constraints(self, table: str) -> list[dict[str, Any]]:
        return []

    def get_check_constraints(self, table: str) -> list[dict[str, Any]]:
        return []


class _PresentInspector(_EmptyInspector):
    def has_table(self, table: str) -> bool:
        return True


def _render_upgrade(
    filename: str,
    monkeypatch: pytest.MonkeyPatch,
    inspector: _EmptyInspector | None = None,
) -> str:
    module = _load_revision(filename)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with monkeypatch.context() as patch:
        patch.setattr(module, "op", Operations(context))
        patch.setattr(sa, "inspect", lambda _bind: inspector or _EmptyInspector())
        module.upgrade()
    return output.getvalue()


def _index_definitions(sql: str) -> dict[str, str]:
    definitions = {}
    for statement in sql.split(";"):
        normalized = " ".join(statement.split())
        match = re.fullmatch(
            r"CREATE (?:UNIQUE )?INDEX (?:CONCURRENTLY )?(?:IF NOT EXISTS )?"
            r"(\S+) (ON .+)",
            normalized,
        )
        if match:
            definitions[match.group(1)] = match.group(2)
    return definitions


@pytest.fixture
def reconcile_sql(monkeypatch: pytest.MonkeyPatch) -> str:
    return _render_upgrade(
        "202603280001_reconcile_post_uuid_migration_drift.py", monkeypatch
    )


def test_characterized_revisions_are_ancestors_of_reconciliation() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    ancestors = {
        revision.revision
        for revision in script.iterate_revisions("202603280001", "base")
    }
    assert {
        "202506150001",
        "202602010004",
        "202603060001",
        "202603070001",
        "202603140002",
        "202603140003",
        "202603150001",
        "202603170001",
    } <= ancestors


@pytest.mark.parametrize(
    ("predecessor", "indexes"),
    [
        (
            "202603140002_add_stored_events_pending_partial_indexes.py",
            (
                "ix_stored_events_pending_created",
                "ix_stored_events_pending_aggregate_created",
            ),
        ),
        (
            "202603140003_add_stored_events_aggregate_ordering.py",
            ("ix_stored_events_aggregate_uuid",),
        ),
        (
            "202603060001_add_chat_participants_covering_indexes.py",
            (
                "ix_chat_participants_user_id_chat_id",
                "ix_chat_participants_chat_id_user_id",
            ),
        ),
        (
            "202603070001_add_message_unread_partial_index.py",
            ("ix_messages_unread_chat_sender",),
        ),
        (
            "202603150001_add_news_comment_cursor_index.py",
            ("idx_news_comment_cursor",),
        ),
        (
            "202603170001_add_message_pagination_covering_index.py",
            ("idx_messages_chat_pagination_covering",),
        ),
    ],
)
def test_historical_upgrade_drops_prior_hot_path_indexes_without_recreating_them(
    predecessor: str,
    indexes: tuple[str, ...],
    reconcile_sql: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    earlier_sql = _render_upgrade(predecessor, monkeypatch)
    earlier_indexes = _index_definitions(earlier_sql)
    replacement_indexes = _index_definitions(reconcile_sql)
    for name in indexes:
        assert f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name}" in earlier_sql
        assert f"DROP INDEX IF EXISTS {name} CASCADE" in reconcile_sql
        assert not re.search(
            rf"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF NOT EXISTS\s+)?{name}\b",
            reconcile_sql,
        )
        # Compare complete rendered definitions as well as names; an alternate
        # name with the same columns, order, predicate and INCLUDE would count.
        assert earlier_indexes[name] not in replacement_indexes.values()


def test_historical_reconcile_recreates_hnsw_under_new_names(
    reconcile_sql: str,
) -> None:
    for table in ("events", "news"):
        assert (
            f"DROP INDEX IF EXISTS ix_{table}_embedding_hnsw CASCADE" in reconcile_sql
        )
        assert (
            f"CREATE INDEX IF NOT EXISTS ix_{table}_embedding "
            f"ON {table} USING hnsw (embedding vector_cosine_ops)"
        ) in reconcile_sql


def _delivery_constraint(reconcile_sql: str) -> str:
    statement = next(
        statement.strip()
        for statement in reconcile_sql.split(";")
        if "ADD CONSTRAINT uq_notification_delivery_once" in statement
    )
    return statement.split(" ADD ", 1)[1]


def test_delivery_constraint_permits_later_attempt_and_null_subscription(
    reconcile_sql: str,
) -> None:
    constraint = _delivery_constraint(reconcile_sql)
    assert constraint == (
        "CONSTRAINT uq_notification_delivery_once UNIQUE "
        "(notification_id, channel, subscription_id, attempted_at)"
    )

    # This disposable SQLite table exercises only the generated UNIQUE clause,
    # not the migration or PostgreSQL partitioning, with synthetic values.
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            "CREATE TABLE delivery (notification_id TEXT NOT NULL, channel TEXT NOT NULL, "
            "subscription_id TEXT, attempted_at TEXT NOT NULL, " + constraint + ")"
        )
        insert = "INSERT INTO delivery VALUES (?, ?, ?, ?)"
        connection.execute(insert, ("n1", "webpush", "s1", "first"))
        connection.execute(insert, ("n1", "webpush", "s1", "later"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(insert, ("n1", "webpush", "s1", "first"))
        connection.execute(insert, ("n1", "inapp", None, "same"))
        connection.execute(insert, ("n1", "inapp", None, "same"))
        assert connection.execute("SELECT count(*) FROM delivery").fetchone() == (4,)


def test_queue_started_as_integer_and_reconcile_renders_text_uuid_cast(
    reconcile_sql: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    earlier_sql = _render_upgrade(
        "202506150001_add_notification_queue_jobs_table.py", monkeypatch
    )
    assert "record_id INTEGER NOT NULL" in earlier_sql
    assert (
        "ALTER TABLE notification_queue_jobs ALTER COLUMN record_id TYPE UUID "
        "USING record_id::text::uuid"
    ) in reconcile_sql


def test_prior_cleanup_can_remove_event_and_news_legacy_id_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_sql = _render_upgrade(
        "202602010004_drop_legacy_columns.py", monkeypatch, _PresentInspector()
    )
    for table in ("events", "news"):
        assert (
            f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "legacy_id" CASCADE'
            in cleanup_sql
        )


@pytest.mark.parametrize("record_id", [-2147483648, -1, 0, 1, 42, 2147483647])
def test_legacy_integer_text_is_not_uuid_input(record_id: int) -> None:
    # Every signed 32-bit decimal representation is at most 11 characters;
    # a UUID needs 32 hexadecimal digits, so an integer text cast is not a map.
    assert len(str(record_id)) <= 11
    with pytest.raises(ValueError):
        uuid.UUID(str(record_id))
