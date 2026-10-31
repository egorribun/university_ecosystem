from __future__ import annotations

import asyncio
import contextlib
import copy
import inspect
import json
import logging
import secrets
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.core.nats_broker as nats_broker_module
from app.core.nats_broker import NatsTaskBroker


@pytest.fixture
def configured_smtp(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="",
        smtp_password=secrets.token_urlsafe(24),
        smtp_security="starttls",
        smtp_starttls=False,
        mail_from="sender@example.test",
        is_development=False,
        environment="production",
    )
    monkeypatch.setattr("app.core.config.settings", settings)
    return settings


def _smtp_client(send: AsyncMock | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        connect=AsyncMock(),
        login=AsyncMock(),
        send_message=send or AsyncMock(),
        close=MagicMock(),
        transport=SimpleNamespace(abort=MagicMock()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("security", "legacy_starttls", "development", "smtp_user", "use_tls", "start_tls"),
    [
        ("ssl", False, False, "", True, False),
        ("starttls", False, False, "", False, True),
        ("", True, False, "", False, True),
        ("", False, False, "", False, False),
        ("none", False, True, "mailer", False, False),
    ],
)
async def test_auth_task_preserves_smtp_message_tls_and_optional_login(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    security: str,
    legacy_starttls: bool,
    development: bool,
    smtp_user: str,
    use_tls: bool,
    start_tls: bool,
) -> None:
    from app.tasks import email as email_tasks

    monkeypatch.setattr(configured_smtp, "smtp_security", security)
    monkeypatch.setattr(configured_smtp, "smtp_starttls", legacy_starttls)
    monkeypatch.setattr(configured_smtp, "is_development", development)
    monkeypatch.setattr(configured_smtp, "smtp_user", smtp_user)
    client = _smtp_client()
    smtp_factory = MagicMock(return_value=client)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)
    monkeypatch.setattr(
        email_tasks.email_utils,
        "build_reset_email_content",
        lambda _link, _name, *, locale: (
            f"Reset {locale}",
            "plain body",
            "<p>html</p>",
        ),
    )

    inner = getattr(
        email_tasks.send_auth_email, "__wrapped__", email_tasks.send_auth_email
    )
    await inner(
        "user@example.test", "https://example.test/reset", "Student", locale="en"
    )

    smtp_factory.assert_called_once()
    options = smtp_factory.call_args.kwargs
    assert options["hostname"] == "smtp.example.test"
    assert options["port"] == 587
    assert options["timeout"] == 10
    assert options["use_tls"] is use_tls
    assert options["start_tls"] is start_tls
    assert isinstance(options["tls_context"], ssl.SSLContext) is (use_tls or start_tls)
    client.connect.assert_awaited_once()
    if smtp_user:
        client.login.assert_awaited_once_with(smtp_user, configured_smtp.smtp_password)
    else:
        client.login.assert_not_awaited()
    message = client.send_message.await_args.args[0]
    assert message["From"] == "sender@example.test"
    assert message["To"] == "user@example.test"
    assert message["Subject"] == "Reset en"
    assert "plain body" in message.get_body(preferencelist=("plain",)).get_content()
    assert "<p>html</p>" in message.get_body(preferencelist=("html",)).get_content()
    client.transport.abort.assert_not_called()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_lockout_task_uses_shared_async_delivery_contract(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    client = _smtp_client()
    smtp_factory = MagicMock(return_value=client)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)
    monkeypatch.setattr(
        email_tasks.email_utils,
        "build_lockout_email_content",
        lambda _name, *, locale: (
            f"Lockout {locale}",
            "plain alert",
            "<p>alert</p>",
        ),
    )

    inner = getattr(
        email_tasks.send_lockout_alert, "__wrapped__", email_tasks.send_lockout_alert
    )
    await inner("user@example.test", "Student", locale="ru")

    message = client.send_message.await_args.args[0]
    assert message["From"] == "sender@example.test"
    assert message["To"] == "user@example.test"
    assert message["Subject"] == "Lockout ru"
    assert "plain alert" in message.get_body(preferencelist=("plain",)).get_content()
    client.connect.assert_awaited_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_missing_smtp_keeps_both_task_fallback_logs(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    monkeypatch.setattr(configured_smtp, "smtp_host", "")
    monkeypatch.setattr(configured_smtp, "smtp_port", 0)
    log_event = MagicMock()
    smtp_factory = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)

    auth_inner = getattr(
        email_tasks.send_auth_email, "__wrapped__", email_tasks.send_auth_email
    )
    lockout_inner = getattr(
        email_tasks.send_lockout_alert, "__wrapped__", email_tasks.send_lockout_alert
    )
    await auth_inner("user@example.test", "https://example.test/reset", "Student")
    await lockout_inner("user@example.test", "Student")

    smtp_factory.assert_not_called()
    assert log_event.call_count == 2
    assert log_event.call_args_list[0].args[:2] == (
        logging.WARNING,
        "password.reset_email.fallback",
    )
    assert log_event.call_args_list[0].kwargs["extra"] == {
        "email": "user@example.test",
        "link": "https://example.test/reset",
    }
    assert log_event.call_args_list[1].args[:2] == (
        logging.WARNING,
        "auth.lockout_email.fallback",
    )
    assert log_event.call_args_list[1].kwargs["extra"] == {"email": "user@example.test"}


