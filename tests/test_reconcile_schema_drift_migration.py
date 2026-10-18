"""Focused schema ownership contracts for legacy migration 202607280001."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202607280001_reconcile_schema_drift.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "reconcile_schema_drift_migration_contract", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


class _Inspector:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables

    def get_table_names(self) -> list[str]:
        return sorted(self.tables)


class _Operations:
    def __init__(self) -> None:
        self.bind = object()
        self.created_tables: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.created_indexes: list[
            tuple[str, str, tuple[str, ...], dict[str, Any]]
        ] = []
        self.executed: list[str] = []

    def get_bind(self) -> object:
        return self.bind

    def create_table(self, name: str, *items: Any, **kwargs: Any) -> None:
        self.created_tables.append((name, items, kwargs))

    def create_index(
        self, name: str, table_name: str, columns: list[str], **kwargs: Any
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns), kwargs))

    def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))


def _bind_migration(monkeypatch: pytest.MonkeyPatch, tables: set[str]):
    migration = _load_migration()
    operations = _Operations()
    inspector = _Inspector(tables)
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda bind: inspector
        if bind is operations.bind
        else pytest.fail("migration inspected an unexpected connection"),
    )
    return migration, operations


def _columns(operations: _Operations, table_name: str) -> dict[str, sa.Column[Any]]:
    table_call = next(
        call for call in operations.created_tables if call[0] == table_name
    )
    return {item.name: item for item in table_call[1] if isinstance(item, sa.Column)}


def test_upgrade_creates_expected_schema_for_absent_legacy_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(monkeypatch, set())

    migration.upgrade()

    assert [name for name, _items, _kwargs in operations.created_tables] == [
        "tenants",
        "vector_chunks",
        "grades",
    ]
    tenants = _columns(operations, "tenants")
    assert set(tenants) == {
        "id",
        "name",
        "slug",
        "domain",
        "is_active",
        "created_at",
    }
    assert isinstance(tenants["id"].type, sa.Uuid)
    assert tenants["id"].primary_key and not tenants["id"].nullable
    assert isinstance(tenants["name"].type, sa.String)
    assert tenants["name"].type.length == 256 and not tenants["name"].nullable
    assert isinstance(tenants["slug"].type, sa.String)
    assert tenants["slug"].type.length == 64 and not tenants["slug"].nullable
    assert tenants["domain"].nullable
    assert str(tenants["is_active"].server_default.arg) == "true"
    assert str(tenants["created_at"].server_default.arg) == "now()"

    chunks = _columns(operations, "vector_chunks")
    assert set(chunks) == {
        "id",
        "tenant_id",
        "course_id",
        "document_id",
        "chunk_index",
        "content",
        "embedding",
        "payload",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert getattr(chunks["embedding"].type, "dim", None) == 1536
    assert chunks["tenant_id"].nullable is False
    assert chunks["document_id"].nullable is False
    assert str(chunks["chunk_index"].server_default.arg) == "0"
    assert chunks["updated_at"].nullable

    grades = _columns(operations, "grades")
    assert set(grades) == {
        "id",
        "student_id",
        "subject",
        "score",
        "assessment_type",
        "assigned_by",
        "created_at",
        "updated_at",
    }
    assert grades["student_id"].nullable is False
    assert {
        (key.target_fullname, key.ondelete) for key in grades["student_id"].foreign_keys
    } == {("users.id", "CASCADE")}
    assert grades["assigned_by"].nullable
    assert {
        (key.target_fullname, key.ondelete)
        for key in grades["assigned_by"].foreign_keys
    } == {("users.id", "SET NULL")}
    assert str(grades["assessment_type"].server_default.arg) == "exam"

    indexes = {
        (name, table, columns, kwargs.get("unique", False))
        for name, table, columns, kwargs in operations.created_indexes
    }
    assert indexes == {
        ("ix_tenants_domain", "tenants", ("domain",), True),
        ("ix_tenants_is_active", "tenants", ("is_active",), False),
        ("ix_tenants_slug", "tenants", ("slug",), True),
        ("ix_vector_chunks_chunk_index", "vector_chunks", ("chunk_index",), False),
        ("ix_vector_chunks_course_id", "vector_chunks", ("course_id",), False),
        ("ix_vector_chunks_created_at", "vector_chunks", ("created_at",), False),
        ("ix_vector_chunks_document_id", "vector_chunks", ("document_id",), False),
        ("ix_vector_chunks_embedding", "vector_chunks", ("embedding",), False),
        ("ix_vector_chunks_is_active", "vector_chunks", ("is_active",), False),
        (
            "ix_vector_chunks_tenant_course",
            "vector_chunks",
            ("tenant_id", "course_id"),
            False,
        ),
        (
            "ix_vector_chunks_tenant_doc",
            "vector_chunks",
            ("tenant_id", "document_id"),
            False,
        ),
        ("ix_vector_chunks_tenant_id", "vector_chunks", ("tenant_id",), False),
        ("ix_grades_student_id", "grades", ("student_id",), False),
        (
            "ix_grades_student_subject",
            "grades",
            ("student_id", "subject"),
            False,
        ),
        ("ix_grades_subject", "grades", ("subject",), False),
    }


def test_upgrade_skips_all_existing_tables_without_recreating_tenant_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_migration(
        monkeypatch, {"tenants", "vector_chunks", "grades"}
    )

    migration.upgrade()

    assert operations.created_tables == []
    assert operations.created_indexes == []
    assert operations.executed == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
        "ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_slug_key CASCADE",
        "ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_domain_key CASCADE",
    ]


def test_historical_downgrade_drops_only_revision_owned_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    operations = _Operations()
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert operations.executed == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
        "DROP TABLE IF EXISTS grades CASCADE",
        "DROP TABLE IF EXISTS vector_chunks CASCADE",
    ]
    assert all("tenants" not in statement for statement in operations.executed)
