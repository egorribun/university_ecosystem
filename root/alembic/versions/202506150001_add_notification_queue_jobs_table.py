"""Create durable notification queue table."""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202506150001"
down_revision: Union[str, None] = "202506010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "notification_queue_jobs"
_KIND_CHECK = "ck_notification_queue_jobs_kind"
_UNIQUE_NAME = "uq_notification_queue_jobs_kind_record"
_INDEX_NAME = "ix_notification_queue_jobs_kind_record"


def _ensure_indexes() -> None:
    """Create indexes that back queue lookup operations if missing."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {index["name"] for index in inspector.get_indexes(_TABLE_NAME)}
    if _INDEX_NAME not in existing_indexes:
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            ["kind", "record_id"],
        )

    claimed_index = "ix_notification_queue_jobs_claimed_at"
    if claimed_index not in existing_indexes:
        op.create_index(
            claimed_index,
            _TABLE_NAME,
            ["claimed_at"],
        )


def _ensure_constraints() -> None:
    """Create constraints that may be missing on existing deployments."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_unique = {
        uc["name"] for uc in inspector.get_unique_constraints(_TABLE_NAME)
    }
    if _UNIQUE_NAME not in existing_unique:
        op.create_unique_constraint(
            _UNIQUE_NAME,
            _TABLE_NAME,
            ["kind", "record_id"],
        )

    existing_checks = {
        cc["name"] for cc in inspector.get_check_constraints(_TABLE_NAME)
    }
    if _KIND_CHECK not in existing_checks:
        op.create_check_constraint(
            _KIND_CHECK,
            _TABLE_NAME,
            "kind IN ('event', 'news')",
        )


def upgrade() -> None:
    """Create durable notification queue backing table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_TABLE_NAME):
        op.create_table(
            _TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("record_id", sa.Integer(), nullable=False),
            sa.Column("locale", sa.String(length=16), nullable=True),
            sa.Column(
                "enqueued_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.CheckConstraint("kind IN ('event', 'news')", name=_KIND_CHECK),
            sa.UniqueConstraint("kind", "record_id", name=_UNIQUE_NAME),
        )

    _ensure_constraints()
    _ensure_indexes()


def downgrade() -> None:
    """Drop durable notification queue backing table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(_TABLE_NAME):
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(_TABLE_NAME)
        }
        if "ix_notification_queue_jobs_claimed_at" in existing_indexes:
            op.drop_index(
                "ix_notification_queue_jobs_claimed_at", table_name=_TABLE_NAME
            )
        if _INDEX_NAME in existing_indexes:
            op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)

        existing_checks = {
            cc["name"] for cc in inspector.get_check_constraints(_TABLE_NAME)
        }
        if _KIND_CHECK in existing_checks:
            op.drop_constraint(_KIND_CHECK, _TABLE_NAME, type_="check")

        existing_unique = {
            uc["name"] for uc in inspector.get_unique_constraints(_TABLE_NAME)
        }
        if _UNIQUE_NAME in existing_unique:
            op.drop_constraint(_UNIQUE_NAME, _TABLE_NAME, type_="unique")

        op.drop_table(_TABLE_NAME)
