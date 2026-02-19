"""Create user push topic preferences table."""

from __future__ import annotations


import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# revision identifiers, used by Alembic.
revision: str = "202506260001"
down_revision: str | None = "202506250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE_NAME = "user_push_topics"

_PUSH_SUBSCRIPTIONS = sa.table(
    "push_subscriptions",
    sa.column("user_id", sa.Integer()),
    sa.column("topics", sa.JSON()),
)

_USER_PUSH_TOPICS = sa.table(
    _TABLE_NAME,
    sa.column("user_id", sa.Integer()),
    sa.column("topics", sa.JSON()),
)


def _normalize_topics(raw: Iterable[object] | None) -> list[str]:
    if not raw:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        candidate = str(item).strip().lower()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _populate_existing_data() -> None:
    bind = op.get_bind()
    result = bind.execute(
        sa.select(_PUSH_SUBSCRIPTIONS.c.user_id, _PUSH_SUBSCRIPTIONS.c.topics)
    )
    aggregated: dict[int, list[str]] = {}
    for user_id, topics in result:
        if user_id is None:
            continue
        normalized = _normalize_topics(topics)
        if not normalized:
            continue
        existing = aggregated.setdefault(int(user_id), [])
        for topic in normalized:
            if topic not in existing:
                existing.append(topic)
    if not aggregated:
        return
    rows = [
        {"user_id": user_id, "topics": topics} for user_id, topics in aggregated.items()
    ]
    op.bulk_insert(_USER_PUSH_TOPICS, rows)


def upgrade() -> None:
    """Create the user push topic preferences table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("topics", sa.JSON(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_user_push_topics_updated_at",
            _TABLE_NAME,
            ["updated_at"],
        )
    else:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(_TABLE_NAME)
        }
        if "ix_user_push_topics_updated_at" not in existing_indexes:
            op.create_index(
                "ix_user_push_topics_updated_at",
                _TABLE_NAME,
                ["updated_at"],
            )

    # if inspector.has_table("push_subscriptions"):
    #     _populate_existing_data()


def downgrade() -> None:
    """Drop the user push topic preferences table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE_NAME):
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(_TABLE_NAME)
        }
        if "ix_user_push_topics_updated_at" in existing_indexes:
            op.drop_index("ix_user_push_topics_updated_at", table_name=_TABLE_NAME)
        op.drop_table(_TABLE_NAME)
