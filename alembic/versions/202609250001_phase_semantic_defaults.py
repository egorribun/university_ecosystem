"""Converge reviewed timestamp and native-role insert defaults (BE-02 phase four)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

import sqlalchemy as sa
from alembic import context, op

revision: str = "202609250001"
down_revision: str | None = "202609220001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class DefaultSpec(NamedTuple):
    table: str
    column: str
    expression: str
    kind: str


DEFAULT_SPECS: tuple[DefaultSpec, ...] = (
    DefaultSpec("attachments", "created_at", "now()", "timestamp"),
    DefaultSpec("chats", "created_at", "now()", "timestamp"),
    DefaultSpec("chats", "updated_at", "now()", "timestamp"),
    DefaultSpec("dead_letter_jobs", "created_at", "now()", "timestamp"),
    DefaultSpec("dead_letter_jobs", "updated_at", "now()", "timestamp"),
    DefaultSpec("failed_outbox_events", "failed_at", "now()", "timestamp"),
    DefaultSpec("grades", "created_at", "now()", "timestamp"),
    DefaultSpec("grades", "updated_at", "now()", "timestamp"),
    DefaultSpec("message_reactions", "created_at", "now()", "timestamp"),
    DefaultSpec("messages", "created_at", "now()", "timestamp"),
    DefaultSpec("stored_events", "created_at", "now()", "timestamp"),
    DefaultSpec("users", "role", "'student'::userrole", "role"),
)


class CatalogState(NamedTuple):
    data_type: str
    not_null: bool
    default_sql: str | None
    type_name: str
    type_kind: str
    type_schema_matches: bool
    null_count: int
    has_student_label: bool = True


def _catalog_state(bind: Any, spec: DefaultSpec, schema: str) -> CatalogState:
    row = (
        bind.execute(
            sa.text(
                """
                SELECT format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
                       attribute.attnotnull AS not_null,
                       pg_get_expr(definition.adbin, definition.adrelid) AS default_sql,
                       column_type.typname AS type_name,
                       column_type.typtype::text AS type_kind,
                       type_namespace.nspname = :schema_name AS type_schema_matches,
                       EXISTS (
                           SELECT 1 FROM pg_catalog.pg_enum AS label
                            WHERE label.enumtypid = attribute.atttypid
                              AND label.enumlabel = 'student'
                       ) AS has_student_label
                  FROM pg_catalog.pg_attribute AS attribute
                  JOIN pg_catalog.pg_class AS relation
                    ON relation.oid = attribute.attrelid
                  JOIN pg_catalog.pg_namespace AS table_namespace
                    ON table_namespace.oid = relation.relnamespace
                  JOIN pg_catalog.pg_type AS column_type
                    ON column_type.oid = attribute.atttypid
                  JOIN pg_catalog.pg_namespace AS type_namespace
                    ON type_namespace.oid = column_type.typnamespace
                  LEFT JOIN pg_catalog.pg_attrdef AS definition
                    ON definition.adrelid = attribute.attrelid
                   AND definition.adnum = attribute.attnum
                 WHERE table_namespace.nspname = :schema_name
                   AND relation.relname = :table_name
                   AND relation.relkind IN ('r', 'p')
                   AND attribute.attname = :column_name
                   AND attribute.attnum > 0
                   AND NOT attribute.attisdropped
                """
            ),
            {
                "schema_name": schema,
                "table_name": spec.table,
                "column_name": spec.column,
            },
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(f"BE-02 phase four requires {spec.table}.{spec.column}")
    null_count = 0
    if not row["not_null"]:
        table = sa.table(spec.table, sa.column(spec.column), schema=schema)
        null_count = int(
            bind.execute(
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.c[spec.column].is_(None))
            ).scalar_one()
        )
    return CatalogState(
        data_type=str(row["data_type"]).lower(),
        not_null=bool(row["not_null"]),
        default_sql=None if row["default_sql"] is None else str(row["default_sql"]),
        type_name=str(row["type_name"]),
        type_kind=str(row["type_kind"]),
        type_schema_matches=bool(row["type_schema_matches"]),
        null_count=null_count,
        has_student_label=bool(row["has_student_label"]),
    )


def _validate_state(spec: DefaultSpec, state: CatalogState) -> None:
    qualified = f"{spec.table}.{spec.column}"
    if spec.kind == "timestamp" and state.data_type != "timestamp with time zone":
        raise RuntimeError(f"BE-02 requires timestamptz for {qualified}")
    if spec.kind == "role":
        if state.type_name != "userrole":
            raise RuntimeError(f"BE-02 requires userrole for {qualified}")
        if state.type_kind != "e":
            raise RuntimeError(f"BE-02 requires a native enum for {qualified}")
        if not state.type_schema_matches:
            raise RuntimeError(
                f"BE-02 requires the current enum schema for {qualified}"
            )
        if not state.has_student_label:
            raise RuntimeError(f"BE-02 requires the student enum label for {qualified}")
    if not state.not_null:
        raise RuntimeError(f"BE-02 requires NOT NULL for {qualified}")
    if state.null_count:
        raise RuntimeError(f"BE-02 found NULL rows in {qualified}")
    if spec.kind == "timestamp" and state.default_sql is not None:
        if state.default_sql.strip().lower() not in {
            "now()",
            "current_timestamp",
            "transaction_timestamp()",
        }:
            raise RuntimeError(
                f"conflicting server default on {spec.table}.{spec.column}: "
                f"{state.default_sql!r}"
            )
    if spec.kind == "role" and state.default_sql is not None:
        if state.default_sql.strip() != "'student'::userrole":
            raise RuntimeError(
                f"conflicting server default on {qualified}: {state.default_sql!r}"
            )


def _run_upgrade(bind: Any) -> None:
    _lock_postgres()
    schema = _target_schema(bind)
    _lock_targets(bind, schema)
    # A drift in the last column must abort before the first ALTER TABLE.
    snapshots = [(spec, _catalog_state(bind, spec, schema)) for spec in DEFAULT_SPECS]
    for spec, state in snapshots:
        _validate_state(spec, state)
    for spec, state in snapshots:
        if state.default_sql is None:
            _apply_default(spec, schema)


def _apply_default(spec: DefaultSpec, schema: str) -> None:
    op.alter_column(
        spec.table,
        spec.column,
        schema=schema,
        server_default=sa.text(spec.expression),
        existing_nullable=False,
    )


def _lock_postgres() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    op.execute(sa.text("SELECT pg_advisory_xact_lock(824609250001)"))


def _target_schema(bind: Any) -> str:
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one_or_none()
    if not schema or not isinstance(schema, str):
        raise RuntimeError("BE-02 requires a current PostgreSQL schema")
    return schema


def _lock_targets(bind: Any, schema: str) -> None:
    preparer = bind.dialect.identifier_preparer
    qualified_schema = preparer.quote_identifier(schema)
    for table in sorted({spec.table for spec in DEFAULT_SPECS}):
        qualified_table = preparer.quote_identifier(table)
        op.execute(
            sa.text(
                f"LOCK TABLE {qualified_schema}.{qualified_table} "
                "IN ACCESS EXCLUSIVE MODE"
            )
        )


def _abort_offline() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN RAISE EXCEPTION "
            "'BE-02 202609250001 requires online PostgreSQL catalog preflight'; "
            "END $$;"
        )
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _abort_offline()
        return
    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    _run_upgrade(bind)


def downgrade() -> None:
    """Retain equivalent defaults: their origin on a deployed DB is unknown."""

    if context.is_offline_mode():
        _abort_offline()
        return
    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    _lock_postgres()
    schema = _target_schema(bind)
    _lock_targets(bind, schema)
    for spec in DEFAULT_SPECS:
        state = _catalog_state(bind, spec, schema)
        _validate_state(spec, state)
        if state.default_sql is None:
            raise RuntimeError(
                f"BE-02 missing server default on {spec.table}.{spec.column}"
            )
