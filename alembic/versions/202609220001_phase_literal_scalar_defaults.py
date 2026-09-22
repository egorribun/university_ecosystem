"""Phase three of the BE-02 dual-default convergence.

Phase one converged the authentication domain's boolean flags.  This phase
takes the next class ADR-036 names: the Python-only declarations whose default
is a **literal, non-secret scalar**.  Twenty-nine columns qualify -- seven
booleans, eleven integers, five floats and six short enumerated strings --
across the dead-letter, events, chat, notification, schedule, Spotify, stats
and vector domains.

What is deliberately excluded, and why:

* the thirty-seven UUIDv7 primary keys, whose default is a Python generator
  with no PostgreSQL equivalent that preserves identity semantics;
* the eleven timestamps, which belong to their own phase because ``now()`` and
  a Python ``datetime.now(UTC)`` disagree about clock authority inside a
  transaction;
* ``active_sessions.signing_key``, whose default is secret material generated
  per row and must never be expressed as a catalog default;
* the two JSON columns defaulting to ``list``, which need a reviewed
  ``'[]'::json`` decision of their own;
* ``users.role``, whose default is a member of the native ``userrole`` enum.
  Its catalog form is ``'student'::userrole``, a cast to a named type rather
  than a literal in any of the four families below -- the type-family guard
  would abort on it, correctly, so it belongs to an enum phase of its own.

Those five groups and the twenty-nine columns here account for all fifty-two
remaining Python-only declarations; nothing is unclassified.

The structure mirrors revision 202609150001 exactly: fail-closed catalog
preflight, bounded NULL backfill, ``NOT VALID`` check validated before
``SET NOT NULL``, server default installed last, and a contract-preserving
downgrade because Alembic cannot prove ownership of equivalent objects that
pre-date this revision on an operator-managed database.
"""

# Ruff's S608 heuristic cannot follow `_quote_identifier`; every interpolated
# identifier is regex-validated and dialect-quoted, and every literal comes
# from the immutable DEFAULT_SPECS tuple below.  The dynamic statements
# therefore have no user-controlled SQL fragments.
# ruff: noqa: S608

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, NamedTuple

import sqlalchemy as sa
from alembic import context, op

revision: str = "202609220001"
down_revision: str | None = "202609150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCK_ID = 824_609_220_001
_BACKFILL_BATCH_SIZE = 1_000
_OFFLINE_ABORT = (
    "DO $$ BEGIN RAISE EXCEPTION "
    "'BE-02 202609220001 requires online PostgreSQL catalog preflight'; "
    "END $$;"
)

# Accepted catalog spellings per declared family.  A column whose deployed type
# is outside its family aborts the phase rather than receiving a default whose
# literal PostgreSQL may coerce differently than the ORM does.
_TYPE_FAMILIES: dict[str, frozenset[str]] = {
    "boolean": frozenset({"boolean", "bool"}),
    "integer": frozenset({"integer", "int4", "bigint", "int8", "smallint", "int2"}),
    "float": frozenset(
        {"double precision", "float8", "real", "float4", "numeric", "decimal"}
    ),
    "text": frozenset({"text", "character varying", "varchar"}),
}


class DefaultSpec(NamedTuple):
    """One reviewed literal default with its PostgreSQL representation."""

    table: str
    column: str
    server_default: str
    family: str

    @property
    def constraint_name(self) -> str:
        return f"ck_be02_{self.table}_{self.column}_not_null"


