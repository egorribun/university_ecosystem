"""Drop legacy INT columns after UUID migration

Revision ID: 202602010004
Revises: 202602010003
Create Date: 2026-02-01 06:00:00.000000

"""

from alembic import op

revision = "202602010004"
down_revision = "202602010003"

TABLES_TO_CLEANUP = []

# (Table, Legacy FK Col)
FK_TO_CLEANUP = []


def upgrade():
    # 1. Drop the legacy primary key columns
    for table in TABLES_TO_CLEANUP:
        op.drop_column(table, "legacy_id")

    # 2. Drop the legacy foreign key columns
    for table, legacy_col in FK_TO_CLEANUP:
        op.drop_column(table, legacy_col)


def downgrade():
    # Adding columns back is complex because we've lost the data.
    # We would need to re-verify or restore from backup.
    # Leaving as pass for safety in this cutover phase.
    pass
