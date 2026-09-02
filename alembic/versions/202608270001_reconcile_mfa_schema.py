"""Reconcile the post-contract MFA schema with the ORM metadata.

The WebAuthn retirement migration intentionally used validated ``CHECK``
constraints while the deployment was expanded.  PostgreSQL still reports the
columns as nullable to Alembic, however, and the indexes declared by the
runtime models were not part of that destructive migration.  This migration
is the narrow, additive follow-up: it proves that no NULL values remain,
verifies those checks remain validated, and creates the model indexes.  The
catalog-level nullable representation is reconciled by the explicit,
check-backed Alembic comparator in ``scripts/quality/alembic_schema_drift.py``
so this migration never takes an ``ACCESS EXCLUSIVE`` lock to rewrite a live
table.  Downgrade is deliberately non-destructive: because indexes can
pre-date this revision, it never drops them without durable ownership
provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision: str = "202608270001"
down_revision: str | None = "202608250003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCK_ID = 824_270_001

# Keep the explicit check names here so the migration can prove that the
# logical NOT NULL contract from 202608250002 was not lost.  We intentionally
# do not issue ``ALTER COLUMN ... SET NOT NULL`` here: PostgreSQL's catalog
# remains nullable by design and the comparator proves the validated checks
# before suppressing only that exact metadata diff.
_REQUIRED_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine[Any]], ...] = (
    ("mfa_challenges", "flow", sa.String(length=32)),
    ("mfa_challenges", "session_identifier", sa.String(length=128)),
    ("mfa_challenges", "client_fingerprint", sa.String(length=64)),
    ("mfa_challenges", "method", sa.String(length=20)),
    ("mfa_challenges", "revision", sa.Integer()),
    ("mfa_challenges", "token_digest", sa.String(length=64)),
    ("mfa_challenges", "token_key_id", sa.String(length=64)),
    ("trusted_devices", "token_key_id", sa.String(length=64)),
    ("trusted_devices", "binding_digest", sa.String(length=64)),
)

_MODEL_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_mfa_challenges_flow", "mfa_challenges", ("flow",)),
    ("ix_mfa_challenges_method", "mfa_challenges", ("method",)),
    (
        "ix_mfa_challenges_resend_available_at",
        "mfa_challenges",
        ("resend_available_at",),
    ),
    (
        "ix_mfa_challenges_session_identifier",
        "mfa_challenges",
        ("session_identifier",),
    ),
    ("ix_users_email_mfa_enabled_at", "users", ("email_mfa_enabled_at",)),
    ("ix_users_email_verified_at", "users", ("email_verified_at",)),
)


def _inspector(bind: Any) -> Any:
    return sa.inspect(bind)


def _assert_required_tables_and_columns(bind: Any) -> None:
    """Fail closed instead of silently producing a partial schema."""

    if context.is_offline_mode():
        return
    inspector = _inspector(bind)
    for table, column, _ in _REQUIRED_COLUMNS:
        if not inspector.has_table(table):
            raise RuntimeError(f"MFA schema reconciliation requires table {table!r}")
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in columns:
            raise RuntimeError(f"MFA schema reconciliation requires {table}.{column}")


def _assert_validated_contract_checks(bind: Any) -> None:
    """Fail closed if the logical NOT NULL checks are absent or unvalidated."""

    if bind.dialect.name != "postgresql":
        return
    if context.is_offline_mode():
        return
    for table, column, _ in _REQUIRED_COLUMNS:
        constraint_name = f"ck_{table}_{column}_not_null"
        row = bind.execute(
            sa.text(
                """
                SELECT convalidated, pg_get_constraintdef(c.oid)
                FROM pg_constraint AS c
                WHERE c.conrelid = to_regclass(:table_name)
                  AND c.conname = :constraint_name
                  AND c.contype = 'c'
                """
            ),
            {"table_name": table, "constraint_name": constraint_name},
        ).first()
        normalized = "" if row is None else " ".join(str(row[1]).split()).upper()
        expected = f"CHECK (({column.upper()} IS NOT NULL))"
        if row is None or row[0] is not True or normalized != expected:
            raise RuntimeError(
                f"MFA schema reconciliation requires validated {constraint_name}"
            )


def _create_model_indexes(bind: Any) -> None:
    existing_by_table = {
        table: {item["name"] for item in _inspector(bind).get_indexes(table)}
        for _, table, _ in _MODEL_INDEXES
    }
    for name, table, columns in _MODEL_INDEXES:
        if name not in existing_by_table[table]:
            op.create_index(name, table, list(columns), unique=False)


def _drop_model_indexes(_bind: Any) -> None:
    """Keep additive model indexes during downgrade.

    The reconciliation is intentionally idempotent: an index may have been
    created by an operator, ``Base.metadata.create_all`` in a test harness, or
    this revision itself.  Alembic does not retain which actor created an
    existing index, so a rollback that drops by name could delete a baseline
    object it does not own.  These indexes are additive and remain valid for
    the parent revision, therefore downgrade is explicitly non-destructive.
    """

    # Deliberately no-op in both online and offline modes.  Keeping the
    # objects also makes generated rollback SQL deterministic and safe when
    # applied to a database whose pre-reconciliation catalog is unknown.
    return


def _lock_postgresql(bind: Any) -> None:
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(
        sa.text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
            sa.bindparam("lock_id", value=_LOCK_ID, literal_execute=True)
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _lock_postgresql(bind)
    _assert_required_tables_and_columns(bind)
    _assert_validated_contract_checks(bind)
    _create_model_indexes(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _lock_postgresql(bind)
    _drop_model_indexes(bind)
