"""Add append-only, PII-free trusted field CWV evidence storage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "202608250003"
down_revision = "202608250002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cwv_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(3), nullable=False),
        sa.Column("unit", sa.String(5), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("metric_id", sa.String(32), nullable=False),
        sa.Column("collector_id", sa.String(32), nullable=False),
        sa.Column("navigation_id", sa.String(128), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("device_class", sa.String(7), nullable=False),
        sa.Column("route_group", sa.String(48), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sampling_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release_sha", sa.String(40), nullable=False),
        sa.Column("frontend_image_digest", sa.String(71), nullable=False),
        sa.Column("deployment_run_id", sa.BigInteger(), nullable=False),
        sa.Column("deployment_run_attempt", sa.Integer(), nullable=False),
        sa.Column("envelope_nonce", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "metric IN ('LCP','INP','CLS')", name="ck_cwv_observation_metric"
        ),
        sa.CheckConstraint(
            "device_class IN ('mobile','desktop')", name="ck_cwv_device_class"
        ),
        sa.CheckConstraint("value >= 0", name="ck_cwv_value_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_id"),
        sa.UniqueConstraint("navigation_id", "metric", name="uq_cwv_navigation_metric"),
        sa.UniqueConstraint("envelope_nonce", "metric", name="uq_cwv_nonce_metric"),
        sa.UniqueConstraint(
            "release_sha",
            "deployment_run_id",
            "deployment_run_attempt",
            "collector_id",
            "route_group",
            "metric",
            "sampling_bucket",
            name="uq_cwv_manual_sample_bucket",
        ),
    )
    op.create_index(
        "ix_cwv_release_deployment_observed",
        "cwv_observations",
        [
            "release_sha",
            "frontend_image_digest",
            "deployment_run_id",
            "deployment_run_attempt",
            "observed_at",
        ],
    )
    op.create_index("ix_cwv_created_at", "cwv_observations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cwv_created_at", table_name="cwv_observations")
    op.drop_index("ix_cwv_release_deployment_observed", table_name="cwv_observations")
    op.drop_table("cwv_observations")
