import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.tasks.cleanups as cleanup_tasks
import app.tasks.email as email_tasks
import app.tasks.notifications as notification_tasks
from app.models import Event, News, NewsComment, User


def test_email_tasks():
    with (
        patch("app.tasks.email.send_reset_email") as mock_reset,
        patch("app.utils.email.send_lockout_email") as mock_lockout,
    ):
        email_tasks.send_auth_email.__wrapped__(
            "test@example.com", "http://reset", "John Doe", "en"
        )
        mock_reset.assert_called_once_with(
            "test@example.com", "http://reset", "John Doe", locale="en"
        )

        email_tasks.send_lockout_alert.__wrapped__("test@example.com", "John Doe", "en")
        mock_lockout.assert_called_once_with(
            "test@example.com", "John Doe", locale="en"
        )


@pytest.mark.anyio
async def test_notification_tasks_found():
    news_id = uuid.uuid4()
    event_id = uuid.uuid4()
    comment_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_news = MagicMock(spec=News)
    mock_event = MagicMock(spec=Event)
    mock_comment = MagicMock(spec=NewsComment)
    mock_user = MagicMock(spec=User)

    mock_db = AsyncMock()

    async def mock_get(model_cls, pk):
        if model_cls == News and pk == news_id:
            return mock_news
        if model_cls == Event and pk == event_id:
            return mock_event
        if model_cls == NewsComment and pk == comment_id:
            return mock_comment
        if model_cls == User and pk == user_id:
            return mock_user
        return None

    mock_db.get = mock_get

    with (
        patch("app.tasks.notifications.async_session") as mock_session,
        patch(
            "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
        ) as mock_notify_news,
        patch(
            "app.tasks.notifications._notify_about_event", new_callable=AsyncMock
        ) as mock_notify_event,
        patch(
            "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
        ) as mock_notify_comment,
    ):
        mock_session.return_value.__aenter__.return_value = mock_db

        # 1. News
        await notification_tasks.enqueue_news_notification_task.__wrapped__(
            news_id, locale="en"
        )
        mock_notify_news.assert_called_once_with(mock_db, mock_news, locale="en")

        # 2. Event
        await notification_tasks.enqueue_event_notification_task.__wrapped__(
            event_id, locale="en"
        )
        mock_notify_event.assert_called_once_with(mock_db, mock_event, locale="en")

        # 3. Comment
        await notification_tasks.enqueue_comment_notification_task.__wrapped__(
            news_id, comment_id, user_id, locale="en"
        )
        mock_notify_comment.assert_called_once_with(
            mock_db, mock_news, mock_comment, mock_user, locale="en"
        )


@pytest.mark.anyio
async def test_notification_tasks_not_found():
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with (
        patch("app.tasks.notifications.async_session") as mock_session,
        patch(
            "app.tasks.notifications._notify_about_news", new_callable=AsyncMock
        ) as mock_notify_news,
        patch(
            "app.tasks.notifications._notify_about_event", new_callable=AsyncMock
        ) as mock_notify_event,
        patch(
            "app.tasks.notifications._notify_about_comment", new_callable=AsyncMock
        ) as mock_notify_comment,
    ):
        mock_session.return_value.__aenter__.return_value = mock_db

        await notification_tasks.enqueue_news_notification_task.__wrapped__(
            uuid.uuid4()
        )
        mock_notify_news.assert_not_called()

        await notification_tasks.enqueue_event_notification_task.__wrapped__(
            uuid.uuid4()
        )
        mock_notify_event.assert_not_called()

        await notification_tasks.enqueue_comment_notification_task.__wrapped__(
            uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        )
        mock_notify_comment.assert_not_called()


