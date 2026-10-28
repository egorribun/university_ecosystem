from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import json
import logging
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Literal, cast

import aiosmtplib
from cryptography.fernet import Fernet

from app.core.nats_broker import broker
from app.utils import email as email_utils

_AUTH_EMAIL_KEY_CONTEXT = b"university-ecosystem:auth-email-delivery:v1"


def _auth_email_cipher(secret: str) -> Fernet:
    # The reset-token HMAC key is already required outside development.
    # Derive a separate encryption key rather than using that key directly.
    key = hmac.digest(secret.encode("utf-8"), _AUTH_EMAIL_KEY_CONTEXT, "sha256")
    return Fernet(base64.urlsafe_b64encode(key))


def seal_auth_email_link(link: str, expires_at: datetime, secret: str) -> str:
    """Protect a queued auth link and its actual database expiry together."""
    envelope = json.dumps({"link": link, "expires_at": expires_at.isoformat()})
    return _auth_email_cipher(secret).encrypt(envelope.encode("utf-8")).decode("ascii")


def _open_auth_email_link(envelope: str, secret: str) -> str:
    data = json.loads(_auth_email_cipher(secret).decrypt(envelope.encode("ascii")))
    expires_at = datetime.fromisoformat(data["expires_at"])
    if expires_at.tzinfo is None:
        raise ValueError("Invalid auth email expiry")
    if expires_at <= datetime.now(UTC):
        raise ValueError("Auth email link expired")
    link = data["link"]
    if not isinstance(link, str):
        raise ValueError("Invalid auth email link")
    return link


async def _deliver_email_message(
    *,
    to_email: str,
    message: EmailMessage,
    insecure_event: str,
    fallback_event: str,
    error_event: str,
    fallback_fields: dict[str, object] | None = None,
    error_fields: dict[str, object] | None = None,
    include_exception_details: bool = True,
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
        email_utils._log_event(
            logging.ERROR, error_event, extra=extra, exc_info=include_exception_details
        )


async def _deliver_auth_email(
    to_email: str,
    link: str,
    full_name: str,
    locale: str | None,
    encrypted_link: bool,
) -> Literal["sent", "failed", "cancelled"]:
    """Keep decrypted data out of traceback frames reported by the worker."""
    try:
        from app.core.config import settings

        if encrypted_link:
            # Import lazily: AuthService itself imports this task.
            from app.services.auth_service import _token_hmac_secret

            link = _open_auth_email_link(link, _token_hmac_secret())
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
            include_exception_details=False,
        )
    except asyncio.CancelledError:
        return "cancelled"
    except Exception:  # RZ-22-01-JUSTIFIED: fail closed without leaking auth links
        return "failed"
    return "sent"


@broker.task()
async def send_auth_email(
    to_email: str,
    link: str,
    full_name: str = "",
    locale: str | None = None,
    *,
    encrypted_link: bool = False,
) -> None:
    """Distributed task for sending authentication-related emails."""
    try:
        outcome = await _deliver_auth_email(
            to_email, link, full_name, locale, encrypted_link
        )
    finally:
        # Observability captures frame locals even when PII defaults are off.
        # Do not leave legacy plaintext or identity fields on this frame.
        to_email = ""
        link = ""
        full_name = ""
        locale = None
    # Raise only after the helper returns: no plaintext frame or chained cause
    # is retained in the traceback that the broker reports to its sinks.
    if outcome == "cancelled":
        raise asyncio.CancelledError
    if outcome == "failed":
        raise RuntimeError("Authentication email delivery failed") from None


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
