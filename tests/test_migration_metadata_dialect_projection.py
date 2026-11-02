"""Dialect-specific audit-log primary keys must change migration clones only."""

from __future__ import annotations

import warnings
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.core.db.retained_table_metadata import build_migration_metadata


def _runtime_metadata(primary_key: tuple[str, ...]) -> sa.MetaData:
    metadata = sa.MetaData(naming_convention={"pk": "pk_%(table_name)s"})
    sa.Table("users", metadata, sa.Column("id", sa.UUID(), primary_key=True))
    log = sa.Table(
        "data_access_logs",
        metadata,
        sa.Column(
            "id",
            sa.UUID(),
            primary_key="id" in primary_key,
            default=uuid4,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            primary_key="created_at" in primary_key,
            nullable=False,
            default=lambda: datetime.now(UTC),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actor_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            primary_key="actor_user_id" in primary_key,
            nullable=True,
        ),
        sa.Column("payload", sa.String(64), default="retained", nullable=False),
        sa.PrimaryKeyConstraint(
            *primary_key,
            name="audit_log_pk",
            deferrable=True,
            initially="DEFERRED",
            info={"owner": "audit-log"},
            mssql_clustered=False,
        ),
        info={"retained": "table-info"},
        postgresql_partition_by="RANGE (created_at)",
    )
    sa.Index("ix_audit_actor", log.c.actor_user_id)
    return metadata


def _non_primary_key_snapshot(table: sa.Table):
    return (
        table.name,
        table.schema,
        dict(table.info),
        dict(table.dialect_kwargs),
        tuple(
            (
                column.name,
                str(column.type),
                column.nullable,
                column.default.arg if column.default is not None else None,
                (
                    str(column.server_default.arg)
                    if column.server_default is not None
                    else None
                ),
                dict(column.info),
            )
            for column in table.c
        ),
        tuple(
            sorted(
                (foreign.parent.name, foreign.target_fullname, foreign.ondelete)
                for foreign in table.foreign_keys
            )
        ),
        tuple(
            sorted(
                (
                    index.name,
                    tuple(str(expr) for expr in index.expressions),
                    index.unique,
                )
                for index in table.indexes
            )
        ),
    )


@pytest.mark.parametrize(
    "source_key", [("id",), ("created_at", "id")], ids=["sqlite", "postgresql"]
)
@pytest.mark.parametrize(
    ("target_dialect", "target_key"),
    [("sqlite", ("id",)), ("postgresql", ("id", "created_at"))],
)
def test_known_audit_primary_key_projection_preserves_every_other_attribute(
    source_key, target_dialect, target_key
) -> None:
    runtime = _runtime_metadata(source_key)
    original = runtime.tables["data_access_logs"]
    original_key = original.primary_key
    snapshot = _non_primary_key_snapshot(original)
    target = build_migration_metadata(runtime, dialect_name=target_dialect)
    copied = target.tables["data_access_logs"]

    assert copied is not original
    assert tuple(copied.primary_key.columns.keys()) == target_key
    assert tuple(original.primary_key.columns.keys()) == source_key
    assert original.primary_key is original_key
    assert _non_primary_key_snapshot(original) == snapshot
    assert _non_primary_key_snapshot(copied) == snapshot
    assert copied.primary_key.name == original_key.name
    assert copied.primary_key.deferrable == original_key.deferrable
    assert copied.primary_key.initially == original_key.initially
    assert copied.primary_key.info == original_key.info
    assert dict(copied.primary_key.dialect_kwargs) == dict(original_key.dialect_kwargs)


def test_sequential_targets_do_not_mutate_each_other_or_runtime_mappers() -> None:
    from app import models
    from app.core.database import Base as RuntimeBase
    from app.core.db.base import Base

    assert RuntimeBase is models.Base is Base
    mapper = sa.inspect(models.DataAccessLog)
    before_mapper_key = tuple(mapper.primary_key)
    original = Base.metadata.tables["data_access_logs"]
    before_key = tuple(original.primary_key.columns)
    before = _non_primary_key_snapshot(original)
    registry = Base.registry
    targets = [
        build_migration_metadata(Base.metadata, dialect_name=dialect)
        for dialect in ("sqlite", "postgresql", "sqlite")
    ]
    expected = [("id",), ("id", "created_at"), ("id",)]
    assert [
        tuple(target.tables["data_access_logs"].primary_key.columns.keys())
        for target in targets
    ] == expected
    assert tuple(mapper.primary_key) == before_mapper_key
    assert tuple(original.primary_key.columns) == before_key
    assert _non_primary_key_snapshot(original) == before
    assert RuntimeBase.registry is Base.registry is registry
    assert all(target is not Base.metadata for target in targets)
    assert len({id(target.tables["data_access_logs"]) for target in targets}) == 3


