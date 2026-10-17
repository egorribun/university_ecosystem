from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
from email.message import EmailMessage
from typing import cast

import aiosmtplib

from app.core.nats_broker import broker
from app.utils import email as email_utils


async def _deliver_email_message(
    *,
    to_email: str,
    message: EmailMessage,
    insecure_event: str,
    fallback_event: str,
    error_event: str,
    fallback_fields: dict[str, object] | None = None,
    error_fields: dict[str, object] | None = None,
) -> None:
    """Send email without leaving blocking SMTP work past task cancellation."""
    from app.core.config import settings

    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    security = (
        settings.smtp_security or ("starttls" if settings.smtp_starttls else "none")
    ).lower()

    if user and security == "none" and not settings.is_development:
        email_utils._log_event(
            logging.ERROR,
            insecure_event,
            extra={
                "email": to_email,
                "smtp_security": security,
                "environment": settings.environment,
            },
        )
        return

    if not host or not port:
        extra: dict[str, object] = {"email": to_email}
        if fallback_fields:
            extra.update(fallback_fields)
            if "link" in extra:
                extra["link"] = email_utils._redact_sensitive_query(str(extra["link"]))
        email_utils._log_event(logging.WARNING, fallback_event, extra=extra)
        return

    client = aiosmtplib.SMTP(
        hostname=host,
        port=port,
        timeout=10,
        use_tls=security == "ssl",
        start_tls=security == "starttls",
        tls_context=ssl.create_default_context() if security != "none" else None,
    )
    try:
        try:
            await client.connect()
            if user:
                await client.login(user, password)
            await client.send_message(message)
        except BaseException:  # RZ-22-01-JUSTIFIED: abort queued SMTP bytes.
            # Abort is cleanup and must not replace the delivery error/cancellation.
            if client.transport is not None:
                with contextlib.suppress(Exception):
                    cast(asyncio.Transport, client.transport).abort()
            # Preserve cancellation/SMTP failure if synchronous close also fails.
            with contextlib.suppress(Exception):
                client.close()
            raise
        else:
            client.close()
    except (OSError, aiosmtplib.SMTPException):
        extra = {"email": to_email}
        if error_fields:
            extra.update(error_fields)
            if "link" in extra:
                extra["link"] = email_utils._redact_sensitive_query(str(extra["link"]))
        email_utils._log_event(logging.ERROR, error_event, extra=extra, exc_info=True)


@broker.task()
async def send_auth_email(
    to_email: str,
    link: str,
    full_name: str = "",
    locale: str | None = None,
) -> None:
    """Distributed task for sending authentication-related emails."""
    from app.core.config import settings

    message = EmailMessage()
    subject, plain, html = email_utils.build_reset_email_content(
        link, full_name, locale=locale
    )
    message["Subject"] = subject
    message["From"] = settings.mail_from or "no-reply@example.com"
    message["To"] = to_email
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    await _deliver_email_message(
        to_email=to_email,
        message=message,
        insecure_event="password.reset_email.insecure_smtp",
        fallback_event="password.reset_email.fallback",
        error_event="password.reset_email.error",
        fallback_fields={"link": link},
        error_fields={"link": link},
    )


@broker.task()
async def send_lockout_alert(
    to_email: str,
    full_name: str = "",
    locale: str | None = None,
) -> None:
    """Distributed task for sending lockout alert emails."""
    from app.core.config import settings

    message = EmailMessage()
    subject, plain, html = email_utils.build_lockout_email_content(
        full_name, locale=locale
    )
    message["Subject"] = subject
    message["From"] = settings.mail_from or "no-reply@example.com"
    message["To"] = to_email
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    await _deliver_email_message(
        to_email=to_email,
        message=message,
        insecure_event="auth.lockout_email.insecure_smtp",
        fallback_event="auth.lockout_email.fallback",
        error_event="auth.lockout_email.error",
    )
