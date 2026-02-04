"""cleanup spotify legacy

Revision ID: 202602040002
Revises: 202602040001
Create Date: 2026-02-04 19:15:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202602040002"
down_revision = "202602040001"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("spotify_integrations")]

    if "legacy_user_id" in columns:
        op.drop_column("spotify_integrations", "legacy_user_id")


def downgrade():
    # We cannot easily restore legacy_user_id without data loss or complex logic
    op.add_column(
        "spotify_integrations", sa.Column("legacy_user_id", sa.Integer(), nullable=True)
    )