# Explicit and reviewable, in the same spirit as phase one.  Each literal is
# the exact scalar the ORM already applies, transcribed once.
DEFAULT_SPECS: tuple[DefaultSpec, ...] = (
    DefaultSpec("dead_letter_jobs", "max_retries", "3", "integer"),
    DefaultSpec("dead_letter_jobs", "retry_count", "0", "integer"),
    DefaultSpec("dead_letter_jobs", "status", "'pending'", "text"),
    DefaultSpec("events", "is_active", "true", "boolean"),
    DefaultSpec("failed_outbox_events", "retry_count", "0", "integer"),
    DefaultSpec("grades", "assessment_type", "'exam'", "text"),
    DefaultSpec("messages", "read_status", "false", "boolean"),
    DefaultSpec("notification_deliveries", "channel", "'inapp'", "text"),
    DefaultSpec("notification_deliveries", "status", "'delivered'", "text"),
    DefaultSpec("notifications", "read", "false", "boolean"),
    DefaultSpec("schedule", "parity", "'both'", "text"),
    DefaultSpec("spotify_integrations", "is_connected", "false", "boolean"),
    DefaultSpec("spotify_integrations", "is_playing", "false", "boolean"),
    DefaultSpec("stored_events", "error_count", "0", "integer"),
    DefaultSpec("stored_events", "status", "'pending'", "text"),
    DefaultSpec("stored_events", "version", "1", "integer"),
    DefaultSpec("user_preferences", "dnd_enabled", "false", "boolean"),
    DefaultSpec("user_stats", "attendance_percent", "0.0", "float"),
    DefaultSpec("user_stats", "attendance_present", "0", "integer"),
    DefaultSpec("user_stats", "attendance_total", "0", "integer"),
    DefaultSpec("user_stats", "attendance_trend", "0.0", "float"),
    DefaultSpec("user_stats", "grades_average", "0.0", "float"),
    DefaultSpec("user_stats", "grades_trend", "0.0", "float"),
    DefaultSpec("user_stats", "participation_events", "0", "integer"),
    DefaultSpec("user_stats", "participation_groups", "0", "integer"),
    DefaultSpec("user_stats", "participation_hours", "0.0", "float"),
    DefaultSpec("user_stats", "participation_trend", "0", "integer"),
    DefaultSpec("vector_chunks", "chunk_index", "0", "integer"),
    DefaultSpec("vector_chunks", "is_active", "true", "boolean"),
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
            f"BE-02 literal-scalar phase requires {spec.table}.{spec.column}"
        )
    data_type = str(row["data_type"]).lower()
    # ``character varying(32)`` and friends carry a length modifier.
    base_type = data_type.split("(", 1)[0].strip()
    accepted = _TYPE_FAMILIES[spec.family]
    if base_type not in accepted:
        raise RuntimeError(
            f"BE-02 requires a {spec.family} column for {spec.table}.{spec.column}, "
            f"found {data_type!r}"
        )
    default_sql = row["default_sql"]
    return CatalogState(
        data_type=data_type,
        not_null=bool(row["not_null"]),
        default_sql=None if default_sql is None else str(default_sql),
    )


def _normalize_sql(value: str, family: str) -> str | None:
    """Recognise only a literal wrapped in parentheses and same-family casts.

    String payloads are opaque: case, whitespace, quotes and numeric-looking
    text must remain exact.  PostgreSQL may quote numeric defaults (for
    example ``'0'::double precision``), so only numeric families coerce those
    spellings.  Unknown expressions, casts and type modifiers fail closed.
    """

    match = re.match(
        r"\s*(?P<opening>(?:\(\s*)*)"
        r"(?P<literal>'(?:[^']|'')*'|true|false|-?\d+(?:\.\d+)?)",
        value,
        re.IGNORECASE,
    )
    if match is None:
        return None
    depth = match["opening"].count("(")
    remainder = value[match.end() :].strip()
    while remainder:
        if remainder.startswith(")"):
            depth -= 1
            if depth < 0:
                return None
            remainder = remainder[1:].strip()
            continue
        cast = re.match(
            r"::\s*(character\s+varying|double\s+precision|[a-z][a-z0-9_]*)",
            remainder,
            re.IGNORECASE,
        )
        if cast is None:
            return None
        cast_type = " ".join(cast[1].lower().split())
        if cast_type not in _TYPE_FAMILIES[family]:
            return None
        remainder = remainder[cast.end() :].strip()
    if depth:
        return None
    literal = match["literal"]
    if family == "text":
        return literal if literal.startswith("'") else None
    normalized = literal.strip("'").lower()
    # ``0.0`` and ``0`` are equivalent floats, but not equivalent text.
    if family == "float" and re.fullmatch(r"-?\d+\.0+", normalized):
        normalized = normalized.split(".", 1)[0]
    return normalized


def _expected_default(spec: DefaultSpec) -> str | None:
    return _normalize_sql(spec.server_default, spec.family)


def _validate_existing_default(spec: DefaultSpec, state: CatalogState) -> None:
    """Reject a conflicting operator default instead of overwriting it."""

    if state.default_sql is None:
        return
    if _normalize_sql(state.default_sql, spec.family) != _expected_default(spec):
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
    normalized = re.sub(r'[\s()"]+', "", definition).lower()
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
    # Snapshot every column before any DDL so a conflict anywhere aborts the
    # phase before the first table is touched.
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
    regressing.  A later phase owns any deliberate rollback policy once
    catalog provenance is available.
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
