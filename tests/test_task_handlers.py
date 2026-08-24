"""Behavioral tests for cleanup, notification, and email task handlers.

Calls each decorated task's inner logic directly, bypassing NATS dispatch.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/tasks/cleanups.py
# ---------------------------------------------------------------------------


class TestCleanupNotificationsTask:
    @pytest.mark.asyncio
    async def test_runs_when_retention_days_positive(self):
        """cleanup_notifications_task invokes service when retention > 0."""
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.notifications_retention_days = 30

            # Call the inner function directly (unwrap the @broker.task decorator)
            inner = (
                cleanups.cleanup_notifications_task.__wrapped__
                if hasattr(cleanups.cleanup_notifications_task, "__wrapped__")
                else cleanups.cleanup_notifications_task.original_func
                if hasattr(cleanups.cleanup_notifications_task, "original_func")
                else cleanups.cleanup_notifications_task
            )

            # If it's still wrapped we call the coroutine function directly
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once_with(retention_days=30)

    @pytest.mark.asyncio
    async def test_skips_when_retention_days_zero(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.notifications_retention_days = 0
            inner = getattr(
                cleanups.cleanup_notifications_task,
                "__wrapped__",
                cleanups.cleanup_notifications_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_not_called()


class TestCleanupSessionsTask:
    @pytest.mark.asyncio
    async def test_calls_cleanup_expired_sessions(self):
        from app.tasks import cleanups

        with patch(
            "app.tasks.cleanups.cleanup_expired_sessions", new_callable=AsyncMock
        ) as mock_cleanup:
            inner = getattr(
                cleanups.cleanup_sessions_task,
                "__wrapped__",
                cleanups.cleanup_sessions_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once()


class TestCleanupStoriesTask:
    @pytest.mark.asyncio
    async def test_runs_when_enabled(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.stories_cleanup_enabled = True
            inner = getattr(
                cleanups.cleanup_stories_task,
                "__wrapped__",
                cleanups.cleanup_stories_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.stories_cleanup_enabled = False
            inner = getattr(
                cleanups.cleanup_stories_task,
                "__wrapped__",
                cleanups.cleanup_stories_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_not_called()


class TestCleanupPasswordResetTokensTask:
    @pytest.mark.asyncio
    async def test_calls_cleanup_stale_password_reset_tokens(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_password_reset_tokens",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            mock_settings.password_reset_cleanup_retention_minutes = 60
            inner = getattr(
                cleanups.cleanup_password_reset_tokens_task,
                "__wrapped__",
                cleanups.cleanup_password_reset_tokens_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once_with(retention_minutes=60)


class TestCleanupEmailChangeTokensTask:
    @pytest.mark.asyncio
    async def test_calls_cleanup_stale_email_change_tokens(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_email_change_tokens",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            mock_settings.email_change_cleanup_retention_minutes = 120
            inner = getattr(
                cleanups.cleanup_email_change_tokens_task,
                "__wrapped__",
                cleanups.cleanup_email_change_tokens_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once_with(retention_minutes=120)


class TestCleanupMfaChallengesTask:
    @pytest.mark.asyncio
    async def test_calls_cleanup_stale_mfa_challenges(self):
        from app.tasks import cleanups

        with patch(
            "app.tasks.cleanups.cleanup_stale_mfa_challenges", new_callable=AsyncMock
        ) as mock_cleanup:
            inner = getattr(
                cleanups.cleanup_mfa_challenges_task,
                "__wrapped__",
                cleanups.cleanup_mfa_challenges_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once()


class TestCleanupPrivacyArtifactsTask:
    @pytest.mark.asyncio
    async def test_calls_cleanup_privacy_artifacts(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_privacy_artifacts", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.session_retention_days = 30
            mock_settings.mfa_retention_days = 90
            mock_settings.failed_login_retention_days = 14
            mock_settings.access_log_retention_days = 365
            mock_settings.privacy_cleanup_interval_seconds = 3600
            inner = getattr(
                cleanups.cleanup_privacy_artifacts_task,
                "__wrapped__",
                cleanups.cleanup_privacy_artifacts_task,
            )
            if callable(inner):
                await inner()
            mock_cleanup.assert_called_once()


class TestManagePartitionsTask:
    @pytest.mark.asyncio
    async def test_runs_when_enabled(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
            ) as mock_ensure,
        ):
            mock_settings.partition_management_enabled = True
            inner = getattr(
                cleanups.manage_partitions_task,
                "__wrapped__",
                cleanups.manage_partitions_task,
            )
            if callable(inner):
                await inner()
            mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
            ) as mock_ensure,
        ):
            mock_settings.partition_management_enabled = False
            inner = getattr(
                cleanups.manage_partitions_task,
                "__wrapped__",
                cleanups.manage_partitions_task,
            )
            if callable(inner):
                await inner()
            mock_ensure.assert_not_called()


class TestCleanupDeadLetterJobsTask:
    @pytest.mark.asyncio
    async def test_runs_when_retention_positive(self):
        from app.tasks import cleanups

        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch("app.tasks.cleanups.notification_queue") as mock_nq,
        ):
            mock_settings.notification_queue_dead_letter_retention_days = 7
            mock_nq.cleanup_dead_lettered_jobs = AsyncMock()
            inner = getattr(
                cleanups.cleanup_dead_letter_jobs_task,
                "__wrapped__",
                cleanups.cleanup_dead_letter_jobs_task,
            )
            if callable(inner):
                await inner()
            mock_nq.cleanup_dead_lettered_jobs.assert_called_once_with(retention_days=7)


class TestSetupPeriodicCleanups:
    @pytest.mark.asyncio
    async def test_logs_initialised(self):
        """setup_periodic_cleanups should log a message and return."""
        from app.tasks import cleanups

        with patch("app.tasks.cleanups.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            await cleanups.setup_periodic_cleanups()
            mock_logger.info.assert_called_once()


# ---------------------------------------------------------------------------
# app/tasks/email.py
# ---------------------------------------------------------------------------


class TestSendAuthEmail:
    def test_calls_send_reset_email(self):
        from app.tasks import email as email_tasks

        with patch("app.tasks.email.send_reset_email") as mock_send:
            inner = getattr(
                email_tasks.send_auth_email, "__wrapped__", email_tasks.send_auth_email
            )
            if callable(inner):
                inner(
                    "user@example.com",
                    "https://example.com/reset",
                    "John Doe",
                    locale="en",
                )
            mock_send.assert_called_once_with(
                "user@example.com", "https://example.com/reset", "John Doe", locale="en"
            )


class TestSendLockoutAlert:
    def test_calls_send_lockout_email(self):
        from app.tasks import email as email_tasks

        with patch("app.utils.email.send_lockout_email") as mock_send:
            inner = getattr(
                email_tasks.send_lockout_alert,
                "__wrapped__",
                email_tasks.send_lockout_alert,
            )
            if callable(inner):
                inner("user@example.com", "Jane Doe", locale="ru")
            mock_send.assert_called_once_with(
                "user@example.com", "Jane Doe", locale="ru"
            )


# ---------------------------------------------------------------------------
# app/tasks/notifications.py
# ---------------------------------------------------------------------------


class TestEnqueueNewsNotificationTask:
    @pytest.mark.asyncio
    async def test_notifies_when_news_found(self):
        from app.tasks import notifications as notif_tasks

        news_id = uuid.uuid4()
        mock_news = MagicMock()

        mock_db = AsyncMock()
        mock_db.get.return_value = mock_news
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.notifications.async_session") as mock_cm,
            patch(
                "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
            ) as mock_notify,
        ):
            mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            inner = getattr(
                notif_tasks.enqueue_news_notification_task,
                "__wrapped__",
                notif_tasks.enqueue_news_notification_task,
            )
            if callable(inner):
                await inner(news_id=news_id, locale="en")

            mock_notify.assert_called_once_with(mock_db, mock_news, locale="en")
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_news_not_found(self):
        from app.tasks import notifications as notif_tasks

        news_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.get.return_value = None

        with (
            patch("app.tasks.notifications.async_session") as mock_cm,
            patch(
                "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
            ) as mock_notify,
        ):
            mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            inner = getattr(
                notif_tasks.enqueue_news_notification_task,
                "__wrapped__",
                notif_tasks.enqueue_news_notification_task,
            )
            if callable(inner):
                await inner(news_id=news_id)

            mock_notify.assert_not_called()


class TestEnqueueEventNotificationTask:
    @pytest.mark.asyncio
    async def test_notifies_when_event_found(self):
        from app.tasks import notifications as notif_tasks

        event_id = uuid.uuid4()
        mock_event = MagicMock()

        mock_db = AsyncMock()
        mock_db.get.return_value = mock_event
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.notifications.async_session") as mock_cm,
            patch(
                "app.tasks.notifications._notify_about_event", new_callable=AsyncMock
            ) as mock_notify,
        ):
            mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            inner = getattr(
                notif_tasks.enqueue_event_notification_task,
                "__wrapped__",
                notif_tasks.enqueue_event_notification_task,
            )
            if callable(inner):
                await inner(event_id=event_id, locale="ru")

            mock_notify.assert_called_once_with(mock_db, mock_event, locale="ru")


class TestEnqueueCommentNotificationTask:
    @pytest.mark.asyncio
    async def test_notifies_when_all_objects_found(self):
        from app.tasks import notifications as notif_tasks

        news_id = uuid.uuid4()
        comment_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_news = MagicMock()
        mock_comment = MagicMock()
        mock_author = MagicMock()
        mock_db.get.side_effect = [mock_news, mock_comment, mock_author]
        mock_db.commit = AsyncMock()

        with (
            patch("app.tasks.notifications.async_session") as mock_cm,
            patch(
                "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
            ) as mock_notify,
        ):
            mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            inner = getattr(
                notif_tasks.enqueue_comment_notification_task,
                "__wrapped__",
                notif_tasks.enqueue_comment_notification_task,
            )
            if callable(inner):
                await inner(
                    news_id=news_id, comment_id=comment_id, user_id=user_id, locale="en"
                )

            mock_notify.assert_called_once_with(
                mock_db, mock_news, mock_comment, mock_author, locale="en"
            )

    @pytest.mark.asyncio
    async def test_skips_when_objects_missing(self):
        from app.tasks import notifications as notif_tasks

        news_id = uuid.uuid4()
        comment_id = uuid.uuid4()
        user_id = uuid.uuid4()

        mock_db = AsyncMock()
        # comment is missing
        mock_db.get.side_effect = [MagicMock(), None, MagicMock()]

        with (
            patch("app.tasks.notifications.async_session") as mock_cm,
            patch(
                "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
            ) as mock_notify,
        ):
            mock_cm.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            inner = getattr(
                notif_tasks.enqueue_comment_notification_task,
                "__wrapped__",
                notif_tasks.enqueue_comment_notification_task,
            )
            if callable(inner):
                await inner(news_id=news_id, comment_id=comment_id, user_id=user_id)

            mock_notify.assert_not_called()
