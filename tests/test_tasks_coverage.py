"""Coverage tests for app/tasks/ — NATS broker task functions and setup.

All external I/O (database sessions, service calls, broker NATS connections)
is patched so the tests run fully in-process with no infrastructure.

Coverage targets
----------------
app/tasks/cleanups.py  — 10 broker tasks + setup_periodic_cleanups
app/tasks/notifications.py — 3 broker tasks (news/event/comment notification)
app/tasks/email.py     — 1 broker task (if present)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db_context(**entities: object) -> AsyncMock:
    """Return an AsyncMock session whose .get() returns entities by model class."""
    db = AsyncMock()

    async def _get(model, pk):  # noqa: ANN001
        return entities.get(model.__name__)

    db.get.side_effect = _get
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


# ---------------------------------------------------------------------------
# app/tasks/cleanups.py
# ---------------------------------------------------------------------------


class TestCleanupTasks:
    """Drive each task's wrapped coroutine directly to reach every branch."""

    @pytest.mark.asyncio
    async def test_cleanup_notifications_enabled(self) -> None:
        """Task body executes cleanup_stale_notifications when retention > 0."""
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.notifications_retention_days = 30
            # Import the coroutine function from the task object.
            from app.tasks.cleanups import cleanup_notifications_task

            await cleanup_notifications_task()
            mock_cleanup.assert_awaited_once_with(retention_days=30)

    @pytest.mark.asyncio
    async def test_cleanup_notifications_disabled(self) -> None:
        """Task body is a no-op when retention_days == 0."""
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.notifications_retention_days = 0
            from app.tasks.cleanups import cleanup_notifications_task

            await cleanup_notifications_task()
            mock_cleanup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_dead_letter_jobs_enabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.notification_queue", new_callable=MagicMock
            ) as mock_queue,
        ):
            mock_settings.notification_queue_dead_letter_retention_days = 7
            mock_queue.cleanup_dead_lettered_jobs = AsyncMock()
            from app.tasks.cleanups import cleanup_dead_letter_jobs_task

            await cleanup_dead_letter_jobs_task()
            mock_queue.cleanup_dead_lettered_jobs.assert_awaited_once_with(retention_days=7)

    @pytest.mark.asyncio
    async def test_cleanup_dead_letter_jobs_disabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.notification_queue", new_callable=MagicMock
            ) as mock_queue,
        ):
            mock_settings.notification_queue_dead_letter_retention_days = 0
            mock_queue.cleanup_dead_lettered_jobs = AsyncMock()
            from app.tasks.cleanups import cleanup_dead_letter_jobs_task

            await cleanup_dead_letter_jobs_task()
            mock_queue.cleanup_dead_lettered_jobs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_sessions_task(self) -> None:
        with patch(
            "app.tasks.cleanups.cleanup_expired_sessions", new_callable=AsyncMock
        ) as mock_cleanup:
            from app.tasks.cleanups import cleanup_sessions_task

            await cleanup_sessions_task()
            mock_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_stories_task_enabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.stories_cleanup_enabled = True
            from app.tasks.cleanups import cleanup_stories_task

            await cleanup_stories_task()
            mock_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_stories_task_disabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.stories_cleanup_enabled = False
            from app.tasks.cleanups import cleanup_stories_task

            await cleanup_stories_task()
            mock_cleanup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_password_reset_tokens_task(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_password_reset_tokens",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            mock_settings.password_reset_cleanup_retention_minutes = 60
            from app.tasks.cleanups import cleanup_password_reset_tokens_task

            await cleanup_password_reset_tokens_task()
            mock_cleanup.assert_awaited_once_with(retention_minutes=60)

    @pytest.mark.asyncio
    async def test_cleanup_email_change_tokens_task(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_stale_email_change_tokens",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            mock_settings.email_change_cleanup_retention_minutes = 60
            from app.tasks.cleanups import cleanup_email_change_tokens_task

            await cleanup_email_change_tokens_task()
            mock_cleanup.assert_awaited_once_with(retention_minutes=60)

    @pytest.mark.asyncio
    async def test_cleanup_mfa_challenges_task(self) -> None:
        with patch(
            "app.tasks.cleanups.cleanup_stale_mfa_challenges", new_callable=AsyncMock
        ) as mock_cleanup:
            from app.tasks.cleanups import cleanup_mfa_challenges_task

            await cleanup_mfa_challenges_task()
            mock_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_privacy_artifacts_task(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.cleanup_privacy_artifacts", new_callable=AsyncMock
            ) as mock_cleanup,
        ):
            mock_settings.session_retention_days = 90
            mock_settings.mfa_retention_days = 30
            mock_settings.failed_login_retention_days = 14
            mock_settings.access_log_retention_days = 180
            mock_settings.privacy_cleanup_interval_seconds = 3600
            from app.tasks.cleanups import cleanup_privacy_artifacts_task

            await cleanup_privacy_artifacts_task()
            mock_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manage_partitions_task_enabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
            ) as mock_ensure,
        ):
            mock_settings.partition_management_enabled = True
            from app.tasks.cleanups import manage_partitions_task

            await manage_partitions_task()
            mock_ensure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_manage_partitions_task_disabled(self) -> None:
        with (
            patch("app.tasks.cleanups.settings") as mock_settings,
            patch(
                "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
            ) as mock_ensure,
        ):
            mock_settings.partition_management_enabled = False
            from app.tasks.cleanups import manage_partitions_task

            await manage_partitions_task()
            mock_ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_setup_periodic_cleanups_logs(self) -> None:
        """setup_periodic_cleanups is a no-op entrypoint; assert it doesn't raise."""
        from app.tasks.cleanups import setup_periodic_cleanups

        # Should execute without raising any exception.
        await setup_periodic_cleanups()


