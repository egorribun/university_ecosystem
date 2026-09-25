"""The MFA SMTP transport must stop before the outbox lease can be reclaimed."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.mfa.email_otp import SmtpMfaEmailSender
from app.core import events


def _smtp_settings(*, port: int = 1025) -> SimpleNamespace:
    return SimpleNamespace(
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_security="none",
        smtp_starttls=False,
        smtp_user="",
        smtp_password="",
        smtp_mfa_total_timeout_seconds=60,
        mail_from="no-reply@example.test",
    )


def _client(send_message: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        connect=AsyncMock(),
        login=AsyncMock(),
        send_message=send_message,
        close=MagicMock(),
        transport=SimpleNamespace(abort=MagicMock()),
    )


async def _send(sender: SmtpMfaEmailSender) -> None:
    await sender.send(
        to_email="user@example.test",
        subject="Verification",
        plain="code 123456",
        html="<p>code 123456</p>",
        message_id="<stable@example.test>",
    )


@pytest.mark.asyncio
async def test_smtp_total_deadline_closes_a_drip_fed_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A peer sending partial replies cannot outlive the delivery lease."""
    connected = asyncio.Event()
    disconnected = asyncio.Event()

    async def drip_greeting(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        connected.set()
        try:
            writer.write(b"220 ")
            await writer.drain()
            while not writer.is_closing():
                writer.write(b"x")
                await writer.drain()
                try:
                    await asyncio.wait_for(reader.read(1), timeout=0.025)
                except TimeoutError:
                    continue
                break
        finally:
            disconnected.set()
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(drip_greeting, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr("app.core.config.settings", _smtp_settings(port=port))
        with pytest.raises(OSError, match=r"^SMTP unavailable$"):
            await _send(SmtpMfaEmailSender(total_timeout_seconds=0.15))
        assert connected.is_set()
        await asyncio.wait_for(disconnected.wait(), timeout=1)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_lost_data_ack_retries_with_the_same_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first peer may accept DATA although its 250 reply is lost."""
    accepted: list[bytes] = []

    async def smtp_peer(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(b"220 test SMTP\r\n")
        await writer.drain()
        try:
            while line := await reader.readline():
                command = line.upper()
                if command.startswith(b"EHLO"):
                    writer.write(b"250-test\r\n250 8BITMIME\r\n")
                elif command.startswith(b"MAIL") or command.startswith(b"RCPT"):
                    writer.write(b"250 OK\r\n")
                elif command.startswith(b"DATA"):
                    writer.write(b"354 Send data\r\n")
                    await writer.drain()
                    body = bytearray()
                    while chunk := await reader.readline():
                        if chunk == b".\r\n":
                            break
                        body.extend(chunk)
                    accepted.append(bytes(body))
                    if len(accepted) == 1:
                        await reader.read()
                        break
                    writer.write(b"250 Accepted\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(smtp_peer, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr("app.core.config.settings", _smtp_settings(port=port))
        sender = SmtpMfaEmailSender(total_timeout_seconds=0.5)
        with pytest.raises(OSError, match=r"^SMTP unavailable$"):
            await _send(sender)
        await _send(sender)
        assert len(accepted) == 2
        for body in accepted:
            assert b"Message-ID: <stable@example.test>" in body
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_smtp_cancellation_aborts_transport_and_cannot_send_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    resumed = asyncio.Event()

    async def blocked_send(_message: object) -> None:
        started.set()
        await resumed.wait()

    client = _client(AsyncMock(side_effect=blocked_send))
    monkeypatch.setattr("app.core.config.settings", _smtp_settings())
    with patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client):
        task = asyncio.create_task(_send(SmtpMfaEmailSender()))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        resumed.set()
        await asyncio.sleep(0)
    client.transport.abort.assert_called_once()
    client.close.assert_called_once()
    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_smtp_repeated_cancellation_does_not_detach_a_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def blocked_send(_message: object) -> None:
        started.set()
        await asyncio.Event().wait()

    client = _client(AsyncMock(side_effect=blocked_send))
    monkeypatch.setattr("app.core.config.settings", _smtp_settings())
    with patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client):
        task = asyncio.create_task(_send(SmtpMfaEmailSender()))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    client.transport.abort.assert_called_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_smtp_failure_redacts_provider_content_and_closes_socket(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(AsyncMock(side_effect=OSError("user@example.test 123456")))
    monkeypatch.setattr("app.core.config.settings", _smtp_settings())
    with (
        patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client),
        pytest.raises(OSError, match=r"^SMTP unavailable$") as caught,
    ):
        await _send(SmtpMfaEmailSender())
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    client.transport.abort.assert_called_once()
    client.close.assert_called_once()
    assert "user@example.test" not in caplog.text
    assert "123456" not in caplog.text


@pytest.mark.asyncio
async def test_durable_mfa_dispatch_waits_for_async_smtp_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    completed: list[str] = []

    async def blocked_send(_message: object) -> None:
        started.set()
        await release.wait()

    client = _client(AsyncMock(side_effect=blocked_send))
    monkeypatch.setattr("app.core.config.settings", _smtp_settings())
    sender = SmtpMfaEmailSender()
    event = events.MfaEmailDeliveryRequested()
    bus = events.EventBus()

    async def handler(_event: events.DomainEvent) -> None:
        await _send(sender)
        completed.append("sent")

    bus.subscribe(event.event_type, handler)
    with patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client):
        publish_task = asyncio.create_task(bus.publish(event, durable=True))
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not publish_task.done()
        release.set()
        await publish_task
    assert completed == ["sent"]
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_durable_mfa_dispatch_failure_is_pii_free(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(AsyncMock(side_effect=OSError("user@example.test 123456")))
    monkeypatch.setattr("app.core.config.settings", _smtp_settings())
    event = events.MfaEmailDeliveryRequested()
    bus = events.EventBus()

    async def handler(_event: events.DomainEvent) -> None:
        await _send(SmtpMfaEmailSender())

    bus.subscribe(event.event_type, handler)
    with (
        patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client),
        pytest.raises(RuntimeError, match="Durable event handler failed") as caught,
    ):
        await bus.publish(event, durable=True)
    assert caught.value.__cause__ is None
    assert "user@example.test" not in caplog.text
    assert "123456" not in caplog.text