@pytest.mark.anyio
async def test_cleanup_tasks_enabled():
    with (
        patch("app.tasks.cleanups.settings") as mock_settings,
        patch(
            "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
        ) as mock_cleanup_notifs,
        patch(
            "app.tasks.cleanups.notification_queue.cleanup_dead_lettered_jobs",
            new_callable=AsyncMock,
        ) as mock_cleanup_dlq,
        patch(
            "app.tasks.cleanups.cleanup_expired_sessions", new_callable=AsyncMock
        ) as mock_cleanup_sessions,
        patch(
            "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
        ) as mock_cleanup_stories,
        patch(
            "app.tasks.cleanups.cleanup_stale_password_reset_tokens",
            new_callable=AsyncMock,
        ) as mock_cleanup_pwd,
        patch(
            "app.tasks.cleanups.cleanup_stale_email_change_tokens",
            new_callable=AsyncMock,
        ) as mock_cleanup_email,
        patch(
            "app.tasks.cleanups.cleanup_stale_mfa_challenges", new_callable=AsyncMock
        ) as mock_cleanup_mfa,
        patch(
            "app.tasks.cleanups.cleanup_privacy_artifacts", new_callable=AsyncMock
        ) as mock_cleanup_privacy,
        patch(
            "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
        ) as mock_partitions,
    ):
        # Configure settings mock
        mock_settings.notifications_retention_days = 7
        mock_settings.notification_queue_dead_letter_retention_days = 14
        mock_settings.stories_cleanup_enabled = True
        mock_settings.password_reset_cleanup_retention_minutes = 60
        mock_settings.email_change_cleanup_retention_minutes = 30
        mock_settings.session_retention_days = 1
        mock_settings.mfa_retention_days = 2
        mock_settings.failed_login_retention_days = 3
        mock_settings.access_log_retention_days = 4
        mock_settings.privacy_cleanup_interval_seconds = 86400
        mock_settings.partition_management_enabled = True

        # Run tasks
        await cleanup_tasks.cleanup_notifications_task.__wrapped__()
        mock_cleanup_notifs.assert_called_once_with(retention_days=7)

        await cleanup_tasks.cleanup_dead_letter_jobs_task.__wrapped__()
        mock_cleanup_dlq.assert_called_once_with(retention_days=14)

        await cleanup_tasks.cleanup_sessions_task.__wrapped__()
        mock_cleanup_sessions.assert_called_once()

        await cleanup_tasks.cleanup_stories_task.__wrapped__()
        mock_cleanup_stories.assert_called_once()

        await cleanup_tasks.cleanup_password_reset_tokens_task.__wrapped__()
        mock_cleanup_pwd.assert_called_once_with(retention_minutes=60)

        await cleanup_tasks.cleanup_email_change_tokens_task.__wrapped__()
        mock_cleanup_email.assert_called_once_with(retention_minutes=30)

        await cleanup_tasks.cleanup_mfa_challenges_task.__wrapped__()
        mock_cleanup_mfa.assert_called_once()

        await cleanup_tasks.cleanup_privacy_artifacts_task.__wrapped__()
        mock_cleanup_privacy.assert_called_once()

        await cleanup_tasks.manage_partitions_task.__wrapped__()
        mock_partitions.assert_called_once()

        await cleanup_tasks.setup_periodic_cleanups()


@pytest.mark.anyio
async def test_cleanup_tasks_disabled():
    with (
        patch("app.tasks.cleanups.settings") as mock_settings,
        patch(
            "app.tasks.cleanups.cleanup_stale_notifications", new_callable=AsyncMock
        ) as mock_cleanup_notifs,
        patch(
            "app.tasks.cleanups.notification_queue.cleanup_dead_lettered_jobs",
            new_callable=AsyncMock,
        ) as mock_cleanup_dlq,
        patch(
            "app.tasks.cleanups.cleanup_expired_stories", new_callable=AsyncMock
        ) as mock_cleanup_stories,
        patch(
            "app.tasks.cleanups.ensure_partitions_exist", new_callable=AsyncMock
        ) as mock_partitions,
    ):
        # Configure settings mock
        mock_settings.notifications_retention_days = 0
        mock_settings.notification_queue_dead_letter_retention_days = 0
        mock_settings.stories_cleanup_enabled = False
        mock_settings.partition_management_enabled = False

        # Run tasks and assert they don't invoke helpers
        await cleanup_tasks.cleanup_notifications_task.__wrapped__()
        mock_cleanup_notifs.assert_not_called()

        await cleanup_tasks.cleanup_dead_letter_jobs_task.__wrapped__()
        mock_cleanup_dlq.assert_not_called()

        await cleanup_tasks.cleanup_stories_task.__wrapped__()
        mock_cleanup_stories.assert_not_called()

        await cleanup_tasks.manage_partitions_task.__wrapped__()
        mock_partitions.assert_not_called()


def test_images_import_fallback():
    import importlib
    import sys

    import app.utils.images as img

    with patch.dict(sys.modules, {"app.utils.images_vips": None}):
        importlib.reload(img)
        assert img.VIPS_AVAILABLE is False
        assert img.optimize_image_vips is None

    importlib.reload(img)