# ---------------------------------------------------------------------------
# app/tasks/notifications.py
# ---------------------------------------------------------------------------


class TestNotificationTasks:
    """Broker task coroutines for outbound news/event/comment notifications."""

    @pytest.mark.asyncio
    async def test_enqueue_news_notification_task_entity_found(self) -> None:
        """Task calls _notify_about_news and commits when News row exists."""
        news_id = uuid.uuid4()
        fake_news = MagicMock()

        db = _make_db_context(News=fake_news)

        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_news_notification_task

            await enqueue_news_notification_task(news_id, locale="ru")
            mock_notify.assert_awaited_once()
            db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_news_notification_task_entity_missing(self) -> None:
        """Task is a no-op when the News row is not found."""
        db = _make_db_context()  # .get() returns None for everything

        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_news_notification_task

            await enqueue_news_notification_task(uuid.uuid4())
            mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_event_notification_task_entity_found(self) -> None:
        """Task calls _notify_about_event when the Event row exists."""
        event_id = uuid.uuid4()
        fake_event = MagicMock()

        db = _make_db_context(Event=fake_event)

        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_event", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_event_notification_task

            await enqueue_event_notification_task(event_id, locale="en")
            mock_notify.assert_awaited_once()
            db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_event_notification_task_entity_missing(self) -> None:
        db = _make_db_context()
        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_event", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_event_notification_task

            await enqueue_event_notification_task(uuid.uuid4())
            mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_comment_notification_task_all_found(self) -> None:
        """Task calls _notify_about_comment when all three entities exist."""
        fake_news = MagicMock()
        fake_comment = MagicMock()
        fake_author = MagicMock()

        # db.get returns distinct objects based on call order.
        db = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        db.commit = AsyncMock()
        # The task calls db.get three times in order: News → NewsComment → User.
        db.get.side_effect = [fake_news, fake_comment, fake_author]

        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_comment_notification_task

            await enqueue_comment_notification_task(
                news_id=uuid.uuid4(),
                comment_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                locale="ru",
            )
            mock_notify.assert_awaited_once()
            db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_comment_notification_task_partial_missing(self) -> None:
        """Task skips notification when any of the three entities is missing."""
        db = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        db.commit = AsyncMock()
        # News is found; Comment and Author are missing.
        db.get.side_effect = [MagicMock(), None, MagicMock()]

        with (
            patch("app.tasks.notifications.async_session", return_value=db),
            patch(
                "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
            ) as mock_notify,
        ):
            from app.tasks.notifications import enqueue_comment_notification_task

            await enqueue_comment_notification_task(
                news_id=uuid.uuid4(),
                comment_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )
            mock_notify.assert_not_awaited()
