"""Phase one of the BE-02 dual-default convergence.

This revision is intentionally limited to non-secret boolean flags owned by
the authentication/registration domain.  It does not guess defaults for
timestamps, JSON values, UUIDv7 identities, enums, or secret material.

PostgreSQL upgrades are fail-closed: the catalog is checked before any DDL,
existing NULLs are backfilled in bounded batches, a validated NOT VALID check
is used as the online path to NOT NULL, and only then is the server default
installed.  The downgrade preserves the resulting contract because Alembic
cannot prove whether an equivalent default or constraint pre-dated this
revision on an operator-managed database.
"""

# Ruff's S608 heuristic cannot follow `_quote_identifier`; every interpolated
# identifier is regex-validated and dialect-quoted, and every literal comes
# from the immutable DEFAULT_SPECS tuple above.  The two dynamic statements
# therefore have no user-controlled SQL fragments.
# ruff: noqa: S608

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, NamedTuple

import sqlalchemy as sa
from alembic import context, op

revision: str = "202609150001"
down_revision: str | None = "202608270003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCK_ID = 824_609_150_001
_BACKFILL_BATCH_SIZE = 1_000
_OFFLINE_ABORT = (
    "DO $$ BEGIN RAISE EXCEPTION "
    "'BE-02 202609150001 requires online PostgreSQL catalog preflight'; "
    "END $$;"
)


class DefaultSpec(NamedTuple):
    """One reviewed scalar default with a literal PostgreSQL representation."""

    table: str
    column: str
    server_default: str

    @property
    def constraint_name(self) -> str:
        return f"ck_be02_{self.table}_{self.column}_not_null"


# Keep this list explicit and reviewable.  It is the owner-scoped first phase,
# not a mechanical rewrite of the complete model-default inventory.
DEFAULT_SPECS: tuple[DefaultSpec, ...] = (
    DefaultSpec("active_sessions", "mfa_required", "false"),
    DefaultSpec("mfa_totp_enrollments", "is_active", "false"),
    DefaultSpec("password_reset_tokens", "used", "false"),
    DefaultSpec("email_change_tokens", "used", "false"),
    DefaultSpec("recovery_codes", "is_used", "false"),
    DefaultSpec("login_history", "is_suspicious", "false"),
    DefaultSpec("users", "is_active", "true"),
    DefaultSpec("users", "mfa_required", "false"),
    DefaultSpec("invite_codes", "is_active", "true"),
    DefaultSpec("invite_codes", "is_used", "false"),
)


class CatalogState(NamedTuple):
    """Small immutable snapshot used to make each phase decision explicit."""

    data_type: str
    not_null: bool
    default_sql: str | None


def _quote_identifier(bind: Any, value: str) -> str:
    """Quote only migration-owned identifiers and reject unexpected names."""

    if re.fullmatch(r"[a-z_][a-z0-9_]*", value) is None:
        raise RuntimeError(f"unsafe migration identifier: {value!r}")
    return bind.dialect.identifier_preparer.quote(value)


