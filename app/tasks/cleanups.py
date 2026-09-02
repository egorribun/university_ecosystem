from app.core.config import settings
from app.core.logging import get_logger
from app.core.nats_broker import broker
from app.services import notification_queue
from app.services.cwv_retention import cleanup_stale_cwv_observations
from app.services.email_change_cleanup import cleanup_stale_email_change_tokens
from app.services.mfa_challenge_cleanup import cleanup_stale_mfa_challenges
from app.services.notifications import cleanup_stale_notifications
from app.services.partition_manager import ensure_partitions_exist
from app.services.password_reset_cleanup import cleanup_stale_password_reset_tokens
from app.services.privacy_cleanup import PrivacyCleanupConfig, cleanup_privacy_artifacts
from app.services.session_cleanup import cleanup_expired_sessions
from app.services.story_cleanup import cleanup_expired_stories


@broker.task()
async def cleanup_notifications_task() -> None:
    """Task for cleaning up stale notifications."""
    if settings.notifications_retention_days > 0:
        await cleanup_stale_notifications(
            retention_days=settings.notifications_retention_days
        )


@broker.task()
async def cleanup_dead_letter_jobs_task() -> None:
    """Task for cleaning up dead lettered jobs."""
    if settings.notification_queue_dead_letter_retention_days > 0:
        await notification_queue.cleanup_dead_lettered_jobs(
            retention_days=settings.notification_queue_dead_letter_retention_days
        )


@broker.task()
async def cleanup_sessions_task() -> None:
    """Task for cleaning up expired sessions."""
    await cleanup_expired_sessions()


@broker.task()
async def cleanup_stories_task() -> None:
    """Task for cleaning up expired stories."""
    if settings.stories_cleanup_enabled:
        await cleanup_expired_stories()


@broker.task()
async def cleanup_password_reset_tokens_task() -> None:
    """Task for cleaning up stale password reset tokens."""
    await cleanup_stale_password_reset_tokens(
        retention_minutes=settings.password_reset_cleanup_retention_minutes
    )


@broker.task()
async def cleanup_email_change_tokens_task() -> None:
    """Task for cleaning up stale email change tokens."""
    await cleanup_stale_email_change_tokens(
        retention_minutes=settings.email_change_cleanup_retention_minutes
    )


@broker.task()
async def cleanup_mfa_challenges_task() -> None:
    """Task for cleaning up stale MFA challenges."""
    await cleanup_stale_mfa_challenges()


@broker.task()
async def cleanup_privacy_artifacts_task() -> None:
    """Task for cleaning up privacy artifacts."""
    config = PrivacyCleanupConfig(
        session_retention_days=settings.session_retention_days,
        mfa_retention_days=settings.mfa_retention_days,
        failed_login_retention_days=settings.failed_login_retention_days,
        audit_log_retention_days=settings.access_log_retention_days,
        interval_seconds=settings.privacy_cleanup_interval_seconds,
    )
    await cleanup_privacy_artifacts(config=config)
    if settings.cwv_rum_enabled:
        await cleanup_stale_cwv_observations(retention_days=settings.cwv_retention_days)


@broker.task()
async def manage_partitions_task() -> None:
    """Task for managing database partitions."""
    if settings.partition_management_enabled:
        await ensure_partitions_exist()


async def setup_periodic_cleanups() -> None:
    """Schedule periodic cleanup tasks.

    (MOD-3: Audit 2026-02-24)
    Periodic tasks are now managed by the application lifespan scheduler.
    """
    _logger = get_logger(__name__)
    _logger.info("NATS periodic cleanups initialised")
