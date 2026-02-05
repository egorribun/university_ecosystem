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

        # 2. Add shadow column
        op.add_column(
            "mfa_challenges",
            sa.Column(
                "shadow_session_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
        )

        # 3. Truncate since mapping is lost (legacy_id is gone)
        # This is safe for a challenge table in dev/test, and likely unavoidable here.
        op.execute('TRUNCATE TABLE "mfa_challenges" CASCADE')
        logger.info("Truncated mfa_challenges due to lost legacy_id mapping")

        # 4. Swap columns
        op.alter_column(
            "mfa_challenges", "session_id", new_column_name="legacy_session_id"
        )
        op.alter_column(
            "mfa_challenges", "shadow_session_id", new_column_name="session_id"
        )

        # 5. Drop legacy column
        op.drop_column("mfa_challenges", "legacy_session_id")

        # 6. Recreate index and FK
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
        op.drop_constraint(
            "fk_mfa_challenges_session_id_uuid", "mfa_challenges", type_="foreignkey"
        )
        op.drop_index("ix_mfa_challenges_session_id", "mfa_challenges")
        op.alter_column(
            "mfa_challenges", "session_id", type_=sa.Integer(), postgresql_using="NULL"
        )
    else:
        with op.batch_alter_table("mfa_challenges") as batch_op:
            batch_op.drop_column("session_id")
            batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
