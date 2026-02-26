"""add_outbox_notification_trigger

Revision ID: 4e39503c07cd
Revises: f2d2414a6b67
Create Date: 2026-02-25 00:40:11.702571

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4e39503c07cd"
down_revision: str | None = "f2d2414a6b67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add outbox notification trigger."""
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION notify_outbox_event()
            RETURNS TRIGGER AS $$
            BEGIN
                PERFORM pg_notify('outbox_events', '');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS trg_notify_outbox_event ON stored_events;
            CREATE TRIGGER trg_notify_outbox_event
            AFTER INSERT ON stored_events
            FOR EACH STATEMENT
            EXECUTE FUNCTION notify_outbox_event();
            """
        )
    )


def downgrade() -> None:
    """Remove outbox notification trigger."""
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS trg_notify_outbox_event ON stored_events;")
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS notify_outbox_event();"))