@pytest.mark.parametrize(
    "key",
    [(), ("actor_user_id",), ("id", "actor_user_id")],
)
def test_unrecognized_primary_key_is_rejected_without_runtime_mutation(key) -> None:
    runtime = _runtime_metadata(key)
    table = runtime.tables["data_access_logs"]
    before = tuple(table.primary_key.columns)
    with pytest.raises(ValueError, match="unrecognized primary key"):
        build_migration_metadata(runtime, dialect_name="postgresql")
    assert tuple(table.primary_key.columns) == before


def test_missing_audit_key_column_is_rejected() -> None:
    runtime = sa.MetaData()
    sa.Table("data_access_logs", runtime, sa.Column("id", sa.UUID(), primary_key=True))
    with pytest.raises(ValueError, match="missing a primary-key column"):
        build_migration_metadata(runtime, dialect_name="postgresql")


def test_builder_rejects_inconsistent_primary_key_flags_before_copying() -> None:
    runtime = _runtime_metadata(("id",))
    table = runtime.tables["data_access_logs"]
    original_key = table.primary_key
    table.c.created_at.primary_key = True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(ValueError, match="flags disagree"):
            build_migration_metadata(runtime, dialect_name="postgresql")

    assert caught == []
    assert table.primary_key is original_key
    assert tuple(table.primary_key.columns.keys()) == ("id",)
    assert table.c.created_at.primary_key is True


def test_projection_keeps_explicit_nullability_drift_visible() -> None:
    runtime = _runtime_metadata(("id",))
    runtime.tables["data_access_logs"].c.created_at.nullable = True
    target = build_migration_metadata(runtime, dialect_name="postgresql")
    assert target.tables["data_access_logs"].c.created_at.nullable is True
    assert runtime.tables["data_access_logs"].c.created_at.nullable is True


@pytest.mark.parametrize(
    "source_key", [("id",), ("id", "created_at"), ("created_at", "id")]
)
@pytest.mark.parametrize("target_dialect", ["sqlite", "postgresql"])
def test_builder_preserves_conditional_primary_key_ddl(
    source_key, target_dialect
) -> None:
    runtime = _runtime_metadata(source_key)
    table = runtime.tables["data_access_logs"]
    original_key = table.primary_key
    state = {"retained": True}

    def condition(*args, **kwargs):
        return True

    original_key.ddl_if(dialect="postgresql", callable_=condition, state=state)
    original_condition = original_key._ddl_if
    target = build_migration_metadata(runtime, dialect_name=target_dialect)
    copied_key = target.tables["data_access_logs"].primary_key

    assert copied_key._ddl_if.dialect == "postgresql"
    assert copied_key._ddl_if.callable_ is condition
    assert copied_key._ddl_if.state is state
    assert table.primary_key is original_key
    assert original_key._ddl_if is original_condition
    assert tuple(original_key.columns.keys()) == source_key


@pytest.mark.parametrize(
    "source_key", [("id",), ("id", "created_at"), ("created_at", "id")]
)
@pytest.mark.parametrize("target_dialect", ["sqlite", "postgresql"])
def test_builder_preserves_propagated_primary_key_ddl_listeners(
    source_key, target_dialect
) -> None:
    runtime = _runtime_metadata(source_key)
    original_key = runtime.tables["data_access_logs"].primary_key
    events = []

    def before_create(target, connection, **kwargs):
        assert connection is None
        events.append(("before", target))

    def after_create(target, connection, **kwargs):
        assert connection is None
        events.append(("after", target))

    def original_only(target, connection, **kwargs):
        assert connection is None
        events.append(("original-only", target))

    sa.event.listen(original_key, "before_create", before_create, propagate=True)
    sa.event.listen(original_key, "after_create", after_create, propagate=True)
    sa.event.listen(original_key, "before_create", original_only, propagate=False)
    target = build_migration_metadata(runtime, dialect_name=target_dialect)
    copied_key = target.tables["data_access_logs"].primary_key

    # Exercise listener dispatch without creating a database or executing DDL.
    copied_key.dispatch.before_create(copied_key, None)
    copied_key.dispatch.after_create(copied_key, None)
    assert events == [("before", copied_key), ("after", copied_key)]

    original_key.dispatch.before_create(original_key, None)
    original_key.dispatch.after_create(original_key, None)
    assert events == [
        ("before", copied_key),
        ("after", copied_key),
        ("before", original_key),
        ("original-only", original_key),
        ("after", original_key),
    ]
    assert runtime.tables["data_access_logs"].primary_key is original_key
    assert tuple(original_key.columns.keys()) == source_key
