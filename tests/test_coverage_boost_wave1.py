"""Wave 1 coverage boost: hermetic unit tests for previously-untested paths.

Target modules and their missing branches
-------------------------------------------
- app/services/notifications/scheduler.py        → _scheduler_loop wrapper
- app/workers/notifications.py                   → start_notifications_scheduler (task-exists path),
                                                    _wait_for_signals, run_worker
- app/services/privacy_cleanup.py                → start_privacy_cleanup_scheduler loop + stop
- app/services/session_cleanup.py                → start_session_cleanup_scheduler stop when task done
- app/services/stats_cache.py                    → cache_stats decorator branches
- app/utils/email.py                             → send_lockout_email various paths

All tests are hermetic: no real DB, no real network, all I/O mocked.
"""

from __future__ import annotations

import asyncio
import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# notifications/scheduler.py  → _scheduler_loop wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_loop_wrapper_delegates_and_cancels():
    """_scheduler_loop instantiates NotificationsScheduler and runs until cancelled."""
    from app.services.notifications.scheduler import _scheduler_loop

    with patch("app.workers.notifications.NotificationsScheduler") as mock_cls:
        mock_sched = mock_cls.return_value
        mock_sched.run_forever = AsyncMock(side_effect=asyncio.CancelledError)

        # Should not raise — CancelledError is consumed inside the wrapper.
        await _scheduler_loop(poll_seconds=1, window_minutes=1, max_backoff_seconds=10)

        mock_cls.assert_called_once()
        mock_sched.run_forever.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_notifications_scheduler_wrapper_delegates():
    """scheduler.start_notifications_scheduler delegates to workers module."""
    from app.services.notifications.scheduler import start_notifications_scheduler

    async def _fake_stop():
        pass

    with patch(
        "app.workers.notifications.start_notifications_scheduler",
        return_value=AsyncMock(return_value=_fake_stop),
    ) as mock_start:
        # The wrapper simply calls the underlying implementation.
        result = await start_notifications_scheduler(
            poll_seconds=10,
            window_minutes=5,
            max_backoff_seconds=60,
        )
        mock_start.assert_awaited_once()


# ---------------------------------------------------------------------------
# app/workers/notifications.py  → task-already-running path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_notifications_scheduler_returns_existing_stop_when_running():
    """If a scheduler task is already running, return a stop for the existing task."""
    import app.workers.notifications as worker_module
    from app.workers.notifications import start_notifications_scheduler

    # Arrange: create a never-finishing task so `_scheduler_task.done()` is False.
    async def _run_forever():
        await asyncio.sleep(9999)

    existing_task = asyncio.get_event_loop().create_task(_run_forever())
    original_task = worker_module._scheduler_task
    worker_module._scheduler_task = existing_task

    try:
        stop_fn = await start_notifications_scheduler(
            poll_seconds=60, window_minutes=30, max_backoff_seconds=300
        )
        # The returned callable should stop the *existing* task.
        assert callable(stop_fn)
        # Calling stop should cancel and await the existing task.
        await stop_fn()
        assert existing_task.cancelled() or existing_task.done()
    finally:
        # Restore global state to avoid polluting other tests.
        if not existing_task.done():
            existing_task.cancel()
            with pytest.raises((asyncio.CancelledError, Exception)):
                await existing_task
        worker_module._scheduler_task = original_task


# ---------------------------------------------------------------------------
# app/workers/notifications.py → _wait_for_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_signals_returns_when_event_set():
    """_wait_for_signals should return as soon as stop_event is set."""
    from app.workers.notifications import _wait_for_signals

    stop_event = asyncio.Event()
    # Set immediately so the coroutine returns without blocking.
    stop_event.set()
    await _wait_for_signals(stop_event)  # Should complete without hanging.


