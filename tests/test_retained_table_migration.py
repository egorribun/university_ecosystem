"""Baseline refusal guards preserve retained schema/data and drift detection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[1]


def _revision():
    path = ROOT / "alembic/versions/202611020000_mvp_baseline.py"
    spec = importlib.util.spec_from_file_location("retained_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_refusals_preserve_retained_rows_and_indexes() -> None:
    """Real SQLite rows survive unsupported upgrade and irreversible downgrade."""
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE user_stats "
                "(user_id TEXT PRIMARY KEY, attendance_total INTEGER)"
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
            assert revision.revision == "202611020000"
            assert revision.downgrade_policy == "irreversible"
            with Operations.context(MigrationContext.configure(connection)):
                for operation, reason in (
                    (revision.upgrade, "requires PostgreSQL"),
                    (revision.downgrade, "cannot be downgraded"),
                ):
                    with pytest.raises(RuntimeError, match=reason):
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
    finally:
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
    metadata = build_migration_metadata(runtime, dialect_name="postgresql")
    assert set(runtime.tables) == {"users", "active_content"}
    assert metadata.tables["users"] is not runtime.tables["users"]
    assert metadata.tables["user_stats"].info["retained_by_revision"] == "202611020000"
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


_EXPECTED_MIGRATION_OWNED_TENANT_TABLES = (
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)


def _add_message_index_columns(table: sa.Table) -> None:
    for column in (
        sa.Column("chat_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_status", sa.Boolean(), nullable=False),
    ):
        table.append_column(column)


def _runtime_metadata_with_tenant_tables():
    metadata = sa.MetaData()
    sa.Table("tenants", metadata, sa.Column("id", sa.UUID(), primary_key=True))
    users = sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    sa.Index("ix_users_tenant_id", users.c.tenant_id)
    for table_name in _EXPECTED_MIGRATION_OWNED_TENANT_TABLES:
        table = sa.Table(
            table_name, metadata, sa.Column("id", sa.UUID(), primary_key=True)
        )
        if table_name == "messages":
            _add_message_index_columns(table)
    return metadata


def test_migration_owned_tenant_metadata_matches_parent_revision():
    from sqlalchemy.dialects import postgresql

    from app.core.db.retained_table_metadata import (
        MIGRATION_OWNED_TENANT_TABLES,
        build_migration_metadata,
    )

    assert MIGRATION_OWNED_TENANT_TABLES == _EXPECTED_MIGRATION_OWNED_TENANT_TABLES
    runtime = _runtime_metadata_with_tenant_tables()
    metadata = build_migration_metadata(runtime, dialect_name="postgresql")
    assert all(
        "tenant_id" not in runtime.tables[name].c
        for name in MIGRATION_OWNED_TENANT_TABLES
    )

    for table_name in MIGRATION_OWNED_TENANT_TABLES:
        tenant_id = metadata.tables[table_name].c.tenant_id
        assert tenant_id.type.compile(dialect=postgresql.dialect()) == "UUID"
        assert tenant_id.nullable is True
        assert tenant_id.info["migration_owned_by_revision"] == "202611020000"
        (foreign_key,) = tenant_id.foreign_keys
        assert foreign_key.target_fullname == "tenants.id"
        assert foreign_key.ondelete == "CASCADE"
        expected_indexes = {f"ix_{table_name}_tenant_id"}
        if table_name == "messages":
            expected_indexes.update(
                {
                    "ix_messages_unread_chat_sender",
                    "idx_messages_chat_pagination_covering",
                }
            )
        assert {
            index.name for index in metadata.tables[table_name].indexes
        } == expected_indexes


def test_autogenerate_keeps_parent_owned_tenant_columns_fk_and_indexes():
    from alembic.autogenerate import compare_metadata
    from pgvector.sqlalchemy import Vector

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata_with_tenant_tables()
    target = build_migration_metadata(runtime, dialect_name="sqlite")
    engine = sa.create_engine("sqlite://")
    engine.dialect.ischema_names = {
        **engine.dialect.ischema_names,
        "VECTOR": Vector,
        "UUID": sa.UUID,
    }
    try:
        with engine.begin() as connection:
            target.create_all(connection)
            context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            assert compare_metadata(context, target) == []
            runtime_drift = compare_metadata(context, runtime)
            removed_tenant_columns = {
                (diff[2], diff[3].name)
                for diff in runtime_drift
                if diff[0] == "remove_column" and diff[3].name == "tenant_id"
            }
            assert removed_tenant_columns == {
                (table_name, "tenant_id")
                for table_name in _EXPECTED_MIGRATION_OWNED_TENANT_TABLES
            }
    finally:
        engine.dispose()


def test_retained_tables_have_one_explicit_owner():
    import pytest

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata()
    sa.Table("user_stats", runtime, sa.Column("user_id", sa.UUID(), primary_key=True))
    with pytest.raises(ValueError, match="competing runtime ownership"):
        build_migration_metadata(runtime, dialect_name="postgresql")


def test_autogenerate_retains_tables_and_still_detects_actual_drift():
    from alembic.autogenerate import compare_metadata
    from pgvector.sqlalchemy import Vector

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata()
    metadata = build_migration_metadata(runtime, dialect_name="sqlite")
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


@pytest.mark.parametrize("catalog_nullable", [False, True], ids=["unchanged", "drift"])
def test_autogenerate_detects_retained_column_nullability_drift(
    catalog_nullable: bool,
) -> None:
    from alembic.autogenerate import compare_metadata
    from pgvector.sqlalchemy import Vector

    from app.core.db.retained_table_metadata import build_migration_metadata

    target = build_migration_metadata(_runtime_metadata(), dialect_name="sqlite")
    catalog = build_migration_metadata(_runtime_metadata(), dialect_name="sqlite")
    catalog.tables["vector_chunks"].c.is_active.nullable = catalog_nullable
    engine = sa.create_engine("sqlite://")
    # Exercise real SQLite reflection/autogeneration, not PostgreSQL execution.
    engine.dialect.ischema_names = {
        **engine.dialect.ischema_names,
        "VECTOR": Vector,
        "UUID": sa.UUID,
    }
    try:
        with engine.begin() as connection:
            catalog.create_all(connection)
            context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            drift = compare_metadata(context, target)
            if catalog_nullable:
                assert len(drift) == 1
                (column_changes,) = drift
                (change,) = column_changes
                assert (change[0], change[2], change[3], change[-2], change[-1]) == (
                    "modify_nullable",
                    "vector_chunks",
                    "is_active",
                    True,
                    False,
                )
            else:
                assert drift == []
    finally:
        engine.dispose()


def test_offline_baseline_downgrade_refuses_without_emitting_sql() -> None:
    from io import StringIO

    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    revision = _revision()
    with Operations.context(context):
        with pytest.raises(RuntimeError, match="cannot be downgraded") as failure:
            revision.downgrade()
    assert str(failure.value) == revision.downgrade_reason
    assert output.getvalue() == ""


def test_migration_owned_columns_skip_absent_runtime_tables() -> None:
    from app.core.db.retained_table_metadata import (
        MIGRATION_OWNED_TENANT_TABLES,
        build_migration_metadata,
    )

    runtime = sa.MetaData()
    sa.Table("tenants", runtime, sa.Column("id", sa.UUID(), primary_key=True))
    messages = sa.Table(
        "messages", runtime, sa.Column("id", sa.UUID(), primary_key=True)
    )
    _add_message_index_columns(messages)

    metadata = build_migration_metadata(runtime, dialect_name="postgresql")

    assert "tenant_id" in metadata.tables["messages"].c
    assert not (set(MIGRATION_OWNED_TENANT_TABLES) - {"messages"}).intersection(
        metadata.tables
    )


def test_migration_owned_tenant_column_conflict_fails_closed() -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata_with_tenant_tables()
    runtime.tables["groups"].append_column(sa.Column("tenant_id", sa.UUID()))

    with pytest.raises(
        ValueError,
        match="Migration-owned tenant_id has competing runtime ownership: groups",
    ):
        build_migration_metadata(runtime, dialect_name="postgresql")


def test_migration_owned_tenant_index_conflict_fails_closed() -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata_with_tenant_tables()
    sa.Index("ix_groups_tenant_id", runtime.tables["groups"].c.id)

    with pytest.raises(
        ValueError,
        match="Migration-owned tenant index has competing runtime ownership: "
        "ix_groups_tenant_id",
    ):
        build_migration_metadata(runtime, dialect_name="postgresql")


_HOT_INDEX_SPECS = {
    "ix_chat_participants_user_id_chat_id": (
        "chat_participants",
        "user_id, chat_id",
        "",
        "202611020000",
    ),
    "ix_chat_participants_chat_id_user_id": (
        "chat_participants",
        "chat_id, user_id",
        "",
        "202611020000",
    ),
    "ix_messages_unread_chat_sender": (
        "messages",
        "chat_id, sender_id",
        " WHERE read_status = FALSE",
        "202611020000",
    ),
    "idx_messages_chat_pagination_covering": (
        "messages",
        "chat_id, created_at DESC, id DESC",
        " INCLUDE (sender_id, read_status)",
        "202611020000",
    ),
    "idx_news_comment_cursor": (
        "news_comments",
        "news_id, created_at, id",
        "",
        "202611020000",
    ),
    "ix_stored_events_pending_created": (
        "stored_events",
        "created_at, id",
        " WHERE processed_at IS NULL",
        "202611020000",
    ),
    "ix_stored_events_pending_aggregate_created": (
        "stored_events",
        "aggregate_id, created_at, id",
        " WHERE processed_at IS NULL",
        "202611020000",
    ),
    "ix_stored_events_aggregate_uuid": (
        "stored_events",
        "aggregate_id_uuid, sequence_number",
        " WHERE processed_at IS NULL AND aggregate_id_uuid IS NOT NULL",
        "202611020000",
    ),
}
_HOT_TABLE_COLUMNS = {
    "chat_participants": ("chat_id", "user_id"),
    "messages": ("id", "chat_id", "sender_id", "created_at", "read_status"),
    "news_comments": ("id", "news_id", "created_at"),
    "stored_events": (
        "id",
        "aggregate_id",
        "created_at",
        "processed_at",
        "aggregate_id_uuid",
        "sequence_number",
    ),
}


def _hot_index_runtime(
    *,
    omit_table: str | None = None,
    omit_column: tuple[str, str] | None = None,
) -> sa.MetaData:
    metadata = _runtime_metadata()
    definitions = {
        "chat_participants": (
            sa.Column("chat_id", sa.UUID(), primary_key=True),
            sa.Column("user_id", sa.UUID(), primary_key=True),
        ),
        "messages": (
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("chat_id", sa.UUID(), nullable=False),
            sa.Column("sender_id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("read_status", sa.Boolean(), nullable=False),
        ),
        "news_comments": (
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("news_id", sa.UUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        ),
        "stored_events": (
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("aggregate_id", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True)),
            sa.Column("aggregate_id_uuid", sa.UUID()),
            sa.Column("sequence_number", sa.BigInteger()),
        ),
    }
    for table_name, columns in definitions.items():
        if table_name == omit_table:
            continue
        selected = [
            column for column in columns if (table_name, column.name) != omit_column
        ]
        sa.Table(table_name, metadata, *selected)
    sa.Index("ix_hot_fixture_active_id", metadata.tables["active_content"].c.id)
    return metadata


def _hot_metadata_snapshot(metadata: sa.MetaData) -> dict[str, object]:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable

    dialect = postgresql.dialect()
    return {
        name: (
            id(table),
            tuple(id(column) for column in table.c),
            str(CreateTable(table).compile(dialect=dialect)),
            tuple(
                sorted(
                    (
                        str(index.name),
                        id(index),
                        str(CreateIndex(index).compile(dialect=dialect)),
                    )
                    for index in table.indexes
                )
            ),
        )
        for name, table in metadata.tables.items()
    }


@pytest.mark.parametrize("index_name", tuple(_HOT_INDEX_SPECS))
def test_migration_metadata_keeps_exact_postgresql_hot_index(index_name: str) -> None:
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    before = _hot_metadata_snapshot(runtime)
    target = build_migration_metadata(runtime, dialect_name="postgresql")
    table_name, columns, suffix, revision = _HOT_INDEX_SPECS[index_name]
    indexes = {index.name: index for index in target.tables[table_name].indexes}
    assert _hot_metadata_snapshot(runtime) == before
    assert index_name in indexes, f"missing migration-owned index: {index_name}"
    index = indexes[index_name]
    assert index.table is target.tables[table_name]
    assert index.unique is False
    actual = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    expected = f"CREATE INDEX {index_name} ON {table_name} ({columns}){suffix}"
    assert " ".join(actual.split()).upper() == expected.upper()
    assert index.info["migration_owned_by_revision"] == revision


def test_migration_metadata_retains_hot_indexes_without_changing_runtime_base() -> None:
    from app import models
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = models.Base.metadata
    before = _hot_metadata_snapshot(runtime)
    target = build_migration_metadata(runtime, dialect_name="postgresql")
    assert _hot_metadata_snapshot(runtime) == before
    for table_name in _HOT_TABLE_COLUMNS:
        expected = {
            name
            for name, (owner, _columns, _suffix, _revision) in _HOT_INDEX_SPECS.items()
            if owner == table_name
        }
        expected.update(index.name for index in runtime.tables[table_name].indexes)
        if table_name == "messages":
            expected.add("ix_messages_tenant_id")
        assert {index.name for index in target.tables[table_name].indexes} == expected


@pytest.mark.parametrize("index_name", tuple(_HOT_INDEX_SPECS))
def test_migration_owned_hot_index_rejects_competing_runtime_name(
    index_name: str,
) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    table_name = _HOT_INDEX_SPECS[index_name][0]
    table = runtime.tables[table_name]
    sa.Index(index_name, next(iter(table.c)), unique=True)
    before = _hot_metadata_snapshot(runtime)
    with pytest.raises(ValueError, match="competing runtime ownership"):
        build_migration_metadata(runtime, dialect_name="postgresql")
    assert _hot_metadata_snapshot(runtime) == before


@pytest.mark.parametrize(
    ("table_name", "column_name"),
    [
        (table_name, column_name)
        for table_name, columns in _HOT_TABLE_COLUMNS.items()
        for column_name in columns
    ],
)
def test_migration_owned_hot_index_rejects_missing_required_column(
    table_name: str,
    column_name: str,
) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime(omit_column=(table_name, column_name))
    assert column_name not in runtime.tables[table_name].c
    before = _hot_metadata_snapshot(runtime)
    with pytest.raises(ValueError, match="missing required column"):
        build_migration_metadata(runtime, dialect_name="postgresql")
    assert _hot_metadata_snapshot(runtime) == before


@pytest.mark.parametrize("table_name", tuple(_HOT_TABLE_COLUMNS))
def test_migration_metadata_does_not_invent_absent_hot_tables(table_name: str) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime(omit_table=table_name)
    before = _hot_metadata_snapshot(runtime)
    target = build_migration_metadata(runtime, dialect_name="postgresql")
    assert table_name not in target.tables
    assert set(target.tables) == set(runtime.tables) | {"user_stats", "vector_chunks"}
    assert _hot_metadata_snapshot(runtime) == before


def test_migration_metadata_clones_are_independent_of_runtime_and_each_other() -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    before = _hot_metadata_snapshot(runtime)
    first = build_migration_metadata(runtime, dialect_name="postgresql")
    second = build_migration_metadata(runtime, dialect_name="postgresql")
    assert set(first.tables) == set(second.tables)
    for table_name, table in first.tables.items():
        other = second.tables[table_name]
        assert table is not other
        assert {id(column) for column in table.c}.isdisjoint(
            id(column) for column in other.c
        )
        assert {id(index) for index in table.indexes}.isdisjoint(
            id(index) for index in other.indexes
        )
    first_table = first.tables["active_content"]
    second_table = second.tables["active_content"]
    (first_index,) = first_table.indexes
    (second_index,) = second_table.indexes
    first_index.unique = True
    first_table.c.id.nullable = True
    assert second_index.unique is False
    assert second_table.c.id.nullable is False
    assert _hot_metadata_snapshot(runtime) == before


_SQLITE_HOT_INDEX_NAMES = (
    "idx_news_comment_cursor",
    "ix_stored_events_pending_created",
    "ix_stored_events_pending_aggregate_created",
    "ix_stored_events_aggregate_uuid",
)


@pytest.mark.parametrize(
    ("dialect_name", "index_name"),
    [
        (dialect_name, index_name)
        for dialect_name, names in (
            ("postgresql", tuple(_HOT_INDEX_SPECS)),
            ("sqlite", _SQLITE_HOT_INDEX_NAMES),
        )
        for index_name in names
    ],
)
@pytest.mark.parametrize("owner_present", [False, True])
def test_hot_index_rejects_reserved_name_on_another_table(
    dialect_name: str, index_name: str, owner_present: bool
) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    owner = _HOT_INDEX_SPECS[index_name][0]
    runtime = _hot_index_runtime(omit_table=None if owner_present else owner)
    sa.Index(index_name, runtime.tables["active_content"].c.id)
    before = _hot_metadata_snapshot(runtime)

    with pytest.raises(ValueError, match="competing runtime ownership"):
        build_migration_metadata(runtime, dialect_name=dialect_name)

    assert _hot_metadata_snapshot(runtime) == before


@pytest.mark.parametrize(
    "dialect_name", ["", "mysql", "postgresql+asyncpg", "POSTGRESQL"]
)
def test_migration_metadata_rejects_unknown_dialect_before_cloning(
    monkeypatch: pytest.MonkeyPatch, dialect_name: str
) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    before = _hot_metadata_snapshot(runtime)
    clone_calls = []

    def unexpected_clone(*args, **kwargs):
        clone_calls.append((args, kwargs))
        raise AssertionError("unsupported dialect must fail before cloning")

    monkeypatch.setattr(sa.Table, "to_metadata", unexpected_clone)
    with pytest.raises(ValueError, match="Unsupported migration metadata dialect"):
        build_migration_metadata(runtime, dialect_name=dialect_name)

    assert clone_calls == []
    assert _hot_metadata_snapshot(runtime) == before


@pytest.mark.parametrize("index_name", _SQLITE_HOT_INDEX_NAMES)
def test_migration_metadata_keeps_exact_sqlite_hot_index(index_name: str) -> None:
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateIndex

    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    before = _hot_metadata_snapshot(runtime)
    target = build_migration_metadata(runtime, dialect_name="sqlite")
    all_names = {
        index.name for table in target.tables.values() for index in table.indexes
    }
    assert all_names.intersection(_HOT_INDEX_SPECS) == set(_SQLITE_HOT_INDEX_NAMES)
    table_name, columns, suffix, revision = _HOT_INDEX_SPECS[index_name]
    if index_name == "ix_stored_events_aggregate_uuid":
        suffix = ""
    indexes = {index.name: index for index in target.tables[table_name].indexes}
    index = indexes[index_name]
    actual = str(CreateIndex(index).compile(dialect=sqlite.dialect()))
    expected = f"CREATE INDEX {index_name} ON {table_name} ({columns}){suffix}"
    assert " ".join(actual.split()).upper() == expected.upper()
    assert index.unique is False
    assert index.info["migration_owned_by_revision"] == revision
    assert _hot_metadata_snapshot(runtime) == before


def test_sqlite_keeps_runtime_indexes_whose_names_are_postgresql_only() -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _hot_index_runtime()
    postgres_only = set(_HOT_INDEX_SPECS) - set(_SQLITE_HOT_INDEX_NAMES)
    for index_name in sorted(postgres_only):
        sa.Index(index_name, runtime.tables["active_content"].c.id)
    before = _hot_metadata_snapshot(runtime)

    target = build_migration_metadata(runtime, dialect_name="sqlite")

    assert {index.name for index in target.tables["active_content"].indexes} == {
        "ix_hot_fixture_active_id",
        *postgres_only,
    }
    assert _hot_metadata_snapshot(runtime) == before


@pytest.mark.parametrize("mutation", ["missing", "wrong_columns", "extra"])
def test_sqlite_autogenerate_still_detects_hot_index_drift(mutation: str) -> None:
    from alembic.autogenerate import compare_metadata
    from pgvector.sqlalchemy import Vector
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateIndex

    from app.core.db.retained_table_metadata import build_migration_metadata

    target = build_migration_metadata(_hot_index_runtime(), dialect_name="sqlite")
    engine = sa.create_engine("sqlite://")
    engine.dialect.ischema_names = {
        **engine.dialect.ischema_names,
        "VECTOR": Vector,
        "UUID": sa.UUID,
    }
    try:
        with engine.begin() as connection:
            target.create_all(connection)
            context = MigrationContext.configure(
                connection, opts={"compare_type": True}
            )
            assert compare_metadata(context, target) == []
            for index_name in _SQLITE_HOT_INDEX_NAMES:
                table_name = _HOT_INDEX_SPECS[index_name][0]
                index = next(
                    index
                    for index in target.tables[table_name].indexes
                    if index.name == index_name
                )
                stored_sql = connection.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                    (index_name,),
                ).scalar_one()
                expected_sql = str(CreateIndex(index).compile(dialect=sqlite.dialect()))
                assert " ".join(stored_sql.split()).upper() == expected_sql.upper()

            if mutation == "extra":
                connection.exec_driver_sql(
                    "CREATE INDEX unexpected_hot_index ON news_comments(id)"
                )
                expected = {("remove_index", "unexpected_hot_index")}
            else:
                connection.exec_driver_sql("DROP INDEX idx_news_comment_cursor")
                expected = {("add_index", "idx_news_comment_cursor")}
                if mutation == "wrong_columns":
                    connection.exec_driver_sql(
                        "CREATE INDEX idx_news_comment_cursor ON news_comments(news_id)"
                    )
                    expected.add(("remove_index", "idx_news_comment_cursor"))

            drift = compare_metadata(context, target)
            assert all(diff[0] in {"add_index", "remove_index"} for diff in drift)
            assert {(diff[0], diff[1].name) for diff in drift} == expected
    finally:
        engine.dispose()


@pytest.mark.parametrize("offline", [False, True], ids=["injected-online", "offline"])
def test_alembic_selects_metadata_for_the_actual_dialect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline: bool
) -> None:
    from io import StringIO

    from alembic.config import Config

    from alembic import command
    from app.core.db import retained_table_metadata

    script_dir = tmp_path / "alembic"
    versions = script_dir / "versions"
    versions.mkdir(parents=True)
    (script_dir / "env.py").write_text(
        (ROOT / "alembic/env.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (versions / "finite8_probe.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = 'finite8_probe'\n"
        "down_revision = None\n"
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade():\n"
        "    op.execute(sa.text('SELECT 1'))\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )
    database_url = "postgresql+asyncpg://migration@localhost:5432/test"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(output_buffer=StringIO())
    config.set_main_option("script_location", str(script_dir))
    config.set_main_option("sqlalchemy.url", database_url)
    original = retained_table_metadata.build_migration_metadata
    observed = []

    def recording_builder(
        runtime_metadata: sa.MetaData, *, dialect_name: str
    ) -> sa.MetaData:
        target = original(runtime_metadata, dialect_name=dialect_name)
        names = {
            index.name for table in target.tables.values() for index in table.indexes
        }
        observed.append((dialect_name, names.intersection(_HOT_INDEX_SPECS)))
        return target

    monkeypatch.setattr(
        retained_table_metadata, "build_migration_metadata", recording_builder
    )
    if offline:
        command.upgrade(config, "head", sql=True)
        assert observed == [("postgresql", set(_HOT_INDEX_SPECS))]
    else:
        engine = sa.create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            assert observed == [("sqlite", set(_SQLITE_HOT_INDEX_NAMES))]
        finally:
            engine.dispose()


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_runtime_users_tenant_ownership_is_exact_and_not_mutated(dialect: str) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata_with_tenant_tables()
    original = runtime.tables["users"].c.tenant_id
    target = build_migration_metadata(runtime, dialect_name=dialect)
    column = target.tables["users"].c.tenant_id
    assert column is not original
    assert original.nullable is True and column.nullable is True
    assert "migration_owned_by_revision" not in column.info
    assert [(fk.target_fullname, fk.ondelete) for fk in column.foreign_keys] == [
        ("tenants.id", "CASCADE")
    ]
    indexes = list(target.tables["users"].indexes)
    assert len(indexes) == 1
    assert indexes[0].name == "ix_users_tenant_id"
    assert tuple(indexes[0].columns.keys()) == ("tenant_id",)
    assert indexes[0].unique is False


@pytest.mark.parametrize(
    "drift",
    [
        "type",
        "nullable",
        "default",
        "server_default",
        "primary_key",
        "unique",
        "foreign_key",
        "ondelete",
        "onupdate",
        "missing_index",
        "index_name",
        "index_unique",
        "index_columns",
        "index_options",
        "extra_index",
    ],
)
def test_runtime_users_tenant_shape_drift_is_rejected(drift: str) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = _runtime_metadata_with_tenant_tables()
    table = runtime.tables["users"]
    column = table.c.tenant_id
    index = next(iter(table.indexes))
    if drift == "type":
        column.type = sa.String()
    elif drift == "nullable":
        column.nullable = False
    elif drift == "default":
        column.default = sa.ColumnDefault("unexpected")
    elif drift == "server_default":
        column.server_default = sa.DefaultClause("unexpected")
    elif drift == "primary_key":
        column.primary_key = True
    elif drift == "unique":
        column.unique = True
    elif drift == "foreign_key":
        column.append_foreign_key(sa.ForeignKey("users.id"))
    elif drift == "ondelete":
        next(iter(column.foreign_keys)).ondelete = "SET NULL"
    elif drift == "onupdate":
        next(iter(column.foreign_keys)).onupdate = "CASCADE"
    elif drift == "missing_index":
        table.indexes.clear()
    elif drift == "index_name":
        index.name = "other"
    elif drift == "index_unique":
        index.unique = True
    elif drift == "index_columns":
        table.indexes.clear()
        sa.Index("ix_users_tenant_id", table.c.id)
    elif drift == "index_options":
        index.dialect_kwargs["postgresql_where"] = column.is_not(None)
    elif drift == "extra_index":
        sa.Index("extra_tenant", column)
    with pytest.raises(ValueError, match="Runtime users tenant schema"):
        build_migration_metadata(runtime, dialect_name="postgresql")


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_runtime_users_missing_tenant_column_is_rejected_without_mutation(
    dialect: str,
) -> None:
    from app.core.db.retained_table_metadata import build_migration_metadata

    runtime = sa.MetaData()
    sa.Table("tenants", runtime, sa.Column("id", sa.UUID(), primary_key=True))
    users = sa.Table("users", runtime, sa.Column("id", sa.UUID(), primary_key=True))
    original_id = users.c.id

    with pytest.raises(ValueError, match="Runtime users tenant schema"):
        build_migration_metadata(runtime, dialect_name=dialect)

    assert set(runtime.tables) == {"users", "tenants"}
    assert tuple(users.c.keys()) == ("id",)
    assert users.c.id is original_id
    assert not users.indexes
