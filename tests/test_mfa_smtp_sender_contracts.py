"""Configuration and message contracts of the MFA SMTP sender."""

from __future__ import annotations

import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.mfa.email_otp import SmtpMfaEmailSender


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
        "smtp_security": "none",
        "smtp_starttls": False,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_mfa_total_timeout_seconds": 60,
        "mail_from": "no-reply@example.test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client() -> SimpleNamespace:
    return SimpleNamespace(
        connect=AsyncMock(),
        login=AsyncMock(),
        send_message=AsyncMock(),
        close=MagicMock(),
        transport=SimpleNamespace(abort=MagicMock()),
    )


async def _send(sender: SmtpMfaEmailSender, monkeypatch, settings, client) -> MagicMock:
    monkeypatch.setattr("app.core.config.settings", settings)
    with patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client) as smtp:
        await sender.send(
            to_email="user@example.test",
            subject="Verification",
            plain="code 123456",
            html="<p>code 123456</p>",
            message_id="<stable@example.test>",
        )
    return smtp


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0.001, 90])
async def test_accepts_total_deadlines_inside_the_lease(
    monkeypatch, timeout: float
) -> None:
    client = _client()

    await _send(
        SmtpMfaEmailSender(total_timeout_seconds=timeout),
        monkeypatch,
        _settings(),
        client,
    )

    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, 90.5, -1])
async def test_rejects_total_deadlines_outside_the_lease(
    monkeypatch, timeout: float
) -> None:
    client = _client()

    with pytest.raises(OSError, match=r"^SMTP unavailable$"):
        await _send(
            SmtpMfaEmailSender(total_timeout_seconds=timeout),
            monkeypatch,
            _settings(),
            client,
        )

    client.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_explicit_sender_deadline_overrides_the_global_setting(
    monkeypatch,
) -> None:
    client = _client()

    await _send(
        SmtpMfaEmailSender(total_timeout_seconds=30),
        monkeypatch,
        _settings(smtp_mfa_total_timeout_seconds=0),
        client,
    )

    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [{"smtp_host": ""}, {"smtp_port": 0}, {"smtp_host": "", "smtp_port": 0}],
    ids=["no-host", "no-port", "neither"],
)
async def test_requires_both_host_and_port(monkeypatch, overrides) -> None:
    client = _client()

    with pytest.raises(OSError, match=r"^SMTP unavailable$"):
        await _send(SmtpMfaEmailSender(), monkeypatch, _settings(**overrides), client)

    client.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_sends_the_composed_message_and_an_empty_default_password(
    monkeypatch,
) -> None:
    client = _client()

    await _send(
        SmtpMfaEmailSender(),
        monkeypatch,
        _settings(smtp_user="mailer", smtp_password=None),
        client,
    )

    client.login.assert_awaited_once_with("mailer", "")
    (message,), _ = client.send_message.await_args
    assert message["To"] == "user@example.test"
    assert message["Subject"] == "Verification"
    assert message["Message-ID"] == "<stable@example.test>"
    assert message["From"] == "no-reply@example.test"
    client.transport.abort.assert_not_called()
    client.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("security", "has_tls_context"),
    [("none", False), ("starttls", True), ("ssl", True)],
)
async def test_tls_context_follows_the_security_mode(
    monkeypatch, security: str, has_tls_context: bool
) -> None:
    smtp = await _send(
        SmtpMfaEmailSender(), monkeypatch, _settings(smtp_security=security), _client()
    )

    tls_context = smtp.call_args.kwargs["tls_context"]
    assert isinstance(tls_context, ssl.SSLContext) is has_tls_context
    assert smtp.call_args.kwargs["use_tls"] is (security == "ssl")
    assert smtp.call_args.kwargs["start_tls"] is (security == "starttls")


@pytest.mark.asyncio
async def test_a_failed_send_aborts_queued_bytes_behind_a_fixed_error(
    monkeypatch,
) -> None:
    client = _client()
    client.send_message.side_effect = OSError("550 user@example.test rejected")

    with pytest.raises(OSError, match=r"^SMTP unavailable$") as error:
        await _send(SmtpMfaEmailSender(), monkeypatch, _settings(), client)

    assert error.value.__cause__ is None
    client.transport.abort.assert_called_once()
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_an_unexpected_error_still_aborts_and_propagates_unchanged(
    monkeypatch,
) -> None:
    client = _client()
    failure = LookupError("bug")
    client.send_message.side_effect = failure

    with pytest.raises(LookupError) as error:
        await _send(SmtpMfaEmailSender(), monkeypatch, _settings(), client)

    assert error.value is failure
    client.transport.abort.assert_called_once()


@pytest.mark.asyncio
async def test_a_failure_before_a_transport_exists_does_not_abort(monkeypatch) -> None:
    client = _client()
    client.transport = None
    client.connect.side_effect = OSError("refused")

    with pytest.raises(OSError, match=r"^SMTP unavailable$"):
        await _send(SmtpMfaEmailSender(), monkeypatch, _settings(), client)

    client.close.assert_called_once()
