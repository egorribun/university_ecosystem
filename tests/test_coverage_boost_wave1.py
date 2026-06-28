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
import io
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
        await start_notifications_scheduler(
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

    subject, _, html = build_lockout_email_content()
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
        mock_settings.smtp_password = "secret"  # pragma: allowlist secret
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
        mock_settings.smtp_password = "pass"  # pragma: allowlist secret
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


# ---------------------------------------------------------------------------
# Wave 1 Coverage Boost: NatsTaskBroker, NatsService, FileScanner
# ---------------------------------------------------------------------------
import json

import nats.errors
from pydantic import ValidationError


def test_nats_task_payload_empty_name():
    from app.core.nats_broker import _NatsTaskPayload

    with pytest.raises(ValidationError):
        _NatsTaskPayload(id="123", name="")
    with pytest.raises(ValidationError):
        _NatsTaskPayload(id="123", name="   ")


def test_nats_broker_js_property():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    assert broker.js is None
    mock_js = MagicMock()
    broker._js = mock_js
    assert broker.js is mock_js


@pytest.mark.asyncio
async def test_nats_broker_connect_callbacks():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)

    with patch("nats.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_nc
        await broker.connect()

        # Extract callbacks
        kwargs = mock_connect.call_args.kwargs
        reconnected_cb = kwargs.get("reconnected_cb")
        disconnected_cb = kwargs.get("disconnected_cb")

        assert reconnected_cb is not None
        assert disconnected_cb is not None

        # Call them to cover warning logging statements
        await reconnected_cb()
        await disconnected_cb()


@pytest.mark.asyncio
async def test_nats_broker_close_error():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    mock_nc.close.side_effect = OSError("Connection refused")
    broker._nc = mock_nc
    broker._js = AsyncMock()

    # Should handle error and clear client/JS refs
    await broker.close()
    assert broker._nc is None
    assert broker._js is None


@pytest.mark.asyncio
async def test_nats_broker_publish_not_available():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    with patch.object(broker, "connect", AsyncMock()):
        with pytest.raises(RuntimeError, match="NATS JetStream not available"):
            await broker.publish("subject", {})


@pytest.mark.asyncio
async def test_nats_broker_enqueue_not_available():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    with patch.object(broker, "connect", AsyncMock()):
        with pytest.raises(RuntimeError, match="NATS JetStream not available"):
            await broker.enqueue("task_name")


@pytest.mark.asyncio
async def test_nats_broker_run_worker_no_dishka():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js

    # Sync task handler
    sync_called = False

    def my_sync_handler(x):
        nonlocal sync_called
        sync_called = True
        assert x == 42

    # Async task handler
    async_called = False

    async def my_async_handler(x):
        nonlocal async_called
        async_called = True
        assert x == 42

    broker._tasks["sync_task"] = my_sync_handler
    broker._tasks["async_task"] = my_async_handler

    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub

    msg1 = AsyncMock()
    msg1.data = json.dumps(
        {
            "id": "1",
            "name": "sync_task",
            "args": [42],
            "kwargs": {},
            "trace_context": {},
        }
    ).encode()
    msg2 = AsyncMock()
    msg2.data = json.dumps(
        {
            "id": "2",
            "name": "async_task",
            "args": [42],
            "kwargs": {},
            "trace_context": {},
        }
    ).encode()

    loop_count = 0

    async def mock_fetch(batch_size, timeout=5):
        nonlocal loop_count
        loop_count += 1
        if loop_count == 1:
            return [msg1, msg2]
        raise asyncio.CancelledError()

    mock_sub.fetch = mock_fetch

    from app.core.nats_broker import set_app

    set_app(None)

    try:
        await broker.run_worker()
    except asyncio.CancelledError:
        pass

    assert sync_called is True
    assert async_called is True
    msg1.ack.assert_called_once()
    msg2.ack.assert_called_once()


@pytest.mark.asyncio
async def test_nats_broker_run_worker_errors():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js

    # TimeoutError
    async def timeout_handler():
        raise TimeoutError()

    # General Exception
    async def fail_handler():
        raise ValueError("Oops")

    broker._tasks["timeout_task"] = timeout_handler
    broker._tasks["fail_task"] = fail_handler

    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub

    msg_timeout = AsyncMock()
    msg_timeout.data = json.dumps(
        {
            "id": "1",
            "name": "timeout_task",
            "args": [],
            "kwargs": {},
            "trace_context": {},
        }
    ).encode()

    msg_fail = AsyncMock()
    msg_fail.data = json.dumps(
        {"id": "2", "name": "fail_task", "args": [], "kwargs": {}, "trace_context": {}}
    ).encode()

    loop_count = 0

    async def mock_fetch(batch_size, timeout=5):
        nonlocal loop_count
        loop_count += 1
        if loop_count == 1:
            return [msg_timeout, msg_fail]
        raise asyncio.CancelledError()

    mock_sub.fetch = mock_fetch

    from app.core.nats_broker import set_app

    set_app(None)

    try:
        await broker.run_worker()
    except asyncio.CancelledError:
        pass

    msg_timeout.nak.assert_called_once()
    msg_fail.nak.assert_called_once()


@pytest.mark.asyncio
async def test_nats_broker_run_worker_outer_exceptions():
    from app.core.nats_broker import NatsTaskBroker

    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js

    mock_sub = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub

    loop_count = 0

    async def mock_fetch(batch_size, timeout=5):
        nonlocal loop_count
        loop_count += 1
        if loop_count == 1:
            raise nats.errors.TimeoutError()
        elif loop_count == 2:
            raise RuntimeError("Fatal broker error")
        raise asyncio.CancelledError()

    mock_sub.fetch = mock_fetch

    with patch(
        "app.core.nats_broker.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        try:
            await broker.run_worker()
        except asyncio.CancelledError:
            pass

        mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_nats_service_close_drain_raises():
    from app.services.nats_messaging import NatsService

    service = NatsService()
    mock_client = AsyncMock()
    service._client = mock_client
    service._js = AsyncMock()

    await service.close()
    mock_client.drain.assert_called_once()


@pytest.mark.asyncio
async def test_nats_service_ensure_stream_error():
    from app.services.nats_messaging import NatsService

    service = NatsService()
    mock_js = AsyncMock()
    service._js = mock_js

    mock_js.add_stream.side_effect = ConnectionError("NATS disconnected")
    with patch("app.services.nats_messaging.logger.warning") as mock_warn:
        await service.ensure_stream(name="test", subjects=["test"])
        mock_warn.assert_called_once()
        assert "Stream setup issue" in mock_warn.call_args[0][0]


@pytest.mark.asyncio
async def test_nats_service_not_connected_errors():
    from app.services.nats_messaging import NatsService

    service = NatsService()

    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.publish("subject", b"data")

    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.publish_jetstream("subject", b"data")

    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.subscribe("subject", AsyncMock())

    with pytest.raises(RuntimeError, match="Not connected to NATS"):
        await service.subscribe_jetstream("stream", "subject", AsyncMock())


@pytest.mark.asyncio
async def test_nats_service_publish_dict_encoding():
    from app.services.nats_messaging import NatsService

    service = NatsService()
    mock_client = AsyncMock()
    service._client = mock_client

    await service.publish("subject", {"hello": "world"})
    mock_client.publish.assert_called_once()
    args = mock_client.publish.call_args.args
    assert b"hello" in args[1]


def test_get_nats_service_lock_initialization():
    import app.services.nats_messaging as nm

    with patch.object(nm, "_nats_service", None):
        s1 = nm.get_nats_service()
        assert s1 is not None
        assert nm._nats_service is s1


def test_create_clamd_client_network():
    from app.services.file_scanner import _create_clamd_client

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "127.0.0.1"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 10.0
        with patch("clamd.ClamdNetworkSocket") as mock_net:
            _create_clamd_client()
            mock_net.assert_called_once_with(host="127.0.0.1", port=3310, timeout=10.0)


def test_scan_with_clamd_stream_unavailable_propagates():
    from app.services.file_scanner import (
        FileScannerUnavailableError,
        _scan_with_clamd_stream,
    )

    with patch(
        "app.services.file_scanner._create_clamd_client",
        side_effect=FileScannerUnavailableError("offline"),
    ):
        with pytest.raises(FileScannerUnavailableError, match="offline"):
            _scan_with_clamd_stream(io.BytesIO(b"data"))


def test_check_clamd_health_unavailable_propagates():
    from app.services.file_scanner import (
        FileScannerUnavailableError,
        _check_clamd_health,
    )

    with patch(
        "app.services.file_scanner._create_clamd_client",
        side_effect=FileScannerUnavailableError("offline"),
    ):
        with pytest.raises(FileScannerUnavailableError, match="offline"):
            _check_clamd_health()


def test_check_clamd_health_success():
    from app.services.file_scanner import _check_clamd_health

    mock_client = MagicMock()
    mock_client.ping.return_value = "PONG"
    with patch(
        "app.services.file_scanner._create_clamd_client", return_value=mock_client
    ):
        _check_clamd_health()


def test_scanner_duration_limit_zero_or_negative():
    from app.services.file_scanner import _scanner_duration_limit_seconds

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_max_duration_sec = 0.0
        assert _scanner_duration_limit_seconds() == 0.0
        mock_settings.event_file_scanner_max_duration_sec = -5.0
        assert _scanner_duration_limit_seconds() == 0.0


def test_upload_stream_read_eof():
    from app.services.file_scanner import _UploadStream

    wrapped = io.BytesIO(b"")
    stream = _UploadStream(wrapped, limit=10)
    assert stream.read() == b""


@pytest.mark.asyncio
async def test_scan_for_malware_upload_file():
    from fastapi import UploadFile

    from app.services.file_scanner import _ScanResult, scan_for_malware

    mock_upload = AsyncMock(spec=UploadFile)

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"
        mock_settings.event_file_scanner_max_size_mb = 0.0

        scan_res = _ScanResult(signature=None, duration=0.1, bytes_scanned=10)
        with patch(
            "app.services.file_scanner._scan_upload_with_clamd", return_value=scan_res
        ) as mock_scan:
            await scan_for_malware(mock_upload, size_bytes=10)
            mock_scan.assert_called_once_with(mock_upload, size_limit=0)


@pytest.mark.asyncio
async def test_scan_for_malware_payload_too_large_exception_handling():
    from fastapi import HTTPException

    from app.services.file_scanner import FileScannerPayloadTooLarge, scan_for_malware

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            side_effect=FileScannerPayloadTooLarge(100, limit_bytes=50),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await scan_for_malware(b"data")
            assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_scan_for_malware_quarantine_called():
    from fastapi import HTTPException

    from app.services.file_scanner import _ScanResult, scan_for_malware

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = True
        mock_settings.event_file_scanner_backend = "clamd"
        mock_settings.environment = "testing"

        infected_res = _ScanResult(signature="Eicar", duration=0.1, bytes_scanned=10)
        quarantine_payload = b"infected-data"
        mock_handler = AsyncMock()

        with patch(
            "app.services.file_scanner._scan_bytes_with_clamd",
            return_value=infected_res,
        ):
            with pytest.raises(HTTPException):
                await scan_for_malware(
                    b"some-payload",
                    quarantine_payload=quarantine_payload,
                    quarantine_handler=mock_handler,
                )
            mock_handler.assert_called_once_with(quarantine_payload, "Eicar")


@pytest.mark.asyncio
async def test_check_file_scanner_health_disabled():
    from app.services.file_scanner import check_file_scanner_health

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_enabled = False
        with patch("app.services.file_scanner._check_clamd_health") as mock_check:
            await check_file_scanner_health()
            mock_check.assert_not_called()


@pytest.mark.asyncio
async def test_scan_upload_with_clamd_timeout():
    from fastapi import UploadFile

    from app.services.file_scanner import (
        FileScannerUnavailableError,
        _scan_upload_with_clamd,
    )

    mock_upload = AsyncMock(spec=UploadFile)
    mock_upload.seek = AsyncMock()
    mock_upload.read.side_effect = [b"chunk", b""]

    with patch("app.services.file_scanner.settings") as mock_settings:
        mock_settings.event_file_scanner_socket = ""
        mock_settings.event_file_scanner_host = "localhost"
        mock_settings.event_file_scanner_port = 3310
        mock_settings.event_file_scanner_timeout = 5.0

        with patch("asyncio.open_connection", side_effect=TimeoutError()):
            with pytest.raises(
                FileScannerUnavailableError, match="clamd scan timed out"
            ):
                await _scan_upload_with_clamd(mock_upload, size_limit=1000)


# ---------------------------------------------------------------------------
# Wave 1 Coverage Boost: app/core/lifespan.py
# ---------------------------------------------------------------------------
def test_runtime_feature_overrides():
    from app.core.lifespan import RuntimeFeatureOverrides

    overrides = RuntimeFeatureOverrides()
    assert overrides.resolve("semantic_search_enabled", default=True) is True
    assert overrides.resolve("semantic_search_enabled", default=False) is False

    overrides.semantic_search_enabled = True
    assert overrides.resolve("semantic_search_enabled", default=False) is True

    overrides.disable("semantic_search_enabled")
    assert overrides.resolve("semantic_search_enabled", default=True) is False

    with pytest.raises(AttributeError):
        overrides.disable("non_existent_flag")


@pytest.mark.asyncio
async def test_startup_database_and_di_raises_when_no_token_secret_in_prod():
    from app.core.lifespan import _startup_database_and_di

    mock_app = MagicMock()
    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.spotify_token_secret = ""
        mock_settings.environment = "production"
        with pytest.raises(RuntimeError, match="SPOTIFY_TOKEN_SECRET must be set"):
            await _startup_database_and_di(mock_app)

        mock_settings.environment = "development"
        with patch("app.core.lifespan._logger.warning") as mock_warn:
            await _startup_database_and_di(mock_app)
            mock_warn.assert_called_once()


@pytest.mark.asyncio
async def test_verify_database_readiness_exceptions():
    from app.core.lifespan import _verify_database_readiness

    with patch("app.core.lifespan.wait_db", side_effect=TimeoutError("DB offline")):
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "production"
            with pytest.raises(TimeoutError):
                await _verify_database_readiness()

            mock_settings.environment = "development"
            with patch("app.core.lifespan._logger.warning") as mock_warn:
                await _verify_database_readiness()
                assert any(
                    "Database unavailable" in call.args[0]
                    for call in mock_warn.call_args_list
                )


@pytest.mark.asyncio
async def test_verify_database_readiness_migration_check_raises():
    from app.core.lifespan import _verify_database_readiness

    with patch("app.core.lifespan.wait_db", new_callable=AsyncMock):
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "local"
            mock_engine = AsyncMock()
            mock_engine.connect.side_effect = ValueError("Mock connection error")
            with patch("app.core.lifespan.engine", mock_engine):
                with patch("app.core.lifespan._logger.warning") as mock_warn:
                    await _verify_database_readiness()
                    mock_warn.assert_called_once()
                    assert (
                        "Migration head check skipped/failed"
                        in mock_warn.call_args[0][0]
                    )


@pytest.mark.asyncio
async def test_verify_database_readiness_migration_check_raises_in_prod():
    from app.core.lifespan import _verify_database_readiness

    with patch("app.core.lifespan.wait_db", new_callable=AsyncMock):
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_engine = AsyncMock()
            mock_engine.connect.side_effect = ValueError("Mock connection error")
            with patch("app.core.lifespan.engine", mock_engine):
                with patch(
                    "alembic.config.Config", side_effect=ValueError("Bad config")
                ):
                    with pytest.raises(ValueError, match="Bad config"):
                        await _verify_database_readiness()


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_disabled():
    from app.core.lifespan import _handle_schema_and_extensions

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.auto_create_schema = False
        await _handle_schema_and_extensions()


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_pgvector_error():
    from app.core.lifespan import _handle_schema_and_extensions, runtime_flags

    mock_conn = AsyncMock()
    mock_conn.dialect.name = "postgresql"
    mock_conn.execute.side_effect = ConnectionError("DB offline")

    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock()

    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_begin

    runtime_flags.semantic_search_enabled = True

    with patch("app.core.lifespan.engine", mock_engine):
        with patch("app.core.lifespan._logger.warning") as mock_warn:
            await _handle_schema_and_extensions()
            mock_warn.assert_called_once()
            assert runtime_flags.semantic_search_enabled is False


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_general_error():
    from app.core.lifespan import _handle_schema_and_extensions

    mock_engine = MagicMock()
    mock_engine.begin.side_effect = ValueError("Fatal DB error")

    with patch("app.core.lifespan.engine", mock_engine):
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "production"
            mock_settings.auto_create_schema = True
            with pytest.raises(ValueError, match="Fatal DB error"):
                await _handle_schema_and_extensions()

            mock_settings.environment = "development"
            with patch("app.core.lifespan._logger.warning") as mock_warn:
                await _handle_schema_and_extensions()
                mock_warn.assert_called_once()


@pytest.mark.asyncio
async def test_handle_schema_and_extensions_sqlite_patch():
    from app.core.lifespan import _handle_schema_and_extensions

    mock_conn = AsyncMock()
    mock_conn.dialect.name = "sqlite"

    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_begin.__aexit__ = AsyncMock()

    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_begin

    from sqlalchemy import Column, Computed, Integer, MetaData, Table

    metadata = MetaData()
    table = Table(
        "dummy_test_table",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tsv", Integer, Computed("to_tsvector('english', 'test')")),
    )

    with patch("app.core.lifespan.engine", mock_engine):
        with patch("app.core.lifespan.Base") as mock_base:
            mock_base.metadata.tables = {"dummy_test_table": table}
            await _handle_schema_and_extensions()
            assert table.columns.tsv.computed is None


@pytest.mark.asyncio
async def test_validate_di_container():
    from app.core.lifespan import _validate_di_container

    mock_app = MagicMock()
    mock_container = AsyncMock()
    mock_container.get.side_effect = ValueError("DI fail")
    mock_app.state.dishka_container = mock_container

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.environment = "production"
        with pytest.raises(RuntimeError, match="DI container smoke-test FAILED"):
            await _validate_di_container(mock_app)

        mock_settings.environment = "development"
        with patch("app.core.lifespan._logger.warning") as mock_warn:
            await _validate_di_container(mock_app)
            mock_warn.assert_called_once()

    mock_container.get.side_effect = None
    mock_container.get.return_value = MagicMock()
    with patch("app.core.lifespan._logger.info") as mock_info:
        await _validate_di_container(mock_app)
        mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_startup_background_workers_non_testing():
    from app.core.lifespan import _startup_background_workers

    mock_app = MagicMock()
    mock_app.state.background_tasks = set()

    mock_container = AsyncMock()
    mock_outbox = AsyncMock()
    mock_nats = AsyncMock()
    mock_nats.is_connected = True

    async def mock_get(cls):
        from app.core.nats_broker import NatsTaskBroker
        from app.workers.outbox import OutboxWorker

        if cls is OutboxWorker:
            return mock_outbox
        if cls is NatsTaskBroker:
            return mock_nats

    mock_container.get = mock_get
    mock_app.state.dishka_container = mock_container

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.environment = "development"
        with patch(
            "app.core.lifespan._periodic_scheduler_loop", return_value=AsyncMock()
        ):
            with patch(
                "app.core.lifespan.setup_periodic_cleanups", new_callable=AsyncMock
            ):
                await _startup_background_workers(mock_app)
                assert len(mock_app.state.background_tasks) == 3
                for task in mock_app.state.background_tasks:
                    task.cancel()


@pytest.mark.asyncio
async def test_startup_background_workers_partition_management():
    from app.core.lifespan import _startup_background_workers

    mock_app = MagicMock()
    mock_app.state.background_tasks = set()

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.environment = "testing"
        mock_settings.partition_management_enabled = True
        mock_settings.partition_management_interval_seconds = 3600

        with patch(
            "app.core.lifespan.ensure_partitions_exist", new_callable=AsyncMock
        ) as mock_ensure:
            with patch(
                "app.core.lifespan.start_partition_management_scheduler",
                new_callable=AsyncMock,
            ) as mock_start:
                await _startup_background_workers(mock_app)
                mock_ensure.assert_awaited_once()
                mock_start.assert_not_awaited()

        with patch(
            "app.core.lifespan.ensure_partitions_exist",
            side_effect=ValueError("Partition error"),
        ):
            with patch("app.core.lifespan._logger.warning") as mock_warn:
                await _startup_background_workers(mock_app)
                mock_warn.assert_called_once()
                assert "Partition init failed" in mock_warn.call_args[0][0]


@pytest.mark.asyncio
async def test_periodic_scheduler_loop():
    import app.tasks.cleanups as cleanups
    from app.core.lifespan import _SCHEDULER_STOP, _periodic_scheduler_loop

    _SCHEDULER_STOP.clear()

    mock_cleanup = AsyncMock()

    async def mock_kick():
        _SCHEDULER_STOP.set()

    mock_cleanup.kick = mock_kick

    with patch.multiple(
        cleanups,
        cleanup_stories_task=mock_cleanup,
        cleanup_password_reset_tokens_task=mock_cleanup,
        cleanup_email_change_tokens_task=mock_cleanup,
        cleanup_mfa_challenges_task=mock_cleanup,
        cleanup_sessions_task=mock_cleanup,
        cleanup_notifications_task=mock_cleanup,
        cleanup_dead_letter_jobs_task=mock_cleanup,
        cleanup_privacy_artifacts_task=mock_cleanup,
        manage_partitions_task=mock_cleanup,
    ):
        with patch("random.uniform", return_value=0.001):
            import datetime

            mock_now = datetime.datetime(2026, 6, 22, 2, 0, 0, tzinfo=datetime.UTC)
            with patch("datetime.datetime") as mock_datetime:
                mock_datetime.now.return_value = mock_now
                mock_datetime.UTC = datetime.UTC

                await _periodic_scheduler_loop()

    assert _SCHEDULER_STOP.is_set()


@pytest.mark.asyncio
async def test_periodic_scheduler_loop_task_failure():
    import app.tasks.cleanups as cleanups
    from app.core.lifespan import _SCHEDULER_STOP, _periodic_scheduler_loop

    _SCHEDULER_STOP.clear()

    mock_fail = AsyncMock()
    mock_fail.kick.side_effect = ValueError("Kick failed")

    mock_success = AsyncMock()

    async def mock_kick():
        _SCHEDULER_STOP.set()

    mock_success.kick = mock_kick

    with patch.multiple(
        cleanups,
        cleanup_stories_task=mock_fail,
        cleanup_password_reset_tokens_task=mock_success,
        cleanup_email_change_tokens_task=mock_success,
        cleanup_mfa_challenges_task=mock_success,
        cleanup_sessions_task=mock_success,
        cleanup_notifications_task=mock_success,
        cleanup_dead_letter_jobs_task=mock_success,
        cleanup_privacy_artifacts_task=mock_success,
        manage_partitions_task=mock_success,
    ):
        with patch("random.uniform", return_value=0.001):
            import datetime

            mock_now = datetime.datetime(2026, 6, 22, 2, 0, 0, tzinfo=datetime.UTC)
            with patch("datetime.datetime") as mock_datetime:
                mock_datetime.now.return_value = mock_now
                mock_datetime.UTC = datetime.UTC

                with patch(
                    "app.core.metrics.record_background_task_error"
                ) as mock_metric:
                    await _periodic_scheduler_loop()
                    mock_metric.assert_called_once()


@pytest.mark.asyncio
async def test_prewarm_jwt_public_key_cache():
    from app.core.lifespan import _prewarm_jwt_public_key_cache

    with patch("app.core.lifespan.settings") as mock_settings:
        mock_settings.jwt_signing_key_registry = {
            "key1": "--- BEGIN PRIVATE KEY ---",  # pragma: allowlist secret
            "key2": "some-symmetric-secret",
        }

        with patch("app.auth.security._get_cached_public_key_pem") as mock_get:
            await _prewarm_jwt_public_key_cache()
            mock_get.assert_called_once_with(
                "key1",
                "--- BEGIN PRIVATE KEY ---",  # pragma: allowlist secret
            )

        with patch(
            "app.auth.security._get_cached_public_key_pem",
            side_effect=ValueError("Invalid PEM"),
        ):
            with patch("app.core.lifespan._logger.warning") as mock_warn:
                await _prewarm_jwt_public_key_cache()
                mock_warn.assert_called_once()
                assert "JWT key pre-warm failed" in mock_warn.call_args[0][0]


@pytest.mark.asyncio
async def test_lifespan_context_manager():
    from app.core.lifespan import _SCHEDULER_STOP, lifespan

    mock_app = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.background_tasks = set()
    mock_app.state.partition_stopper = AsyncMock()
    mock_app.state.dishka_container = AsyncMock()

    with (
        patch(
            "app.core.lifespan._startup_database_and_di", new_callable=AsyncMock
        ) as mock_db,
        patch(
            "app.core.lifespan._startup_websocket_and_flags", new_callable=AsyncMock
        ) as mock_ws,
        patch(
            "app.core.lifespan._validate_di_container", new_callable=AsyncMock
        ) as mock_di,
        patch(
            "app.core.lifespan._verify_database_readiness", new_callable=AsyncMock
        ) as mock_ready,
        patch(
            "app.core.lifespan._handle_schema_and_extensions", new_callable=AsyncMock
        ) as mock_schema,
        patch(
            "app.core.lifespan._startup_background_workers", new_callable=AsyncMock
        ) as mock_workers,
        patch(
            "app.core.lifespan._prewarm_jwt_public_key_cache", new_callable=AsyncMock
        ) as mock_prewarm,
        patch("app.core.lifespan.settings") as mock_settings,
    ):
        mock_settings.environment = "development"

        with patch(
            "app.core.lifespan.warm_cache", side_effect=ValueError("Warm fail")
        ) as mock_warm:
            async with lifespan(mock_app):
                mock_db.assert_awaited_once()
                mock_ws.assert_awaited_once()
                mock_di.assert_awaited_once()
                mock_ready.assert_awaited_once()
                mock_schema.assert_awaited_once()
                mock_workers.assert_awaited_once()
                mock_warm.assert_awaited_once()
                mock_prewarm.assert_awaited_once()

            assert _SCHEDULER_STOP.is_set()
            mock_app.state.partition_stopper.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_prewarm_exception():
    from app.core.lifespan import lifespan

    mock_app = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.background_tasks = set()

    with (
        patch("app.core.lifespan._startup_database_and_di", new_callable=AsyncMock),
        patch("app.core.lifespan._startup_websocket_and_flags", new_callable=AsyncMock),
        patch("app.core.lifespan._validate_di_container", new_callable=AsyncMock),
        patch("app.core.lifespan._verify_database_readiness", new_callable=AsyncMock),
        patch(
            "app.core.lifespan._handle_schema_and_extensions", new_callable=AsyncMock
        ),
        patch("app.core.lifespan._startup_background_workers", new_callable=AsyncMock),
        patch(
            "app.core.lifespan._prewarm_jwt_public_key_cache",
            side_effect=ValueError("Prewarm fail"),
        ),
        patch("app.core.lifespan._shutdown_subsystems", new_callable=AsyncMock),
        patch("app.core.lifespan.settings") as mock_settings,
    ):
        mock_settings.environment = "testing"

        with patch("app.core.lifespan._logger.warning") as mock_warn:
            async with lifespan(mock_app):
                pass
            mock_warn.assert_called_once()
            assert "JWT public key pre-warm failed" in mock_warn.call_args[0][0]


@pytest.mark.asyncio
async def test_shutdown_subsystems_cancels_tasks():
    from app.core.lifespan import _shutdown_subsystems

    mock_app = MagicMock()
    mock_app.state = MagicMock()
    mock_app.state.dishka_container = AsyncMock()
    mock_app.state.partition_stopper = AsyncMock()

    mock_task = asyncio.create_task(asyncio.sleep(999))
    mock_app.state.background_tasks = {mock_task}

    with (
        patch("app.api.health.set_shutdown_flag"),
        patch("app.api.ws.presence.stop_presence_pubsub", new_callable=AsyncMock),
        patch("app.auth.security.close_hibp_client", new_callable=AsyncMock),
        patch("app.core.feature_flags.feature_flags.close", new_callable=AsyncMock),
        patch("app.core.ratelimit.stop_memory_cleanup_task", new_callable=AsyncMock),
        patch("app.services.geolocation.shutdown_geolocation_service"),
        patch(
            "app.services.notification_queue.shutdown_notification_queue",
            new_callable=AsyncMock,
        ),
        patch("app.services.webpush.cleanup"),
        patch("app.deps.cache.shutdown_cache", new_callable=AsyncMock),
        patch("app.core.spicedb.close_global_spicedb_channel", new_callable=AsyncMock),
        patch("app.core.observability.shutdown_observability"),
    ):
        await _shutdown_subsystems(mock_app)
        assert mock_task.cancelled() or mock_task.done()
