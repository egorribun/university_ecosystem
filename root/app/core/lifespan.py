from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine, wait_db
from app.core.observability import shutdown_observability
from app.deps.cache import shutdown_cache
from app.services import notification_queue, webpush
from app.services.cache_warmup import warm_cache
from app.services.email_change_cleanup import (
    EmailChangeCleanupConfig,
    cleanup_stale_email_change_tokens,
    start_email_change_cleanup_scheduler,
)
from app.services.mfa_challenge_cleanup import (
    MfaChallengeCleanupConfig,
    cleanup_stale_mfa_challenges,
    start_mfa_challenge_cleanup_scheduler,
)
from app.services.notification_queue import (
    DeadLetterCleanupConfig,
    start_dead_letter_cleanup_scheduler,
)
from app.services.notifications import (
    cleanup_stale_notifications,
    start_notifications_scheduler,
)
from app.services.notifications_retention import (
    NotificationsRetentionConfig,
    start_notifications_retention_scheduler,
)
from app.services.password_reset_cleanup import (
    PasswordResetCleanupConfig,
    cleanup_stale_password_reset_tokens,
    start_password_reset_cleanup_scheduler,
)
from app.services.privacy_cleanup import (
    PrivacyCleanupConfig,
    cleanup_privacy_artifacts,
    start_privacy_cleanup_scheduler,
)
from app.services.session_cleanup import (
    SessionCleanupConfig,
    cleanup_expired_sessions,
    start_session_cleanup_scheduler,
)
from app.services.story_cleanup import (
    StoryCleanupConfig,
    cleanup_expired_stories,
    start_story_cleanup_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_db(max_attempts=10, delay=0.5)
    if settings.auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    stop_scheduler = None
    stop_notifications_retention = None
    stop_dead_letter_cleanup = None
    stop_session_cleanup = None
    stop_story_cleanup = None
    stop_password_reset_cleanup = None
    stop_mfa_challenge_cleanup = None
    stop_email_change_cleanup = None
    stop_privacy_cleanup = None
    if settings.is_development and settings.notifications_scheduler_inline_enabled:
        stop_scheduler = await start_notifications_scheduler(
            poll_seconds=settings.notifications_scheduler_poll_seconds,
            window_minutes=settings.notifications_scheduler_window_minutes,
            max_backoff_seconds=settings.notifications_scheduler_max_backoff_seconds,
        )
    await cleanup_stale_notifications(
        retention_days=settings.notifications_retention_days
    )
    await notification_queue.cleanup_dead_lettered_jobs(
        retention_days=settings.notification_queue_dead_letter_retention_days
    )
    await cleanup_expired_sessions()
    await cleanup_expired_stories()
    await cleanup_stale_password_reset_tokens(
        retention_minutes=settings.password_reset_cleanup_retention_minutes
    )
    await cleanup_stale_email_change_tokens(
        retention_minutes=settings.email_change_cleanup_retention_minutes
    )
    await cleanup_stale_mfa_challenges()
    await cleanup_privacy_artifacts(
        config=PrivacyCleanupConfig(
            session_retention_days=settings.session_retention_days,
            mfa_retention_days=settings.mfa_retention_days,
            failed_login_retention_days=settings.failed_login_retention_days,
            audit_log_retention_days=settings.access_log_retention_days,
            interval_seconds=settings.privacy_cleanup_interval_seconds,
        )
    )
    if (
        settings.notifications_retention_days > 0
        and settings.notifications_retention_cleanup_interval_seconds > 0
    ):
        stop_notifications_retention = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(
                retention_days=settings.notifications_retention_days,
                interval_seconds=settings.notifications_retention_cleanup_interval_seconds,
            )
        )
    if (
        settings.notification_queue_dead_letter_retention_days > 0
        and settings.notification_queue_dead_letter_cleanup_interval_seconds > 0
    ):
        stop_dead_letter_cleanup = await start_dead_letter_cleanup_scheduler(
            config=DeadLetterCleanupConfig(
                retention_days=settings.notification_queue_dead_letter_retention_days,
                interval_seconds=settings.notification_queue_dead_letter_cleanup_interval_seconds,
            )
        )
    if settings.session_cleanup_interval_seconds > 0:
        stop_session_cleanup = await start_session_cleanup_scheduler(
            config=SessionCleanupConfig(
                interval_seconds=settings.session_cleanup_interval_seconds
            )
        )
    if settings.mfa_challenge_cleanup_interval_seconds > 0:
        stop_mfa_challenge_cleanup = await start_mfa_challenge_cleanup_scheduler(
            config=MfaChallengeCleanupConfig(
                interval_seconds=settings.mfa_challenge_cleanup_interval_seconds,
                grace_period_seconds=settings.mfa_challenge_cleanup_grace_period_seconds,
            )
        )
    if settings.password_reset_cleanup_interval_seconds > 0:
        stop_password_reset_cleanup = await start_password_reset_cleanup_scheduler(
            config=PasswordResetCleanupConfig(
                interval_seconds=settings.password_reset_cleanup_interval_seconds,
                retention_minutes=settings.password_reset_cleanup_retention_minutes,
            )
        )
    if settings.email_change_cleanup_interval_seconds > 0:
        stop_email_change_cleanup = await start_email_change_cleanup_scheduler(
            config=EmailChangeCleanupConfig(
                interval_seconds=settings.email_change_cleanup_interval_seconds,
                retention_minutes=settings.email_change_cleanup_retention_minutes,
            )
        )
    if (
        settings.stories_cleanup_enabled
        and settings.stories_retention_cleanup_interval_seconds > 0
    ):
        stop_story_cleanup = await start_story_cleanup_scheduler(
            config=StoryCleanupConfig(
                interval_seconds=settings.stories_retention_cleanup_interval_seconds
            )
        )
    if settings.privacy_cleanup_interval_seconds > 0:
        stop_privacy_cleanup = await start_privacy_cleanup_scheduler(
            config=PrivacyCleanupConfig(
                session_retention_days=settings.session_retention_days,
                mfa_retention_days=settings.mfa_retention_days,
                failed_login_retention_days=settings.failed_login_retention_days,
                audit_log_retention_days=settings.access_log_retention_days,
                interval_seconds=settings.privacy_cleanup_interval_seconds,
            )
        )
    await warm_cache()
    try:
        yield
    finally:
        if stop_scheduler is not None:
            await stop_scheduler()
        if stop_notifications_retention is not None:
            await stop_notifications_retention()
        if stop_dead_letter_cleanup is not None:
            await stop_dead_letter_cleanup()
        if stop_session_cleanup is not None:
            await stop_session_cleanup()
        if stop_story_cleanup is not None:
            await stop_story_cleanup()
        if stop_password_reset_cleanup is not None:
            await stop_password_reset_cleanup()
        if stop_email_change_cleanup is not None:
            await stop_email_change_cleanup()
        if stop_mfa_challenge_cleanup is not None:
            await stop_mfa_challenge_cleanup()
        if stop_privacy_cleanup is not None:
            await stop_privacy_cleanup()
        await notification_queue.shutdown_notification_queue()
        webpush.cleanup()
        await shutdown_cache()
        shutdown_observability()
