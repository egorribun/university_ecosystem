"""Cancellation must not detach an in-flight SMTP send from durable delivery."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch

import pytest

from app.auth.mfa.email_otp import SmtpMfaEmailSender
from app.core import events


@pytest.mark.asyncio
async def test_smtp_sender_waits_for_in_flight_thread_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_send(**_kwargs: str) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test SMTP sender was not released")

    monkeypatch.setattr(SmtpMfaEmailSender, "_send_sync", staticmethod(blocking_send))
    sender = SmtpMfaEmailSender()
    task = asyncio.create_task(
        sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code",
            html="<p>code</p>",
            message_id="<stable@example.test>",
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "SMTP send must remain attached until the thread exits"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_smtp_sender_keeps_waiting_after_a_second_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def blocking_send(**_kwargs: str) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test SMTP sender was not released")

    monkeypatch.setattr(SmtpMfaEmailSender, "_send_sync", staticmethod(blocking_send))
    sender = SmtpMfaEmailSender()
    task = asyncio.create_task(
        sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code",
            html="<p>code</p>",
            message_id="<stable@example.test>",
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "repeated cancellation must not orphan SMTP"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_smtp_failure_does_not_escape_through_asyncio_logging(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def failing_send(**_kwargs: str) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test SMTP sender was not released")
        raise OSError("recipient user@example.test, code 123456")

    monkeypatch.setattr(SmtpMfaEmailSender, "_send_sync", staticmethod(failing_send))
    sender = SmtpMfaEmailSender()
    task = asyncio.create_task(
        sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code",
            html="<p>code</p>",
            message_id="<stable@example.test>",
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(OSError, match=r"recipient user@example\.test, code 123456"):
        await task
    await asyncio.sleep(0)
    assert "user@example.test" not in caplog.text
    assert "123456" not in caplog.text


@pytest.mark.asyncio
async def test_durable_mfa_dispatch_waits_for_send_and_acknowledges_real_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = threading.Event()
    release = threading.Event()
    completed: list[str] = []

    def blocking_send(**_kwargs: str) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test SMTP sender was not released")

    monkeypatch.setattr(SmtpMfaEmailSender, "_send_sync", staticmethod(blocking_send))
    sender = SmtpMfaEmailSender()
    event = events.MfaEmailDeliveryRequested()
    bus = events.EventBus()

    async def handler(_event: events.DomainEvent) -> None:
        await sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code",
            html="<p>code</p>",
            message_id="<stable@example.test>",
        )
        completed.append("sent")

    async def pending_wait(
        tasks: set[asyncio.Task[object]], *, timeout: float
    ) -> tuple[set[asyncio.Task[object]], set[asyncio.Task[object]]]:
        del timeout
        assert await asyncio.to_thread(started.wait, 2)
        return set(), tasks

    bus.subscribe(event.event_type, handler)
    with patch.object(events.asyncio, "wait", side_effect=pending_wait):
        publish_task = asyncio.create_task(bus.publish(event, durable=True))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            await asyncio.sleep(0)
            assert not publish_task.done(), "durable dispatch must await SMTP outcome"
        finally:
            release.set()
            await asyncio.gather(publish_task, return_exceptions=True)
        await publish_task
    assert completed == ["sent"]


@pytest.mark.asyncio
async def test_durable_mfa_dispatch_reports_late_transport_failure_without_pii(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def failing_send(**_kwargs: str) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test SMTP sender was not released")
        raise OSError("recipient user@example.test, code 123456")

    monkeypatch.setattr(SmtpMfaEmailSender, "_send_sync", staticmethod(failing_send))
    sender = SmtpMfaEmailSender()
    event = events.MfaEmailDeliveryRequested()
    bus = events.EventBus()

    async def handler(_event: events.DomainEvent) -> None:
        await sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code",
            html="<p>code</p>",
            message_id="<stable@example.test>",
        )

    async def pending_wait(
        tasks: set[asyncio.Task[object]], *, timeout: float
    ) -> tuple[set[asyncio.Task[object]], set[asyncio.Task[object]]]:
        del timeout
        assert await asyncio.to_thread(started.wait, 2)
        return set(), tasks

    bus.subscribe(event.event_type, handler)
    with patch.object(events.asyncio, "wait", side_effect=pending_wait):
        publish_task = asyncio.create_task(bus.publish(event, durable=True))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            await asyncio.sleep(0)
            assert not publish_task.done()
        finally:
            release.set()
            await asyncio.gather(publish_task, return_exceptions=True)
        with pytest.raises(
            RuntimeError, match="Durable event handler failed"
        ) as caught:
            await publish_task
    assert caught.value.__cause__ is None
    assert "user@example.test" not in str(caught.value)
    assert "123456" not in str(caught.value)
    assert "user@example.test" not in caplog.text
    assert "123456" not in caplog.text