@pytest.mark.asyncio
async def test_insecure_authenticated_transport_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    monkeypatch.setattr(configured_smtp, "smtp_security", "none")
    monkeypatch.setattr(configured_smtp, "smtp_user", "mailer")
    log_event = MagicMock()
    smtp_factory = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)

    inner = getattr(
        email_tasks.send_lockout_alert, "__wrapped__", email_tasks.send_lockout_alert
    )
    await inner("user@example.test", "Student")

    smtp_factory.assert_not_called()
    assert log_event.call_args.args[1] == "auth.lockout_email.insecure_smtp"


@pytest.mark.asyncio
async def test_smtp_errors_keep_task_logging_and_suppression_contract(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    events: list[str] = []
    reset_client = _smtp_client(
        AsyncMock(side_effect=OSError("SMTP peer rejected message"))
    )
    lockout_client = _smtp_client(
        AsyncMock(side_effect=email_tasks.aiosmtplib.SMTPException("SMTP error"))
    )

    def record_abort(label: str):
        def abort() -> None:
            events.append(f"{label}.abort")

        return abort

    def record_failing_close(label: str):
        def close() -> None:
            events.append(f"{label}.close")
            raise OSError("local SMTP close failed")

        return close

    for label, client in (("reset", reset_client), ("lockout", lockout_client)):
        client.transport.abort.side_effect = record_abort(label)
        client.close.side_effect = record_failing_close(label)
    smtp_factory = MagicMock(side_effect=[reset_client, lockout_client])
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)
    log_event = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)

    auth_inner = getattr(
        email_tasks.send_auth_email, "__wrapped__", email_tasks.send_auth_email
    )
    lockout_inner = getattr(
        email_tasks.send_lockout_alert, "__wrapped__", email_tasks.send_lockout_alert
    )
    await auth_inner("user@example.test", "https://example.test/reset", "Student")
    await lockout_inner("user@example.test", "Student")

    assert log_event.call_count == 2
    assert log_event.call_args_list[0].args[1] == "password.reset_email.error"
    assert log_event.call_args_list[0].kwargs["extra"] == {
        "email": "user@example.test",
        "link": "https://example.test/reset",
    }
    assert log_event.call_args_list[1].args[1] == "auth.lockout_email.error"
    assert log_event.call_args_list[1].kwargs["extra"] == {"email": "user@example.test"}
    assert log_event.call_args_list[0].kwargs["exc_info"] is False
    assert log_event.call_args_list[1].kwargs["exc_info"] is True
    assert events == [
        "reset.abort",
        "reset.close",
        "lockout.abort",
        "lockout.close",
    ]
    reset_client.transport.abort.assert_called_once()
    reset_client.close.assert_called_once()
    lockout_client.transport.abort.assert_called_once()
    lockout_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_connect_failure_without_transport_does_not_abort(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    client = _smtp_client()
    client.transport = None
    client.connect.side_effect = OSError("SMTP connection failed")
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", MagicMock(return_value=client))
    log_event = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)

    inner = getattr(
        email_tasks.send_lockout_alert, "__wrapped__", email_tasks.send_lockout_alert
    )
    await inner("user@example.test", "Student")

    assert log_event.call_args.args[1] == "auth.lockout_email.error"
    client.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "abort_error",
    [
        OSError("transport abort failed"),
        RuntimeError("transport abort failed"),
    ],
    ids=["abort-oserror", "abort-runtimeerror"],
)
async def test_smtp_abort_failure_still_closes_and_preserves_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    abort_error: Exception,
) -> None:
    from app.tasks import email as email_tasks

    started = asyncio.Event()
    events: list[str] = []

    async def blocked_send(_message: object) -> None:
        started.set()
        await asyncio.Event().wait()

    client = _smtp_client(AsyncMock(side_effect=blocked_send))

    def abort() -> None:
        events.append("abort")
        raise abort_error

    def close() -> None:
        events.append("close")

    client.transport.abort.side_effect = abort
    client.close.side_effect = close
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", MagicMock(return_value=client))
    handler = getattr(
        email_tasks.send_auth_email, "__wrapped__", email_tasks.send_auth_email
    )
    delivery_task: asyncio.Task[None] | None = None

    try:
        delivery_task = asyncio.create_task(
            handler("user@example.test", "https://example.test/reset", "Student")
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        delivery_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await delivery_task
    finally:
        if delivery_task is not None and not delivery_task.done():
            delivery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await delivery_task

    assert events == ["abort", "close"]
    client.transport.abort.assert_called_once()
    client.close.assert_called_once()
    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("encrypted", [False, True], ids=["legacy", "encrypted"])
@pytest.mark.parametrize(
    "abort_error",
    [
        None,
        OSError("transport abort failed"),
        RuntimeError("transport abort failed"),
    ],
    ids=["abort-ok", "abort-oserror", "abort-runtimeerror"],
)
async def test_nats_timeout_cancels_smtp_before_redelivery(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    abort_error: Exception | None,
    encrypted: bool,
) -> None:
    """Cancel local SMTP work before NATS retry; remote exactly-once is unprovable."""
    import app.services.auth_service as auth_module
    from app.tasks import email as email_tasks

    task_name = "app.tasks.email.send_auth_email"
    for registered_name in (
        "app.tasks.email.send_auth_email",
        "app.tasks.email.send_lockout_alert",
    ):
        registered_handler = email_tasks.broker._tasks.get(registered_name)
        assert registered_handler is not None
        assert inspect.iscoroutinefunction(registered_handler), (
            "The NATS email handler must be async before SMTP dependencies are used"
        )
    handler = email_tasks.broker._tasks[task_name]
    events: list[str] = []
    marker = secrets.token_hex(16)
    link = f"https://example.test/reset-password#token={marker}"
    if encrypted:
        secret = secrets.token_hex(32)
        monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
        link = email_tasks.seal_auth_email_link(
            link, datetime.now(UTC) + timedelta(minutes=5), secret
        )
    payload = {
        "id": "same-task-id",
        "name": task_name,
        "args": ["user@example.test", link, "Student"],
        "kwargs": {"locale": "en", "encrypted_link": encrypted},
        "trace_context": {},
    }
    first_message = SimpleNamespace(
        data=json.dumps(payload).encode(),
        metadata=SimpleNamespace(num_delivered=1),
        ack=AsyncMock(),
        nak=AsyncMock(),
    )
    retry_message = SimpleNamespace(
        data=json.dumps(payload).encode(),
        metadata=SimpleNamespace(num_delivered=2),
        ack=AsyncMock(),
        nak=AsyncMock(),
    )

    async def record_first_nak(*, delay: float) -> None:
        del delay
        events.append("first.nak")

    async def record_retry_ack() -> None:
        events.append("retry.ack")

    first_message.nak.side_effect = record_first_nak
    retry_message.ack.side_effect = record_retry_ack
    first_started = asyncio.Event()
    first_cancelled = asyncio.Event()
    retry_started = asyncio.Event()
    third_fetch = asyncio.Event()
    active_sends = 0
    maximum_active_sends = 0
    link_was_delivered: list[bool] = []

    async def blocked_first_send(_message: EmailMessage) -> None:
        nonlocal active_sends, maximum_active_sends
        plain_body = _message.get_body(preferencelist=("plain",))
        link_was_delivered.append(
            plain_body is not None and marker in plain_body.get_content()
        )
        active_sends += 1
        maximum_active_sends = max(maximum_active_sends, active_sends)
        events.append("first.send_started")
        first_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            events.append("first.send_cancelled")
            first_cancelled.set()
            raise
        finally:
            active_sends -= 1

    async def successful_retry_send(_message: EmailMessage) -> None:
        nonlocal active_sends, maximum_active_sends
        plain_body = _message.get_body(preferencelist=("plain",))
        link_was_delivered.append(
            plain_body is not None and marker in plain_body.get_content()
        )
        active_sends += 1
        maximum_active_sends = max(maximum_active_sends, active_sends)
        events.append("retry.send_started")
        retry_started.set()
        try:
            await asyncio.sleep(0)
        finally:
            active_sends -= 1

    first_client = _smtp_client(AsyncMock(side_effect=blocked_first_send))

    def abort_first_transport() -> None:
        events.append("first.transport_abort")
        if abort_error is not None:
            raise abort_error

    def fail_first_close() -> None:
        events.append("first.close")
        raise OSError("local SMTP close failed")

    first_client.transport.abort.side_effect = abort_first_transport
    first_client.close.side_effect = fail_first_close
    retry_client = _smtp_client(AsyncMock(side_effect=successful_retry_send))
    retry_client.close.side_effect = lambda: events.append("retry.close")
    smtp_factory = MagicMock(side_effect=[first_client, retry_client])
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)

    broker = NatsTaskBroker()
    broker.task(name=task_name)(handler)
    fetch_calls = 0

    async def fetch(_batch_size: int, *, timeout: int) -> list[SimpleNamespace]:
        nonlocal fetch_calls
        del timeout
        fetch_calls += 1
        if fetch_calls == 1:
            return [first_message]
        if fetch_calls == 2:
            return [retry_message]
        third_fetch.set()
        raise asyncio.CancelledError

    subscription = SimpleNamespace(fetch=fetch)
    broker._js = SimpleNamespace(pull_subscribe=AsyncMock(return_value=subscription))
    monkeypatch.setattr(nats_broker_module, "_app", None)
    monkeypatch.setattr(nats_broker_module, "_DEFAULT_TASK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(nats_broker_module, "_RETRY_BASE_DELAY_S", 0)

    worker = asyncio.create_task(broker.run_worker())
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.wait_for(third_fetch.wait(), timeout=2)
        with pytest.raises(asyncio.CancelledError):
            await worker
    finally:
        if not worker.done():
            worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    assert first_cancelled.is_set()
    assert retry_started.is_set()
    assert maximum_active_sends == 1
    assert active_sends == 0
    assert link_was_delivered == [True, True]
    first_client.transport.abort.assert_called_once()
    first_client.close.assert_called_once()
    retry_client.transport.abort.assert_not_called()
    retry_client.close.assert_called_once()
    first_message.nak.assert_awaited_once()
    first_message.ack.assert_not_awaited()
    retry_message.ack.assert_awaited_once()
    retry_message.nak.assert_not_awaited()
    assert events == [
        "first.send_started",
        "first.send_cancelled",
        "first.transport_abort",
        "first.close",
        "first.nak",
        "retry.send_started",
        "retry.close",
        "retry.ack",
    ]
    assert fetch_calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing_field", "present_field", "present_value"),
    [
        ("smtp_host", "smtp_port", 587),
        ("smtp_port", "smtp_host", "smtp.example.test"),
    ],
    ids=["host-missing-port-present", "port-missing-host-present"],
)
async def test_each_missing_smtp_coordinate_uses_fallback_independently(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    missing_field: str,
    present_field: str,
    present_value: str | int,
) -> None:
    from app.core.config.notifications import NotificationSettings
    from app.tasks import email as email_tasks

    defaults = NotificationSettings.model_fields
    missing_value = defaults[missing_field].default
    assert missing_value == ("" if missing_field == "smtp_host" else 0)
    monkeypatch.setattr(configured_smtp, missing_field, missing_value)
    monkeypatch.setattr(configured_smtp, present_field, present_value)
    monkeypatch.setattr(
        email_tasks.email_utils,
        "build_lockout_email_content",
        lambda _name, *, locale: (f"Lockout {locale}", "plain", "<p>alert</p>"),
    )
    log_event = MagicMock()
    smtp_factory = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)

    handler = getattr(
        email_tasks.send_lockout_alert,
        "__wrapped__",
        email_tasks.send_lockout_alert,
    )
    await handler("user@example.test", "Student", locale="en")

    smtp_factory.assert_not_called()
    log_event.assert_called_once_with(
        logging.WARNING,
        "auth.lockout_email.fallback",
        extra={"email": "user@example.test"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "smtp_user",
    ["", "mailer"],
    ids=["default-empty-user-skips-login", "user-with-default-empty-password"],
)
async def test_smtp_default_credentials_keep_optional_login_semantics(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    smtp_user: str,
) -> None:
    from app.core.config.notifications import NotificationSettings
    from app.tasks import email as email_tasks

    defaults = NotificationSettings.model_fields
    assert defaults["smtp_user"].default == ""
    assert defaults["smtp_password"].default == ""
    monkeypatch.setattr(configured_smtp, "smtp_user", smtp_user)
    monkeypatch.setattr(
        configured_smtp, "smtp_password", defaults["smtp_password"].default
    )
    monkeypatch.setattr(configured_smtp, "smtp_security", "ssl")
    client = _smtp_client()
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", MagicMock(return_value=client))
    monkeypatch.setattr(
        email_tasks.email_utils,
        "build_lockout_email_content",
        lambda _name, *, locale: (f"Lockout {locale}", "plain", "<p>alert</p>"),
    )

    handler = getattr(
        email_tasks.send_lockout_alert,
        "__wrapped__",
        email_tasks.send_lockout_alert,
    )
    await handler("user@example.test", "Student", locale="en")

    if smtp_user:
        client.login.assert_awaited_once_with(smtp_user, "")
    else:
        client.login.assert_not_awaited()
    client.send_message.assert_awaited_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_name", "builder_name", "args"),
    [
        (
            "send_auth_email",
            "build_reset_email_content",
            ("user@example.test", "https://example.test/reset", "Student"),
        ),
        (
            "send_lockout_alert",
            "build_lockout_email_content",
            ("user@example.test", "Student"),
        ),
    ],
    ids=["auth-default-sender", "lockout-default-sender"],
)
async def test_tasks_use_default_sender_when_mail_from_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
    task_name: str,
    builder_name: str,
    args: tuple[str, ...],
) -> None:
    from app.core.config.notifications import NotificationSettings
    from app.tasks import email as email_tasks

    default_sender = NotificationSettings.model_fields["mail_from"].default
    assert default_sender == "no-reply@example.com"
    monkeypatch.setattr(configured_smtp, "mail_from", "")
    client = _smtp_client()
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", MagicMock(return_value=client))
    monkeypatch.setattr(
        email_tasks.email_utils,
        builder_name,
        lambda *_args, locale: (f"Message {locale}", "plain body", "<p>html</p>"),
    )
    handler = getattr(
        getattr(email_tasks, task_name),
        "__wrapped__",
        getattr(email_tasks, task_name),
    )

    await handler(*args, locale="en")

    sent_message = client.send_message.await_args.args[0]
    assert sent_message["From"] == default_sender
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_missing_smtp_fallback_redacts_reset_token_in_log(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from app.tasks import email as email_tasks

    monkeypatch.setattr(configured_smtp, "smtp_host", "")
    log_event = MagicMock()
    smtp_factory = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)
    monkeypatch.setattr(
        email_tasks.email_utils,
        "build_reset_email_content",
        lambda _link, _name, *, locale: (f"Reset {locale}", "plain", "<p>reset</p>"),
    )

    handler = getattr(
        email_tasks.send_auth_email,
        "__wrapped__",
        email_tasks.send_auth_email,
    )
    reset_token = secrets.token_urlsafe(24)
    reset_url = f"https://example.test/reset?token={reset_token}&locale=en"
    await handler(
        "user@example.test",
        reset_url,
        "Student",
        locale="en",
    )

    expected_redacted_url = (
        "https://example.test/reset?token=%2A%2A%2Aredacted%2A%2A%2A&locale=en"
    )
    smtp_factory.assert_not_called()
    log_event.assert_called_once()
    logged_call = log_event.call_args
    assert logged_call.kwargs["extra"]["link"] == expected_redacted_url
    assert reset_token not in repr(logged_call)