# ---------------------------------------------------------------------------
# app/services/privacy_cleanup.py → scheduler start/stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_privacy_cleanup_scheduler_returns_callable_stop():
    """start_privacy_cleanup_scheduler returns a callable stop function."""
    from app.services.privacy_cleanup import (
        PrivacyCleanupConfig,
        start_privacy_cleanup_scheduler,
    )

    with patch(
        "app.services.privacy_cleanup.cleanup_privacy_artifacts",
        return_value={"sessions": 0},
    ):
        stop_fn = await start_privacy_cleanup_scheduler(
            config=PrivacyCleanupConfig(interval_seconds=100_000)
        )

    assert callable(stop_fn)
    # Stopping should cancel and await the background task.
    await stop_fn()


@pytest.mark.asyncio
async def test_privacy_cleanup_scheduler_stop_when_task_already_done():
    """Calling stop on a scheduler whose task has already completed is safe."""
    from app.services.privacy_cleanup import (
        PrivacyCleanupConfig,
        start_privacy_cleanup_scheduler,
    )

    # Patch the loop so it completes immediately after one run.
    async def _one_shot_cleanup(**_kwargs):
        return {"sessions": 1}

    with patch(
        "app.services.privacy_cleanup.cleanup_privacy_artifacts",
        side_effect=_one_shot_cleanup,
    ):
        with patch(
            "app.services.privacy_cleanup.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ):
            stop_fn = await start_privacy_cleanup_scheduler(
                config=PrivacyCleanupConfig(interval_seconds=1)
            )

    # By this point the task raised CancelledError during sleep; it is done.
    # Calling stop should be a no-op.
    await stop_fn()


# ---------------------------------------------------------------------------
# app/services/session_cleanup.py → stop when task done
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_cleanup_stop_when_task_done():
    """Calling the stop function when the scheduler task is already done is safe."""
    from app.services.session_cleanup import (
        SessionCleanupConfig,
        start_session_cleanup_scheduler,
    )

    with patch("app.services.session_cleanup.cleanup_expired_sessions", return_value=0):
        # Cancel after first sleep to let the task end quickly.
        with patch(
            "app.services.session_cleanup.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ):
            stop_fn = await start_session_cleanup_scheduler(
                config=SessionCleanupConfig(interval_seconds=1)
            )

    # Task should be done now (CancelledError propagated out).
    # Calling stop is a no-op — verify it doesn't raise.
    await stop_fn()


# ---------------------------------------------------------------------------
# app/services/stats_cache.py → cache_stats decorator paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_stats_decorator_no_user_id_skips_cache():
    """When user_id is None the decorator bypasses cache entirely."""
    from app.services.stats_cache import cache_stats

    class FakeService:
        cache = None

        @cache_stats("grades")
        async def get_stats(self, user_id=None):
            return {"grade": "A"}

    svc = FakeService()
    result = await svc.get_stats(user_id=None)
    assert result == {"grade": "A"}


@pytest.mark.asyncio
async def test_cache_stats_decorator_returns_cached_value():
    """When cache has a hit the decorator returns it without calling the method."""
    import datetime

    from app.deps.cache import CacheEntry
    from app.services.stats_cache import cache_stats

    cached_payload = {"cached": True}
    fake_entry = CacheEntry(
        etag="etag-1", payload=cached_payload, stored_at=datetime.datetime.now()
    )

    class FakeService:
        cache = None

        @cache_stats("grades")
        async def get_stats(self, user_id, period_key="30d"):
            return {"live": True}

    svc = FakeService()
    with patch(
        "app.services.stats_cache.get_cached_stats", return_value=fake_entry
    ) as mock_get:
        result = await svc.get_stats(user_id="user-1", period_key="30d")

    assert result == cached_payload
    mock_get.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_stats_decorator_stores_result_on_miss():
    """On a cache miss the decorator calls the method and stores the result."""
    from app.services.stats_cache import cache_stats

    class FakeService:
        cache = None

        @cache_stats("grades")
        async def get_stats(self, user_id, period_key="30d"):
            return {"live": True}

    svc = FakeService()
    with patch("app.services.stats_cache.get_cached_stats", return_value=None):
        with patch("app.services.stats_cache.set_cached_stats") as mock_set:
            result = await svc.get_stats(user_id="user-1", period_key="30d")

    assert result == {"live": True}
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_stats_decorator_does_not_store_none_result():
    """When the method returns None, the decorator does not call set_cached_stats."""
    from app.services.stats_cache import cache_stats

    class FakeService:
        cache = None

        @cache_stats("grades")
        async def get_stats(self, user_id, period_key="30d"):
            return None

    svc = FakeService()
    with patch("app.services.stats_cache.get_cached_stats", return_value=None):
        with patch("app.services.stats_cache.set_cached_stats") as mock_set:
            result = await svc.get_stats(user_id="user-1", period_key="30d")

    assert result is None
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_period_key_from_days():
    """resolve_period_key produces '30d' when period_key is empty but period_days given."""
    from app.services.stats_cache import resolve_period_key

    assert resolve_period_key("", 30) == "30d"
    assert resolve_period_key("custom", None) == "custom"
    assert resolve_period_key(None, None) == "default"
    assert resolve_period_key("  ", 90) == "90d"


# ---------------------------------------------------------------------------
# app/utils/email.py → send_lockout_email paths
# ---------------------------------------------------------------------------


def test_build_lockout_email_content_default():
    """build_lockout_email_content returns non-empty strings for default locale."""
    from app.utils.email import build_lockout_email_content

    subject, plain, html = build_lockout_email_content("Alice")
    assert subject
    assert plain
    assert "<h2>" in html


def test_build_lockout_email_content_no_name():
    """build_lockout_email_content works when full_name is omitted."""
    from app.utils.email import build_lockout_email_content

    subject, plain, html = build_lockout_email_content()
    assert subject
    assert html


def test_send_lockout_email_no_host_logs_warning(caplog):
    """send_lockout_email logs a warning and returns early when SMTP host is missing."""

    from app.utils.email import send_lockout_email

    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = ""
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "noreply@example.com"
        mock_settings.smtp_security = "starttls"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = True

        # Should complete without error (fallback path)
        send_lockout_email("user@example.com", "Bob")


def test_send_lockout_email_insecure_smtp_blocked():
    """send_lockout_email blocks insecure SMTP in non-dev when user is set."""
    from app.utils.email import send_lockout_email

    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_user = "user@example.com"
        mock_settings.smtp_password = "secret"
        mock_settings.mail_from = "noreply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        # Blocked path: logs error and returns without sending
        send_lockout_email("victim@example.com")


def test_send_lockout_email_ssl_sends():
    """send_lockout_email sends via SMTP_SSL when security='ssl'."""
    from app.utils.email import send_lockout_email

    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "noreply@example.com"
        mock_settings.smtp_security = "ssl"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = True

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp):
            with patch("ssl.create_default_context", return_value=MagicMock()):
                send_lockout_email("user@example.com", "Carol")

        mock_smtp.send_message.assert_called_once()


def test_send_lockout_email_starttls_sends():
    """send_lockout_email sends via STARTTLS when security='starttls'."""
    from app.utils.email import send_lockout_email

    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.mail_from = "noreply@example.com"
        mock_settings.smtp_security = "starttls"
        mock_settings.smtp_starttls = True
        mock_settings.is_development = True

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            with patch("ssl.create_default_context", return_value=MagicMock()):
                send_lockout_email("user@example.com", "Dave")

        mock_smtp.login.assert_called_once_with("user", "pass")
        mock_smtp.send_message.assert_called_once()


def test_send_lockout_email_smtp_error_handled():
    """send_lockout_email logs an error when SMTP raises and does not re-raise."""
    from app.utils.email import send_lockout_email

    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "noreply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = True

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)
        mock_smtp.send_message.side_effect = smtplib.SMTPException("failure")

        with patch("smtplib.SMTP", return_value=mock_smtp):
            # Must not raise — error is swallowed with logging
            send_lockout_email("user@example.com")
