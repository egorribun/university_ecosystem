"""Add generated search_vector column for events."""

from __future__ import annotations


import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "202509200001"
down_revision: str | Sequence[str] | None = "202509100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_INDEX_NAME = "ix_events_search_vector"
_OLD_INDEX_NAME = "ix_events_search_text"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    # Check if events table exists
    if "events" not in inspector.get_table_names():
        return

    if dialect != "postgresql":
        # SQLite keeps a plain column for compatibility even though full-text
        # search falls back to LIKE queries in application code.
        existing = {column["name"] for column in inspector.get_columns("events")}
        if "search_vector" not in existing:
            op.add_column(
                "events", sa.Column("search_vector", sa.Text(), nullable=True)
            )
        return

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"DROP INDEX IF EXISTS {_OLD_INDEX_NAME}"
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "ALTER TABLE events DROP COLUMN IF EXISTS search_vector"
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            """
            ALTER TABLE events
            ADD COLUMN search_vector tsvector
            GENERATED ALWAYS AS (
                to_tsvector(
                    'simple'::regconfig,
                    coalesce(title, '')
                    || ' ' || coalesce(description, '')
                    || ' ' || coalesce(location, '')
                    || ' ' || coalesce(title_en, '')
                    || ' ' || coalesce(description_en, '')
                    || ' ' || coalesce(location_en, '')
                    || ' ' || coalesce(about, '')
                    || ' ' || coalesce(about_en, '')
                )
            ) STORED
            """
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"""
            CREATE INDEX IF NOT EXISTS {_NEW_INDEX_NAME}
            ON events
            USING gin (search_vector)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    # Check if events table exists
    if "events" not in inspector.get_table_names():
        return

    if dialect != "postgresql":
        op.drop_column("events", "search_vector")
        return

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"DROP INDEX IF EXISTS {_NEW_INDEX_NAME}"
        )
    )
    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            "ALTER TABLE events DROP COLUMN IF EXISTS search_vector"
        )
    )

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"""
            CREATE INDEX IF NOT EXISTS {_OLD_INDEX_NAME}
            ON events
            USING gin (
                to_tsvector(
                    'simple'::regconfig,
                    coalesce(title, '')
                    || ' ' || coalesce(description, '')
                    || ' ' || coalesce(location, '')
                    || ' ' || coalesce(title_en, '')
                    || ' ' || coalesce(description_en, '')
                    || ' ' || coalesce(location_en, '')
                    || ' ' || coalesce(about, '')
                    || ' ' || coalesce(about_en, '')
                )
            )
            """
        )
    )
