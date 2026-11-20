"""Add a generation for push subscription bindings.

Revision ID: 202611200001
Revises: 202611020000

Preflight: the baseline must be applied and ``public.push_subscriptions`` must
exist. An existing ``binding_version`` is accepted only when the Alembic ledger
records this successor and the column is nullable BIGINT without a default,
identity, generated expression, column constraint or direct unique index. The
table lock keeps this targeted preflight and idempotent addition in one transaction.

The nullable column has no server default and requires no row backfill. A
physical NULL represents logical generation zero to the consuming application.
The metadata-only addition still requires a PostgreSQL table lock; lock waits
are limited to 10 seconds and statements to 60 seconds.

Downgrade drops only the generation. It loses generation history, so quiesce
in-flight push sends and roll back the consuming application with the schema.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "202611200001"
down_revision: str = "202611020000"
branch_labels = None
depends_on = None


def _set_timeouts() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.execute("SET LOCAL statement_timeout = '60s'")


def upgrade() -> None:
    _set_timeouts()
    op.execute("LOCK TABLE public.push_subscriptions IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute AS attribute
            WHERE attribute.attrelid = 'public.push_subscriptions'::regclass
              AND attribute.attname = 'binding_version'
              AND attribute.attnum > 0 AND NOT attribute.attisdropped
          ) THEN
            IF pg_catalog.to_regclass('public.alembic_version') IS NULL THEN
              RAISE EXCEPTION 'push binding column has no successor ledger';
            END IF;
            IF (SELECT count(*) FROM public.alembic_version) <> 1
              OR NOT EXISTS (
                SELECT 1 FROM public.alembic_version
                WHERE version_num = '202611200001'
              ) THEN
              RAISE EXCEPTION 'push binding column predates successor ledger';
            END IF;
          END IF;
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute AS attribute
            WHERE attribute.attrelid = 'public.push_subscriptions'::regclass
              AND attribute.attname = 'binding_version'
              AND attribute.attnum > 0 AND NOT attribute.attisdropped
              AND (
                attribute.atttypid <> 'pg_catalog.int8'::regtype
                OR attribute.atttypmod <> -1
                OR attribute.attnotnull OR attribute.atthasdef
                OR attribute.attidentity <> '' OR attribute.attgenerated <> ''
                OR EXISTS (
                  SELECT 1 FROM pg_catalog.pg_constraint AS constraint_row
                  WHERE constraint_row.conrelid = attribute.attrelid
                    AND attribute.attnum = ANY (constraint_row.conkey)
                )
                OR EXISTS (
                  SELECT 1 FROM pg_catalog.pg_index AS index_row
                  WHERE index_row.indrelid = attribute.attrelid
                    AND index_row.indisunique
                    AND attribute.attnum = ANY (index_row.indkey)
                )
              )
          ) THEN
            RAISE EXCEPTION 'push subscription binding_version has incompatible schema';
          END IF;
        END $$
        """
    )
    op.add_column(
        "push_subscriptions",
        sa.Column("binding_version", sa.BigInteger(), nullable=True),
        schema="public",
        if_not_exists=True,
    )


def downgrade() -> None:
    _set_timeouts()
    op.drop_column("push_subscriptions", "binding_version", schema="public")
