"""Fix mfa_challenges session_id type mismatch

Revision ID: 202602050001
Revises: 202602010004
Create Date: 2026-02-05 05:05:00.000000

"""

import logging

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "202602050001"
down_revision = "202602040002"
branch_labels = None
depends_on = None


def upgrade():
    logger = logging.getLogger("alembic")
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. Drop existing FK if it exists
    # We use a raw SQL approach for Postgres since inspector might be stale
    if dialect == "postgresql":
        # Find FK name
        result = bind.execute(
            sa.text("""
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'mfa_challenges'::regclass
            AND contype = 'f'
            AND confrelid = 'active_sessions'::regclass
        """)
        ).fetchone()

        if result:
            fk_name = result[0]
            op.drop_constraint(fk_name, "mfa_challenges", type_="foreignkey")
            logger.info(f"Dropped FK {fk_name} from mfa_challenges")

        # 2. Check current column type — the UUID cutover (202602010003) may
        # have already converted session_id, or it may still be INTEGER.
        col_type_row = bind.execute(
            sa.text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'mfa_challenges' AND column_name = 'session_id'
        """)
        ).fetchone()
        current_type = col_type_row[0] if col_type_row else None
        logger.info("mfa_challenges.session_id current type: %s", current_type)

        if current_type and current_type.lower() == "uuid":
            # Already UUID (e.g. from the UUID cutover) — nothing to convert.
            logger.info("session_id is already UUID — skipping type conversion")
        else:
            # Still INTEGER — old FK values are orphaned after UUID cutover.
            # Drop the integer column and recreate as UUID.
            op.drop_column("mfa_challenges", "session_id")
            op.add_column(
                "mfa_challenges",
                sa.Column(
                    "session_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )
            logger.info("Replaced integer session_id with UUID column")

        # 3. Recreate index and FK
        op.create_index(
            "ix_mfa_challenges_session_id", "mfa_challenges", ["session_id"]
        )
        op.create_foreign_key(
            "fk_mfa_challenges_session_id_uuid",
            "mfa_challenges",
            "active_sessions",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )
        logger.info("Successfully converted mfa_challenges.session_id to UUID")
    else:
        # Non-PostgreSQL path (testing/dev)
        with op.batch_alter_table("mfa_challenges") as batch_op:
            batch_op.drop_column("session_id")
            batch_op.add_column(sa.Column("session_id", sa.UUID(), nullable=True))
            batch_op.create_foreign_key(
                "fk_mfa_challenges_session_id_uuid",
                "active_sessions",
                ["session_id"],
                ["id"],
                ondelete="CASCADE",
            )


def downgrade():
    # Simplistic downgrade - switch back to INTEGER, but data is already lost
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE mfa_challenges "
                "DROP CONSTRAINT IF EXISTS fk_mfa_challenges_session_id_uuid"
            )
        )
        op.execute(sa.text("DROP INDEX IF EXISTS ix_mfa_challenges_session_id"))
        op.alter_column(
            "mfa_challenges", "session_id", type_=sa.Integer(), postgresql_using="NULL"
        )
    else:
        with op.batch_alter_table("mfa_challenges") as batch_op:
            batch_op.drop_column("session_id")
            batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
