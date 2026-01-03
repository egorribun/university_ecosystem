"""Add indexes to support attendance stats query"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202506250001"
down_revision: str | None = "202506200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_index(
    inspector: sa.Inspector, table_name: str, column_names: Sequence[str]
) -> bool:
    # Check if table exists first
    if table_name not in inspector.get_table_names():
        return True  # Return True to skip index creation
    normalized = tuple(column_names)
    for index in inspector.get_indexes(table_name):
        if tuple(index.get("column_names", [])) == normalized:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "events" in table_names and not _has_index(inspector, "events", ("starts_at",)):
        op.create_index("ix_events_starts_at", "events", ["starts_at"])

    if "event_attendance" in table_names and not _has_index(inspector, "event_attendance", ("user_id",)):
        op.create_index("ix_event_attendance_user_id", "event_attendance", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "event_attendance" in table_names:
        op.drop_index("ix_event_attendance_user_id", table_name="event_attendance")
    if "events" in table_names:
        op.drop_index("ix_events_starts_at", table_name="events")