def _catalog_state(bind: Any, spec: DefaultSpec) -> CatalogState:
    """Read type, nullability and DDL default from the current PostgreSQL catalog."""

    row = (
        bind.execute(
            sa.text(
                """
            SELECT format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
                   attribute.attnotnull AS not_null,
                   pg_get_expr(definition.adbin, definition.adrelid) AS default_sql
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            LEFT JOIN pg_catalog.pg_attrdef AS definition
              ON definition.adrelid = attribute.attrelid
             AND definition.adnum = attribute.attnum
            WHERE namespace.nspname = current_schema()
              AND relation.relname = :table_name
              AND attribute.attname = :column_name
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            """
            ),
            {"table_name": spec.table, "column_name": spec.column},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(
            f"BE-02 auth-default phase requires {spec.table}.{spec.column}"
        )
    data_type = str(row["data_type"]).lower()
    if data_type not in {"boolean", "bool"}:
        raise RuntimeError(
            f"BE-02 requires boolean {spec.table}.{spec.column}, found {data_type!r}"
        )
    default_sql = row["default_sql"]
    return CatalogState(
        data_type=data_type,
        not_null=bool(row["not_null"]),
        default_sql=None if default_sql is None else str(default_sql),
    )


def _normalize_sql(value: str) -> str:
    normalized = re.sub(r"[\s\"]+", "", value).lower()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return normalized.replace("::boolean", "")


def _validate_existing_default(spec: DefaultSpec, state: CatalogState) -> None:
    """Reject a conflicting operator default instead of overwriting it."""

    if state.default_sql is None:
        return
    if _normalize_sql(state.default_sql) != spec.server_default:
        raise RuntimeError(
            f"conflicting server default on {spec.table}.{spec.column}: "
            f"expected {spec.server_default!r}, found {state.default_sql!r}"
        )


def _constraint_rows(bind: Any, spec: DefaultSpec) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT constraint_name,
                   convalidated,
                   pg_get_constraintdef(constraint_oid) AS definition
            FROM (
                SELECT constr.conname AS constraint_name,
                       constr.convalidated,
                       constr.oid AS constraint_oid
                FROM pg_catalog.pg_constraint AS constr
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constr.conrelid
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = :table_name
                  AND constr.contype = 'c'
            ) AS checks
            """
        ),
        {"table_name": spec.table},
    ).mappings()
    return [dict(row) for row in rows]


def _is_not_null_check(definition: str, column: str) -> bool:
    normalized = re.sub(r"[\s()\"]+", "", definition).lower()
    return normalized == f"check{column.lower()}isnotnull"


def _matching_check(bind: Any, spec: DefaultSpec) -> tuple[str | None, bool, bool]:
    """Return (constraint name, validated, added-by-this-phase-candidate)."""

    rows = _constraint_rows(bind, spec)
    for row in rows:
        name = str(row["constraint_name"])
        definition = str(row["definition"])
        if name == spec.constraint_name and not _is_not_null_check(
            definition, spec.column
        ):
            raise RuntimeError(
                f"existing {spec.constraint_name!r} on {spec.table} has an "
                "unexpected definition"
            )
    for row in rows:
        if _is_not_null_check(str(row["definition"]), spec.column):
            return str(row["constraint_name"]), bool(row["convalidated"]), False
    return None, False, True


def _null_count(bind: Any, spec: DefaultSpec) -> int:
    table = _quote_identifier(bind, spec.table)
    column = _quote_identifier(bind, spec.column)
    result = bind.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- identifiers are validated and quoted above
            f"SELECT count(*) FROM {table} WHERE {column} IS NULL"
        )
    )
    return int(result.scalar_one())


def _backfill_nulls(bind: Any, spec: DefaultSpec) -> None:
    """Backfill NULLs in bounded, retry-safe batches before validation."""

    remaining = _null_count(bind, spec)
    if remaining == 0:
        return
    table = _quote_identifier(bind, spec.table)
    column = _quote_identifier(bind, spec.column)
    while remaining:
        result = bind.execute(
            sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- identifiers and literal are migration constants
                f"""
                UPDATE {table}
                   SET {column} = {spec.server_default}
                 WHERE ctid IN (
                    SELECT ctid
                      FROM {table}
                     WHERE {column} IS NULL
                     LIMIT :batch_size
                 )
                """
            ),
            {"batch_size": _BACKFILL_BATCH_SIZE},
        )
        updated = int(result.rowcount or 0)
        if updated <= 0:
            raise RuntimeError(
                f"BE-02 backfill made no progress for {spec.table}.{spec.column}"
            )
        remaining = _null_count(bind, spec)


def _execute_ddl(bind: Any, statement: str) -> None:
    """Execute a statement assembled solely from validated migration constants."""

    op.execute(
        sa.text(
            statement
        )  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text -- all identifiers and literals are migration constants
    )


def _ensure_not_null_contract(
    bind: Any, spec: DefaultSpec, state: CatalogState
) -> None:
    constraint_name, validated, may_add = _matching_check(bind, spec)
    if constraint_name is None and may_add and not state.not_null:
        table = _quote_identifier(bind, spec.table)
        column = _quote_identifier(bind, spec.column)
        name = _quote_identifier(bind, spec.constraint_name)
        _execute_ddl(
            bind,
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"CHECK ({column} IS NOT NULL) NOT VALID",
        )
        constraint_name = spec.constraint_name
        validated = False
    if constraint_name is not None and not validated:
        table = _quote_identifier(bind, spec.table)
        name = _quote_identifier(bind, constraint_name)
        _execute_ddl(bind, f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
    if not state.not_null:
        table = _quote_identifier(bind, spec.table)
        column = _quote_identifier(bind, spec.column)
        _execute_ddl(bind, f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")


def _set_server_default(bind: Any, spec: DefaultSpec, state: CatalogState) -> None:
    if state.default_sql is not None:
        return
    table = _quote_identifier(bind, spec.table)
    column = _quote_identifier(bind, spec.column)
    _execute_ddl(
        bind,
        f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {spec.server_default}",
    )


def _lock_postgresql() -> None:
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    op.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
            sa.bindparam("lock_id", value=_LOCK_ID, literal_execute=True)
        )
    )


def _run_upgrade(bind: Any) -> None:
    _lock_postgresql()
    snapshots = [(spec, _catalog_state(bind, spec)) for spec in DEFAULT_SPECS]
    for spec, state in snapshots:
        _validate_existing_default(spec, state)
    for spec, state in snapshots:
        _backfill_nulls(bind, spec)
        _ensure_not_null_contract(bind, spec, state)
        _set_server_default(bind, spec, state)


def _abort_offline_upgrade() -> None:
    """Prevent an offline script from recording a schema change it cannot prove."""

    op.execute(sa.text(_OFFLINE_ABORT))


def upgrade() -> None:
    bind = op.get_bind()
    if context.is_offline_mode():
        _abort_offline_upgrade()
        return
    if bind is None or bind.dialect.name != "postgresql":
        return
    _run_upgrade(bind)


def downgrade() -> None:
    """Preserve the dual-default contract on an operator-managed database.

    The phase is additive.  Removing a matching default or check during
    downgrade could delete an equivalent object installed before this
    revision, while retaining it is data-safe and keeps direct writers from
    regressing.  The next migration phase owns any deliberate rollback
    policy after catalog provenance is available.
    """

    bind = op.get_bind()
    if context.is_offline_mode():
        _abort_offline_upgrade()
        return
    if bind is None or bind.dialect.name != "postgresql":
        return
    _lock_postgresql()
    for spec in DEFAULT_SPECS:
        state = _catalog_state(bind, spec)
        _validate_existing_default(spec, state)
