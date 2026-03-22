"""Add pg_cron periodic token cleanup jobs.

MOD-W5-06: Offloads application-level cron cleanup to pg_cron so token tables
stay lean even during application downtime. Three jobs:

  1. expire-password-reset-tokens   — hourly
  2. expire-mfa-challenges          — every 15 minutes  (state → 'expired')
  3. clean-trusted-devices          — monthly at 03:00

Requires the pg_cron extension to be available in the PostgreSQL cluster.
For self-hosted deployments: `CREATE EXTENSION pg_cron;` must be run as a
superuser before applying this migration (the extension is pre-installed on
Supabase, Aurora, and Cloud SQL with pg_cron support enabled).

Revision ID: 202603130002
Revises: 202603130001
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

_CRON_JOB_NAMES: tuple[str, ...] = (
    "expire-password-reset-tokens",
    "expire-mfa-challenges",
    "clean-trusted-devices",
)

revision: str = "202603130002"
down_revision: str | None = "202603130001"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # Check if pg_cron is available in the cluster before attempting to create it.
    res = (
        op.get_bind()
        .execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron'"))
        .fetchone()
    )
    if not res:
        # P0-W5: Skip pg_cron setup in environments where the extension is not installed
        # (e.g. standard local Docker containers, custom builds without pg_cron).
        return

    # Enable pg_cron if not already present.
    op.execute(text("CREATE EXTENSION IF NOT EXISTS pg_cron"))

    # 1. Expire unused password-reset tokens hourly to keep the table small.
    op.execute(
        text(
            """
        SELECT cron.schedule(
            'expire-password-reset-tokens',
            '0 * * * *',
            $$DELETE FROM password_reset_tokens
              WHERE expires_at < NOW() AND used IS FALSE$$
        )
        """
        )
    )

    # 2. Mark pending MFA challenges as 'expired' every 15 minutes.
    #    Uses the ChallengeState enum added in migration 202603130001.
    op.execute(
        text(
            """
        SELECT cron.schedule(
            'expire-mfa-challenges',
            '*/15 * * * *',
            $$UPDATE mfa_challenges
              SET state = 'expired'
              WHERE expires_at < NOW()
                AND state = 'pending'$$
        )
        """
        )
    )

    # 3. Prune expired trusted-device tokens once a month at 03:00 on the 1st.
    op.execute(
        text(
            """
        SELECT cron.schedule(
            'clean-trusted-devices',
            '0 3 1 * *',
            $$DELETE FROM trusted_devices WHERE expires_at < NOW()$$
        )
        """
        )
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    # pg_cron may not be installed in all environments (e.g., CI without the extension).
    # Guard against missing cron schema before attempting to unschedule.
    has_cron = (
        op.get_bind()
        .execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'cron'")
        )
        .scalar()
    )
    if not has_cron:
        return

    # Remove the three scheduled jobs by name; ignore if they don't exist.
    for job_name in _CRON_JOB_NAMES:
        op.execute(
            text(
                "SELECT cron.unschedule(:job_name) "
                "WHERE EXISTS (SELECT 1 FROM cron.job WHERE jobname = :job_name)"
            ).bindparams(job_name=job_name)
        )
