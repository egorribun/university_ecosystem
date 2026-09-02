"""Restore constraints lost by legacy range-partition table rebuilds.

``202607020001`` can rebuild a regular heap into a partitioned parent.  Its
column-only copy intentionally omitted the parent primary key, foreign keys,
and indexes.  This additive reconciliation restores the contracts declared by
the partitioned audit/notification models.  Existing objects are
validated before any DDL is issued; a same-name or same-column mismatch fails
closed instead of silently replacing an operator-owned constraint.

Downgrade is deliberately non-destructive.  Alembic does not persist object
ownership, so removing an index or constraint by name could delete a contract
that predates this revision.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision: str = "202608270003"
down_revision: str | None = "202608270002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCK_ID = 824_270_003


@dataclass(frozen=True)
class ForeignKeySpec:
    name: str
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    ondelete: str


@dataclass(frozen=True)
class TableContract:
    partition_key: str
    primary_key: tuple[str, ...]
    indexes: tuple[tuple[str, tuple[str, ...]], ...]
    foreign_keys: tuple[ForeignKeySpec, ...]
    unique_constraints: tuple[tuple[str, tuple[str, ...]], ...] = ()


_TABLE_CONTRACTS: dict[str, TableContract] = {
    "data_access_logs": TableContract(
        partition_key="created_at",
        primary_key=("id", "created_at"),
        indexes=(
            ("ix_data_access_logs_action", ("action",)),
            ("ix_data_access_logs_actor_user_id", ("actor_user_id",)),
            ("ix_data_access_logs_created_at", ("created_at",)),
            ("ix_data_access_logs_resource_id", ("resource_id",)),
            ("ix_data_access_logs_resource_type", ("resource_type",)),
            ("ix_data_access_logs_subject_user_id", ("subject_user_id",)),
        ),
        foreign_keys=(
            ForeignKeySpec(
                name="fk_data_access_logs_actor_user_id",
                columns=("actor_user_id",),
                referred_table="users",
                referred_columns=("id",),
                ondelete="SET NULL",
            ),
            ForeignKeySpec(
                name="fk_data_access_logs_subject_user_id",
                columns=("subject_user_id",),
                referred_table="users",
                referred_columns=("id",),
                ondelete="SET NULL",
            ),
        ),
    ),
    "failed_login_attempts": TableContract(
        partition_key="attempted_at",
        primary_key=("id", "attempted_at"),
        indexes=(
            ("ix_failed_login_attempts_attempted_at", ("attempted_at",)),
            ("ix_failed_login_attempts_email", ("email",)),
            (
                "ix_failed_login_attempts_email_attempted_at",
                ("email", "attempted_at"),
            ),
            ("ix_failed_login_attempts_ip_address", ("ip_address",)),
            (
                "ix_failed_login_attempts_ip_attempted_at",
                ("ip_address", "attempted_at"),
            ),
            ("ix_failed_login_attempts_user_id", ("user_id",)),
        ),
        foreign_keys=(
            ForeignKeySpec(
                name="fk_failed_login_attempts_user_id",
                columns=("user_id",),
                referred_table="users",
                referred_columns=("id",),
                ondelete="SET NULL",
            ),
        ),
    ),
    "notifications": TableContract(
        partition_key="created_at",
        primary_key=("id", "created_at"),
        indexes=(
            ("ix_notifications_created_at", ("created_at",)),
            ("ix_notifications_dedupe_key", ("dedupe_key",)),
            ("ix_notifications_dupe_check", ("user_id", "title", "url", "created_at")),
            ("ix_notifications_read", ("read",)),
            ("ix_notifications_read_at", ("read_at",)),
            ("ix_notifications_title", ("title",)),
            ("ix_notifications_type", ("type",)),
            ("ix_notifications_user_created", ("user_id", "created_at")),
            ("ix_notifications_user_dedupe", ("user_id", "dedupe_key")),
            ("ix_notifications_user_id", ("user_id",)),
            ("ix_notifications_user_id_read", ("user_id", "read")),
        ),
        foreign_keys=(
            ForeignKeySpec(
                name="fk_notifications_user_id",
                columns=("user_id",),
                referred_table="users",
                referred_columns=("id",),
                ondelete="CASCADE",
            ),
        ),
    ),
    "notification_deliveries": TableContract(
        partition_key="attempted_at",
        primary_key=("id", "attempted_at"),
        indexes=(
            ("ix_notification_deliveries_attempted_at", ("attempted_at",)),
            ("ix_notification_deliveries_channel", ("channel",)),
            (
                "ix_notification_deliveries_dedup",
                ("notification_id", "channel", "subscription_id"),
            ),
            ("ix_notification_deliveries_delivered_at", ("delivered_at",)),
            (
                "ix_notification_deliveries_notif_channel",
                ("notification_id", "channel"),
            ),
            ("ix_notification_deliveries_notification_id", ("notification_id",)),
            ("ix_notification_deliveries_status", ("status",)),
            ("ix_notification_deliveries_subscription_id", ("subscription_id",)),
        ),
        foreign_keys=(
            ForeignKeySpec(
                name="fk_notification_deliveries_notification",
                columns=("notification_id", "notification_created_at"),
                referred_table="notifications",
                referred_columns=("id", "created_at"),
                ondelete="CASCADE",
            ),
        ),
        unique_constraints=(
            (
                "uq_notification_delivery_once",
                ("notification_id", "channel", "subscription_id", "attempted_at"),
            ),
        ),
    ),
}


def _primary_key_matches(definition: dict[str, Any], columns: tuple[str, ...]) -> bool:
    return tuple(definition.get("constrained_columns") or ()) == columns


def _foreign_key_matches(definition: dict[str, Any], expected: ForeignKeySpec) -> bool:
    options = definition.get("options") or {}
    return (
        tuple(definition.get("constrained_columns") or ()) == expected.columns
        and definition.get("referred_table") == expected.referred_table
        and tuple(definition.get("referred_columns") or ()) == expected.referred_columns
        and str(options.get("ondelete", "")).upper() == expected.ondelete.upper()
    )


def _index_matches(
    definition: dict[str, Any], columns: tuple[str, ...], *, unique: bool = False
) -> bool:
    return (
        tuple(definition.get("column_names") or ()) == columns
        and bool(definition.get("unique", False)) is unique
    )


def _unique_matches(definition: dict[str, Any], columns: tuple[str, ...]) -> bool:
    return tuple(definition.get("column_names") or ()) == columns


def _assert_existing_or_missing(
    table: str,
    object_label: str,
    definitions: Sequence[dict[str, Any]],
    expected: Any,
    matcher: Callable[[dict[str, Any], Any], bool],
) -> bool:
    """Return whether an equivalent object exists; reject non-equivalent drift."""

    if any(matcher(definition, expected) for definition in definitions):
        return True
    if definitions:
        raise RuntimeError(
            f"Existing {object_label} on {table!r} does not match the schema contract"
        )
    return False


def _get_relkind(bind: Any, table: str) -> str | None:
    row = bind.execute(
        sa.text(
            "SELECT c.relkind FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE c.relname = :table_name AND n.nspname = current_schema()"
        ),
        {"table_name": table},
    ).first()
    if row is None:
        return None
    # asyncpg returns PostgreSQL's ``char`` catalog values as bytes; other
    # drivers return text.  Normalize the representation so a real ``p`` or
    # ``r`` relation is never rejected merely because of its DBAPI driver.
    value = row[0]
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def _partition_key_matches(bind: Any, table: str, expected: str) -> bool:
    """Return whether a parent uses the expected RANGE column as its key.

    PostgreSQL allows a partitioned relation to use HASH, LIST, or an
    expression key while still exposing a composite primary key.  Restoring
    the audit contract on such a relation would create a superficially valid
    but operationally incorrect schema, so validate the catalog strategy and
    ordered attribute list before issuing any repair DDL.
    """

    rows = bind.execute(
        sa.text(
            "SELECT pt.partstrat, attribute.attname "
            "FROM pg_partitioned_table AS pt "
            "JOIN pg_class AS relation ON relation.oid = pt.partrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "JOIN LATERAL unnest(pt.partattrs) WITH ORDINALITY "
            "AS key(attnum, ordinal) ON TRUE "
            "JOIN pg_attribute AS attribute "
            "ON attribute.attrelid = relation.oid AND attribute.attnum = key.attnum "
            "WHERE relation.relname = :table_name "
            "AND namespace.nspname = current_schema() "
            "ORDER BY key.ordinal"
        ),
        {"table_name": table},
    ).fetchall()
    if not rows:
        return False
    strategy = rows[0][0]
    if isinstance(strategy, bytes):
        strategy = strategy.decode("ascii")
    return str(strategy) == "r" and tuple(row[1] for row in rows) == (expected,)


def _lock_postgresql(bind: Any) -> None:
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
            sa.bindparam("lock_id", value=_LOCK_ID, literal_execute=True)
        )
    )


def _require_columns(inspector: Any, table: str, contract: TableContract) -> None:
    columns = {item["name"] for item in inspector.get_columns(table)}
    required = set(contract.primary_key)
    required.update(column for _, columns_ in contract.indexes for column in columns_)
    for foreign_key in contract.foreign_keys:
        required.update(foreign_key.columns)
    for _, columns_ in contract.unique_constraints:
        required.update(columns_)
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            f"Partitioned schema reconciliation requires {table} columns: {', '.join(missing)}"
        )


def _ensure_primary_key(
    bind: Any, inspector: Any, table: str, contract: TableContract
) -> None:
    expected = contract.primary_key
    current = inspector.get_pk_constraint(table)
    if _primary_key_matches(current, expected):
        return
    if current.get("constrained_columns"):
        raise RuntimeError(
            f"Existing primary key on {table!r} does not match the schema contract"
        )
    name = f"{table}_pkey"
    for index in inspector.get_indexes(table):
        if index.get("name") == name:
            raise RuntimeError(
                f"Existing index {name!r} blocks creation of the {table!r} primary key"
            )
    op.create_primary_key(name, table, list(expected))


def _ensure_foreign_key(inspector: Any, table: str, expected: ForeignKeySpec) -> None:
    definitions = inspector.get_foreign_keys(table)
    if any(_foreign_key_matches(definition, expected) for definition in definitions):
        return
    same_columns = [
        definition
        for definition in definitions
        if tuple(definition.get("constrained_columns") or ()) == expected.columns
    ]
    if same_columns:
        raise RuntimeError(
            f"Existing foreign key on {table!r} columns {expected.columns!r} "
            "does not match the schema contract"
        )
    op.create_foreign_key(
        expected.name,
        table,
        expected.referred_table,
        list(expected.columns),
        list(expected.referred_columns),
        ondelete=expected.ondelete,
    )


def _ensure_indexes(inspector: Any, table: str, contract: TableContract) -> None:
    existing = {index.get("name"): index for index in inspector.get_indexes(table)}
    for name, columns in contract.indexes:
        definition = existing.get(name)
        if definition is not None:
            if not _index_matches(definition, columns):
                raise RuntimeError(
                    f"Existing index {name!r} on {table!r} does not match the schema contract"
                )
            continue
        op.create_index(name, table, list(columns), unique=False)


def _ensure_unique_constraints(
    inspector: Any, table: str, contract: TableContract
) -> None:
    constraints = inspector.get_unique_constraints(table)
    indexes = inspector.get_indexes(table)
    for name, columns in contract.unique_constraints:
        named = [
            constraint for constraint in constraints if constraint.get("name") == name
        ]
        if named:
            if not any(_unique_matches(constraint, columns) for constraint in named):
                raise RuntimeError(
                    f"Existing unique constraint {name!r} on {table!r} does not match the schema contract"
                )
            continue
        if any(
            _unique_matches(index, columns) and bool(index.get("unique"))
            for index in indexes
        ):
            continue
        op.create_unique_constraint(name, table, list(columns))


def upgrade() -> None:
    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql" or context.is_offline_mode():
        return
    _lock_postgresql(bind)
    inspector = sa.inspect(bind)
    for table, contract in _TABLE_CONTRACTS.items():
        if not inspector.has_table(table):
            raise RuntimeError(
                f"Partitioned schema reconciliation requires table {table!r}"
            )
        relkind = _get_relkind(bind, table)
        if relkind not in {"p", "r"}:
            raise RuntimeError(
                f"Table {table!r} has unsupported PostgreSQL relkind {relkind!r}"
            )
        if relkind == "p" and not _partition_key_matches(
            bind, table, contract.partition_key
        ):
            raise RuntimeError(
                f"Table {table!r} is not RANGE-partitioned by {contract.partition_key!r}"
            )
        _require_columns(inspector, table, contract)
        _ensure_primary_key(bind, inspector, table, contract)
        _ensure_unique_constraints(inspector, table, contract)
        _ensure_indexes(inspector, table, contract)
        for foreign_key in contract.foreign_keys:
            _ensure_foreign_key(inspector, table, foreign_key)


def downgrade() -> None:
    """Keep repaired objects because Alembic cannot prove ownership."""

    return
