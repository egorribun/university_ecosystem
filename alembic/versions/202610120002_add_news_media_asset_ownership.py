"""Track ownership and exclusive news association for generated news images.

Downgrade intentionally keeps this additive table. Older application code
ignores the table, while dropping it could erase the only ownership evidence
for uploaded objects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from alembic import op


revision = "202610120002"
down_revision = "202610120001"
branch_labels = None
depends_on = None

_TABLE = "news_media_assets"


def _is_uuid(column: dict[str, Any]) -> bool:
    return isinstance(column["type"], sa.Uuid)


def _is_storage_url(column: dict[str, Any]) -> bool:
    return isinstance(column["type"], sa.String) and column["type"].length == 2048


def _is_created_at(column: dict[str, Any]) -> bool:
    return isinstance(column["type"], sa.DateTime) and column["type"].timezone


def _schema(bind: sa.Connection) -> str:
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
    if not isinstance(schema, str) or not schema:
        raise RuntimeError("Cannot resolve current schema for news media assets")
    return schema


def _assert_exact_existing_schema(bind: sa.Connection, schema: str) -> None:
    """Fail closed when a preexisting table differs from this revision's DDL."""
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(_TABLE, schema=schema)
    expected_names = (
        "id",
        "storage_url",
        "owner_user_id",
        "news_id",
        "created_at",
    )
    if tuple(column["name"] for column in columns) != expected_names:
        raise RuntimeError("Existing news_media_assets has unexpected columns")

    by_name = {column["name"]: column for column in columns}
    expected: tuple[
        tuple[str, Callable[[dict[str, Any]], bool], bool, str | None], ...
    ] = (
        ("id", _is_uuid, False, None),
        ("storage_url", _is_storage_url, False, None),
        ("owner_user_id", _is_uuid, True, None),
        ("news_id", _is_uuid, True, None),
        ("created_at", _is_created_at, False, "now"),
    )
    for name, type_matches, nullable, server_default in expected:
        column = by_name[name]
        if not type_matches(column) or column["nullable"] is not nullable:
            raise RuntimeError(f"Existing news_media_assets.{name} is incompatible")
        actual_default = column.get("default")
        if server_default is None:
            if actual_default is not None:
                raise RuntimeError(
                    f"Existing news_media_assets.{name} has an unexpected default"
                )
        elif (
            not isinstance(actual_default, str)
            or "".join(ch for ch in actual_default.lower() if ch.isalnum())
            != server_default
        ):
            raise RuntimeError(
                f"Existing news_media_assets.{name} has an unexpected default"
            )
        if column.get("identity") is not None or column.get("computed") is not None:
            raise RuntimeError(
                f"Existing news_media_assets.{name} has generated-column metadata"
            )

    primary_key = inspector.get_pk_constraint(_TABLE, schema=schema)
    if tuple(primary_key.get("constrained_columns") or ()) != ("id",):
        raise RuntimeError("Existing news_media_assets has an unexpected primary key")
    primary_key_options = primary_key.get("dialect_options") or {}
    if primary_key_options.get("postgresql_include") or set(primary_key_options) - {
        "postgresql_include"
    }:
        raise RuntimeError(
            "Existing news_media_assets has modified primary key options"
        )

    reflected_unique_constraints = inspector.get_unique_constraints(
        _TABLE, schema=schema
    )
    for constraint in reflected_unique_constraints:
        options = constraint.get("dialect_options") or {}
        if (
            options.get("postgresql_include")
            or options.get("postgresql_nulls_not_distinct", False)
            or set(options)
            - {
                "postgresql_include",
                "postgresql_nulls_not_distinct",
            }
        ):
            raise RuntimeError(
                "Existing news_media_assets has modified unique constraints"
            )

    unique_constraints = {
        (constraint.get("name"), tuple(constraint.get("column_names") or ()))
        for constraint in reflected_unique_constraints
    }
    expected_unique_constraints = {
        ("uq_news_media_asset_storage_url", ("storage_url",)),
        ("uq_news_media_asset_news_id", ("news_id",)),
    }
    if unique_constraints != expected_unique_constraints:
        raise RuntimeError(
            "Existing news_media_assets has unexpected unique constraints"
        )

    constraint_flags = bind.execute(
        sa.text(
            """
            SELECT constraint_row.conname,
                   constraint_row.condeferrable,
                   constraint_row.condeferred
            FROM pg_catalog.pg_constraint AS constraint_row
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = constraint_row.conrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = :schema
              AND relation.relname = :table
              AND constraint_row.contype IN ('p', 'u', 'f')
            """
        ),
        {"schema": schema, "table": _TABLE},
    ).mappings()
    if any(row["condeferrable"] or row["condeferred"] for row in constraint_flags):
        raise RuntimeError("Existing news_media_assets has deferrable constraints")

    foreign_keys = set()
    for foreign_key in inspector.get_foreign_keys(_TABLE, schema=schema):
        options = foreign_key.get("options") or {}
        referred_schema = foreign_key.get("referred_schema")
        if referred_schema not in (None, schema):
            raise RuntimeError("Existing news_media_assets has an external foreign key")
        foreign_keys.add(
            (
                foreign_key.get("name"),
                tuple(foreign_key.get("constrained_columns") or ()),
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                str(options.get("ondelete", "")).upper(),
            )
        )
    expected_foreign_keys = {
        (
            "news_media_assets_owner_user_id_fkey",
            ("owner_user_id",),
            "users",
            ("id",),
            "SET NULL",
        ),
        (
            "news_media_assets_news_id_fkey",
            ("news_id",),
            "news",
            ("id",),
            "SET NULL",
        ),
    }
    if foreign_keys != expected_foreign_keys:
        raise RuntimeError("Existing news_media_assets has unexpected foreign keys")

    if inspector.get_check_constraints(_TABLE, schema=schema):
        raise RuntimeError(
            "Existing news_media_assets has unexpected check constraints"
        )

    unique_constraint_names = {name for name, _columns in expected_unique_constraints}
    reflected_indexes = [
        index
        for index in inspector.get_indexes(_TABLE, schema=schema)
        if index.get("duplicates_constraint") is None
        and index.get("name") not in unique_constraint_names
    ]
    for index in reflected_indexes:
        dialect_options = index.get("dialect_options")
        if dialect_options is None:
            dialect_options = {}
        has_only_default_dialect_options = (
            isinstance(dialect_options, dict)
            and set(dialect_options) <= {"postgresql_include"}
            and (
                "postgresql_include" not in dialect_options
                or (
                    type(dialect_options["postgresql_include"]) is list
                    and not dialect_options["postgresql_include"]
                )
            )
        )
        if (
            index.get("expressions")
            or index.get("include_columns")
            or index.get("column_sorting")
            or not has_only_default_dialect_options
        ):
            raise RuntimeError("Existing news_media_assets has modified indexes")

    indexes = {
        (
            index.get("name"),
            tuple(index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in reflected_indexes
    }
    expected_indexes = {
        ("ix_news_media_assets_owner_user_id", ("owner_user_id",), False)
    }
    if indexes != expected_indexes:
        raise RuntimeError("Existing news_media_assets has unexpected indexes")


def upgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError("News media ownership migration requires online PostgreSQL")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("News media ownership migration requires PostgreSQL")
    schema = _schema(bind)
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE, schema=schema):
        _assert_exact_existing_schema(bind, schema)
        return

    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    op.create_table(
        _TABLE,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("storage_url", sa.String(length=2048), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("news_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["news_id"], ["news.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_url", name="uq_news_media_asset_storage_url"),
        sa.UniqueConstraint("news_id", name="uq_news_media_asset_news_id"),
    )
    op.create_index(
        "ix_news_media_assets_owner_user_id",
        _TABLE,
        ["owner_user_id"],
    )


def downgrade() -> None:
    """Keep ownership evidence; earlier application revisions ignore this table."""
