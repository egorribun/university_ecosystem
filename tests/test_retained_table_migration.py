"""The online retirement revision preserves schema/data and drift detection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]


def _revision():
    path = (
        ROOT
        / "alembic/versions/202610010001_drop_unused_user_stats_and_vector_chunks.py"
    )
    spec = importlib.util.spec_from_file_location("retained_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_online_upgrade_and_downgrade_preserve_existing_rows_and_indexes():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE user_stats (user_id TEXT PRIMARY KEY, attendance_total INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE vector_chunks (id TEXT PRIMARY KEY, content TEXT)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX saved_content ON vector_chunks(content)"
        )
        connection.exec_driver_sql(
            "INSERT INTO user_stats VALUES ('existing-user', 17)"
        )
        connection.exec_driver_sql(
            "INSERT INTO vector_chunks VALUES ('existing-doc', 'retained')"
        )
        revision = _revision()
        with Operations.context(MigrationContext.configure(connection)):
            for operation in (revision.upgrade, revision.downgrade):
                operation()
                assert set(sa.inspect(connection).get_table_names()) == {
                    "user_stats",
                    "vector_chunks",
                }
                assert (
                    connection.exec_driver_sql(
                        "SELECT attendance_total FROM user_stats"
                    ).scalar_one()
                    == 17
                )
                assert (
                    connection.exec_driver_sql(
                        "SELECT content FROM vector_chunks"
                    ).scalar_one()
                    == "retained"
                )
                assert {
                    index["name"]
                    for index in sa.inspect(connection).get_indexes("vector_chunks")
                } == {"saved_content"}
    engine.dispose()


def _runtime_metadata():
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.UUID(), primary_key=True))
    sa.Table(
        "active_content", metadata, sa.Column("id", sa.Integer(), primary_key=True)
    )
    return metadata


def test_retained_metadata_matches_historical_postgresql_schema():
    import json

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable

    from app.core.db.retained_table_metadata import (
        RETAINED_TABLES,
        build_migration_metadata,
    )

    runtime = _runtime_metadata()
    metadata = build_migration_metadata(runtime)
    assert set(runtime.tables) == {"users", "active_content"}
    assert metadata.tables["users"] is not runtime.tables["users"]
    assert metadata.tables["user_stats"].info["retained_by_revision"] == "202610010001"
    expected = json.loads(
        (ROOT / "tests/fixtures/schema/retained_tables_202609300002.json").read_text()
    )
    dialect = postgresql.dialect()
    actual = {
        name: {
            "create_table": str(
                CreateTable(metadata.tables[name]).compile(dialect=dialect)
            ).strip(),
            "indexes": sorted(
                str(CreateIndex(index).compile(dialect=dialect)).strip()
                for index in metadata.tables[name].indexes
            ),
        }
        for name in RETAINED_TABLES
    }
    assert actual == expected


def test_retained_tables_have_one_explicit_owner():
    import pytest

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata()
    sa.Table("user_stats", runtime, sa.Column("user_id", sa.UUID(), primary_key=True))
    with pytest.raises(ValueError, match="competing runtime ownership"):
        build_migration_metadata(runtime)


def test_autogenerate_retains_tables_and_still_detects_actual_drift():
    from alembic.autogenerate import compare_metadata
    from pgvector.sqlalchemy import Vector

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata()
    metadata = build_migration_metadata(runtime)
    engine = sa.create_engine("sqlite://")
    # SQLite supports the historical DDL, but its default reflection registry has
    # no vector type. Register only its type reader for this real-catalog test.
    engine.dialect.ischema_names = {
        **engine.dialect.ischema_names,
        "VECTOR": Vector,
        "UUID": sa.UUID,
    }
    with engine.begin() as connection:
        metadata.create_all(connection)
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []
        removals = compare_metadata(context, runtime)
        assert {diff[1].name for diff in removals if diff[0] == "remove_table"} == {
            "user_stats",
            "vector_chunks",
        }
        connection.exec_driver_sql("DROP INDEX ix_vector_chunks_tenant_doc")
        connection.exec_driver_sql(
            "CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)"
        )
        drift = compare_metadata(context, metadata)
        assert any(
            diff[0] == "add_index" and diff[1].name == "ix_vector_chunks_tenant_doc"
            for diff in drift
        )
        assert any(
            diff[0] == "remove_table" and diff[1].name == "unexpected_table"
            for diff in drift
        )
    engine.dispose()


def test_offline_revision_has_no_schema_or_data_mutations():
    from io import StringIO

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        _revision().upgrade()
        _revision().downgrade()
    assert output.getvalue() == ""
