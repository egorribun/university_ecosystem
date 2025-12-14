"""Add English localization fields to events"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202501200001"
down_revision = "65319a2b1d7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("events"):
        return
    existing = {column["name"] for column in inspector.get_columns("events")}

    if "title_en" not in existing:
        op.add_column("events", sa.Column("title_en", sa.String(), nullable=True))
    if "description_en" not in existing:
        op.add_column("events", sa.Column("description_en", sa.Text(), nullable=True))
    if "location_en" not in existing:
        op.add_column("events", sa.Column("location_en", sa.String(), nullable=True))
    if "event_type_en" not in existing:
        op.add_column("events", sa.Column("event_type_en", sa.String(), nullable=True))
    if "about_en" not in existing:
        op.add_column("events", sa.Column("about_en", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("events"):
        return
    op.drop_column("events", "about_en")
    op.drop_column("events", "event_type_en")
    op.drop_column("events", "location_en")
    op.drop_column("events", "description_en")
    op.drop_column("events", "title_en")
