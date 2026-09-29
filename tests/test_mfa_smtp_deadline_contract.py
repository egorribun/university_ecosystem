"""The configured total deadline, not the client's own timeout, bounds a send."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.mfa.email_otp import SmtpMfaEmailSender


async def test_hung_connect_is_abandoned_at_the_total_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def hang() -> None:
        await asyncio.Event().wait()

    client = SimpleNamespace(
        connect=AsyncMock(side_effect=hang),
        login=AsyncMock(),
        send_message=AsyncMock(),
        close=MagicMock(),
        transport=SimpleNamespace(abort=MagicMock()),
    )
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_security="none",
            smtp_starttls=False,
            smtp_user="",
            smtp_password="",
            smtp_mfa_total_timeout_seconds=60,
            mail_from="no-reply@example.test",
        ),
    )
    sender = SmtpMfaEmailSender(total_timeout_seconds=0.05)

    with patch("app.auth.mfa.email_otp.aiosmtplib.SMTP", return_value=client):
        with pytest.raises(OSError, match=r"^SMTP unavailable$"):
            await asyncio.wait_for(
                sender.send(
                    to_email="user@example.test",
                    subject="Verification",
                    plain="code 123456",
                    html="<p>code 123456</p>",
                    message_id="<stable@example.test>",
                ),
                timeout=5,
            )

    client.send_message.assert_not_awaited()
    client.transport.abort.assert_called_once_with()
    client.close.assert_called_once_with()
