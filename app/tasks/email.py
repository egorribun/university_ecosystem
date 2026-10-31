from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import inspect
import json
import logging
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Literal, cast

import aiosmtplib
from cryptography.fernet import Fernet

from app.core.nats_broker import broker
from app.utils import email as email_utils

_AUTH_EMAIL_KEY_CONTEXT = b"university-ecosystem:auth-email-delivery:v1"
_AUTH_EMAIL_LEGACY_KIND = "auth-email-legacy-v1"


class AuthEmailPayloadError(ValueError):
    """An auth task cannot be protected without changing its delivery semantics."""

    def __init__(self) -> None:
        super().__init__("Authentication email payload protection failed")


def _auth_email_cipher(secret: str) -> Fernet:
    # The reset-token HMAC key is already required outside development.
    # Derive a separate encryption key rather than using that key directly.
    key = hmac.digest(secret.encode("utf-8"), _AUTH_EMAIL_KEY_CONTEXT, "sha256")
    return Fernet(base64.urlsafe_b64encode(key))


def seal_auth_email_link(link: str, expires_at: datetime, secret: str) -> str:
    """Protect a queued auth link and its actual database expiry together."""
    envelope = json.dumps({"link": link, "expires_at": expires_at.isoformat()})
    return _auth_email_cipher(secret).encrypt(envelope.encode("utf-8")).decode("ascii")


def _read_auth_email_link(
    envelope: str, secret: str
) -> tuple[str, datetime | None, bool | None]:
    """Authenticate the format without imposing delivery-time expiry at storage."""
    data = json.loads(_auth_email_cipher(secret).decrypt(envelope.encode("ascii")))
    if not isinstance(data, dict):
        raise ValueError("Invalid auth email envelope")
    link = data.get("link")
    if not isinstance(link, str):
        raise ValueError("Invalid auth email link")
    if data.get("kind") == _AUTH_EMAIL_LEGACY_KIND:
        if set(data) != {"kind", "link", "encrypted_link_present"}:
            raise ValueError("Invalid legacy auth email envelope")
        flag_present = data["encrypted_link_present"]
        if type(flag_present) is not bool:
            raise ValueError("Invalid legacy auth email marker")
        return link, None, flag_present
    raw_expiry = data.get("expires_at")
    if not isinstance(raw_expiry, str):
        raise ValueError("Invalid auth email expiry")
    expires_at = datetime.fromisoformat(raw_expiry)
    if expires_at.tzinfo is None:
        raise ValueError("Invalid auth email expiry")
    return link, expires_at, None


def _open_auth_email_link(envelope: str, secret: str) -> str:
    link, expires_at, _ = _read_auth_email_link(envelope, secret)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise ValueError("Auth email link expired")
    return link


def prepare_auth_email_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return protected storage/wire data and its original logical hash input."""
    try:
        # Import lazily: AuthService imports this task module.
        from app.services.auth_service import _token_hmac_secret

        if set(payload) != {"args", "kwargs"}:
            raise ValueError("Invalid auth email task payload")
        args = payload["args"]
        kwargs = payload["kwargs"]
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError("Invalid auth email task arguments")
        # Binding enforces required arguments, keyword names, duplicates and the
        # four positional slots without changing defaults or argument placement.
        bound = inspect.signature(send_auth_email).bind(*args, **kwargs)
        link = bound.arguments["link"]
        encrypted_link = bound.arguments.get("encrypted_link", False)
        if not isinstance(link, str) or type(encrypted_link) is not bool:
            raise ValueError("Invalid auth email link or encryption marker")

        safe_args = list(args)
        safe_kwargs = dict(kwargs)
        logical_args = list(args)
        logical_kwargs = dict(kwargs)
        secret = _token_hmac_secret()
        if encrypted_link:
            original_link, _, flag_present = _read_auth_email_link(link, secret)
            if flag_present is not None:
                # Only authenticated legacy metadata can restore the old hash.
                if len(logical_args) >= 2:
                    logical_args[1] = original_link
                else:
                    logical_kwargs["link"] = original_link
                if flag_present:
                    logical_kwargs["encrypted_link"] = False
                else:
                    logical_kwargs.pop("encrypted_link")
            # Native envelopes, including expired ones, retain their exact bytes.
        else:
            legacy = json.dumps(
                {
                    "kind": _AUTH_EMAIL_LEGACY_KIND,
                    "link": link,
                    "encrypted_link_present": "encrypted_link" in kwargs,
                }
            )
            protected_link = (
                _auth_email_cipher(secret)
                .encrypt(legacy.encode("utf-8"))
                .decode("ascii")
            )
            if len(safe_args) >= 2:
                safe_args[1] = protected_link
            else:
                safe_kwargs["link"] = protected_link
            safe_kwargs["encrypted_link"] = True
        return (
            {"args": safe_args, "kwargs": safe_kwargs},
            {"args": logical_args, "kwargs": logical_kwargs},
        )
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed task protection
        raise AuthEmailPayloadError() from None


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
