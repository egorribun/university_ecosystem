"""add schedule and news indexes"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "c8d0b5515f2d"
down_revision: str | None = "933372f5da9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create indexes for frequent schedule and news queries."""
    if context.is_offline_mode():
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_schedule_group_week_parity_date
            ON schedule (group_id, week_parity, date)
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_news_published_at_desc
            ON news (published_at DESC)
            """
        )
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("schedule"):
        schedule_columns = {col["name"] for col in inspector.get_columns("schedule")}
        if {"group_id", "week_parity", "date"}.issubset(schedule_columns):
            op.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_schedule_group_week_parity_date
                ON schedule (group_id, week_parity, date)
                """
            )
        elif {"group_id", "parity", "start_time"}.issubset(schedule_columns):
            op.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_schedule_group_week_parity_date
                ON schedule (group_id, parity, start_time)
                """
            )
        else:
            raise RuntimeError(
                "Expected schedule columns for index creation were not found."
            )

    if inspector.has_table("news"):
        news_columns = {col["name"] for col in inspector.get_columns("news")}
        if "published_at" in news_columns:
            op.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_news_published_at_desc
                ON news (published_at DESC)
                """
            )
        elif "created_at" in news_columns:
            op.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_news_published_at_desc
                ON news (created_at DESC)
                """
            )
        else:
            raise RuntimeError(
                "Expected news timestamp column for index creation was not found."
            )


def downgrade() -> None:
    """Drop schedule and news indexes."""
    op.execute("DROP INDEX IF EXISTS ix_schedule_group_week_parity_date")
    op.execute("DROP INDEX IF EXISTS ix_news_published_at_desc")