@pytest.mark.asyncio
async def test_shared_delivery_fallback_preserves_non_link_metadata(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from email.message import EmailMessage

    from app.tasks import email as email_tasks

    monkeypatch.setattr(configured_smtp, "smtp_host", "")
    log_event = MagicMock()
    smtp_factory = MagicMock()
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)

    await email_tasks._deliver_email_message(
        to_email="user@example.test",
        message=EmailMessage(),
        insecure_event="test.email.insecure",
        fallback_event="test.email.fallback",
        error_event="test.email.error",
        fallback_fields={"delivery_id": "mail-task-42"},
    )

    smtp_factory.assert_not_called()
    log_event.assert_called_once()
    assert log_event.call_args.args[:2] == (
        logging.WARNING,
        "test.email.fallback",
    )
    assert log_event.call_args.kwargs["extra"] == {
        "email": "user@example.test",
        "delivery_id": "mail-task-42",
    }


@pytest.mark.asyncio
async def test_shared_delivery_error_preserves_non_link_metadata_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    configured_smtp: SimpleNamespace,
) -> None:
    from email.message import EmailMessage

    from app.tasks import email as email_tasks

    smtp_user = f"mailer-{secrets.token_urlsafe(12)}"
    smtp_password = configured_smtp.smtp_password
    monkeypatch.setattr(configured_smtp, "smtp_user", smtp_user)
    events: list[str] = []
    client = _smtp_client(AsyncMock(side_effect=OSError("SMTP peer rejected message")))

    def abort() -> None:
        events.append("abort")

    def close() -> None:
        events.append("close")

    client.transport.abort.side_effect = abort
    client.close.side_effect = close
    smtp_factory = MagicMock(return_value=client)
    log_event = MagicMock()
    monkeypatch.setattr(email_tasks.aiosmtplib, "SMTP", smtp_factory)
    monkeypatch.setattr(email_tasks.email_utils, "_log_event", log_event)

    await email_tasks._deliver_email_message(
        to_email="user@example.test",
        message=EmailMessage(),
        insecure_event="test.email.insecure",
        fallback_event="test.email.fallback",
        error_event="test.email.error",
        error_fields={"delivery_id": "mail-task-43"},
    )

    smtp_factory.assert_called_once()
    client.login.assert_awaited_once_with(smtp_user, smtp_password)
    client.send_message.assert_awaited_once()
    assert events == ["abort", "close"]
    assert log_event.call_count == 1
    assert log_event.call_args.args[:2] == (
        logging.ERROR,
        "test.email.error",
    )
    assert log_event.call_args.kwargs["extra"] == {
        "email": "user@example.test",
        "delivery_id": "mail-task-43",
    }
    logged_call = repr(log_event.mock_calls)
    assert smtp_user not in logged_call
    assert smtp_password not in logged_call


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("non_object", "Invalid auth email envelope"),
        ("legacy_extra_field", "Invalid legacy auth email envelope"),
        ("legacy_non_boolean_marker", "Invalid legacy auth email marker"),
    ],
)
def test_auth_payload_rejects_authenticated_invalid_envelope_shapes(
    monkeypatch: pytest.MonkeyPatch, case: str, expected_error: str
) -> None:
    import app.services.auth_service as auth_module
    from app.tasks import email as email_tasks

    marker = "synthetic-" + secrets.token_hex(12)
    link = f"https://example.test/reset-password#token={marker}"
    secret = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    plain = {"args": ["user@example.test", link], "kwargs": {}}
    plain_before = copy.deepcopy(plain)
    protected, logical = email_tasks.prepare_auth_email_payload(plain)
    valid_round_trip = (
        logical == plain_before
        and email_tasks._read_auth_email_link(protected["args"][1], secret)
        == (link, None, False)
        and marker not in json.dumps(protected)
        and plain == plain_before
    )
    assert valid_round_trip, "valid legacy protection must preserve its logical input"

    legacy: dict[str, Any] = {
        "kind": "auth-email-legacy-v1",
        "link": link,
        "encrypted_link_present": False,
    }
    malformed: object = legacy
    if case == "non_object":
        malformed = [link]
    elif case == "legacy_extra_field":
        legacy["unexpected"] = marker
    else:
        assert case == "legacy_non_boolean_marker"
        legacy["encrypted_link_present"] = 1
    envelope = (
        email_tasks._auth_email_cipher(secret)
        .encrypt(json.dumps(malformed).encode("utf-8"))
        .decode("ascii")
    )

    # The bytes authenticate; rejection must be for the inner format, not crypto.
    with pytest.raises(ValueError, match=rf"^{expected_error}$"):
        email_tasks._read_auth_email_link(envelope, secret)
    payload = {
        "args": ["user@example.test", envelope],
        "kwargs": {"encrypted_link": True},
    }
    before = copy.deepcopy(payload)
    with pytest.raises(email_tasks.AuthEmailPayloadError) as failure:
        email_tasks.prepare_auth_email_payload(payload)
    opaque = (
        str(failure.value) == "Authentication email payload protection failed"
        and failure.value.__cause__ is None
        and failure.value.__suppress_context__
    )
    unchanged = payload == before
    assert opaque, "task preparation must expose only its bounded rejection"
    assert unchanged, "rejection must not partially rewrite the caller payload"


