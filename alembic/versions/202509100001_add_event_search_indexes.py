"""Add PostgreSQL search index for events."""

from __future__ import annotations


import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "202509100001"
down_revision: str | Sequence[str] | None = "202509010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIMARY_INDEX_NAME = "ix_events_search_text"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Check if events table exists before creating index
    inspector = sa.inspect(bind)
    if not inspector.has_table("events"):
        return

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"""
            CREATE INDEX IF NOT EXISTS {_PRIMARY_INDEX_NAME}
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


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        sa.text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            f"DROP INDEX IF EXISTS {_PRIMARY_INDEX_NAME}"
        )
    )
