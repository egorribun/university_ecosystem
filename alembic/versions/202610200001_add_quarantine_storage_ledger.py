"""Add durable storage-scoped reservations for rejected upload quarantine.

The ledger is intentionally irreversible: dropping it would release the
cross-process byte charges while quarantined objects could still exist.
"""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "202610200001"
down_revision = "202610120002"
branch_labels = None
depends_on = None

downgrade_policy = "irreversible"
downgrade_reason = (
    "Quarantine reservation ledger is irreversible: dropping it would release "
    "quota charges for objects that may still exist"
)


_SCOPES = "quarantine_storage_scopes"
_RESERVATIONS = "quarantine_reservations"


def _current_schema(bind: sa.Connection) -> str:
    schema = bind.execute(sa.text("SELECT current_schema()")).scalar_one()
    if not isinstance(schema, str) or not schema:
        raise RuntimeError("Cannot resolve current schema for quarantine ledger")
    return schema


def _emit_ledger_ddl(operations: Any) -> None:
    operations.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    operations.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    operations.create_table(
        _SCOPES,
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column(
            "inventory_complete",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("inventory_cursor", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("scope_id"),
    )
    operations.create_table(
        _RESERVATIONS,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=2048), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name="ck_quarantine_reservation_size"),
        sa.CheckConstraint(
            "status IN ('pending', 'stored', 'deleting')",
            name="ck_quarantine_reservation_status",
        ),
        sa.ForeignKeyConstraint(["scope_id"], [f"{_SCOPES}.scope_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scope_id", "object_key", name="uq_quarantine_reservation_object"
        ),
    )
    operations.create_index(
        "ix_quarantine_reservations_expiry",
        _RESERVATIONS,
        ["scope_id", "status", "expires_at"],
    )


def upgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError("Quarantine ledger migration requires online PostgreSQL")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Quarantine ledger migration requires PostgreSQL")
    schema = _current_schema(bind)
    inspector = sa.inspect(bind)
    if inspector.has_table(_SCOPES, schema=schema) or inspector.has_table(
        _RESERVATIONS, schema=schema
    ):
        raise RuntimeError("Existing quarantine ledger tables require manual review")
    _emit_ledger_ddl(op)


def downgrade() -> None:
    raise RuntimeError(
        "Quarantine reservation ledger is irreversible: dropping it would release "
        "quota charges for objects that may still exist"
    )