@pytest.mark.parametrize(
    "case",
    ["extra_field", "tuple_args", "list_kwargs", "non_string_link", "integer_marker"],
)
def test_auth_payload_rejects_invalid_task_structure_without_mutation(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    import app.services.auth_service as auth_module
    from app.tasks import email as email_tasks

    marker = "synthetic-" + secrets.token_hex(12)
    link = f"https://example.test/reset-password#token={marker}"
    secret = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    envelope = email_tasks.seal_auth_email_link(
        link, datetime.now(UTC) + timedelta(minutes=5), secret
    )
    valid = {
        "args": ["user@example.test", envelope],
        "kwargs": {"encrypted_link": True},
    }
    original = copy.deepcopy(valid)
    protected, logical = email_tasks.prepare_auth_email_payload(valid)
    valid_unchanged = (
        protected == original and logical == original and valid == original
    )
    assert valid_unchanged, "valid native envelopes must preserve their exact payload"

    payload: dict[str, Any] = copy.deepcopy(valid)
    if case == "extra_field":
        payload["unexpected"] = marker
    elif case == "tuple_args":
        payload["args"] = tuple(payload["args"])
    elif case == "list_kwargs":
        payload["kwargs"] = []
    elif case == "non_string_link":
        payload["args"][1] = 1
        payload["kwargs"] = {}
    else:
        assert case == "integer_marker"
        # Use an authentic envelope: a later decrypt failure must not hide a
        # missing strict-bool check for the otherwise truthy integer marker.
        payload["kwargs"]["encrypted_link"] = 1
    before = copy.deepcopy(payload)
    with pytest.raises(email_tasks.AuthEmailPayloadError) as failure:
        email_tasks.prepare_auth_email_payload(payload)
    opaque = (
        str(failure.value) == "Authentication email payload protection failed"
        and failure.value.__cause__ is None
        and failure.value.__suppress_context__
    )
    unchanged = payload == before
    assert opaque, "invalid task arguments must produce only the bounded rejection"
    assert unchanged, "rejection must not partially rewrite the caller payload"
