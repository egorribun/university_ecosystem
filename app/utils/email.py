import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from app.core.config import settings
from app.core.localization import resolve_locale, translate
from app.core.logging import _redact_pii, get_logger, is_logger_enabled

logger = get_logger(__name__)


def _log_event(
    level: int,
    message: str,
    *,
    extra: dict[str, object] | None = None,
    exc_info: (
        bool | BaseException | tuple[type[BaseException], BaseException, Any] | None
    ) = None,
) -> None:
    """Emit a log record even if the module logger is disabled upstream."""

    # Keep the ``LogRecord.msg`` value as the stable event name.  Passing an
    # event through ``structlog.BoundLogger.log`` turns the message into an
    # event dictionary before ``ProcessorFormatter`` sees it, which makes
    # standard-library consumers (including ``caplog`` and log shippers) lose
    # the canonical event name.  Use the stdlib bridge directly while running
    # the same redaction processor first so fields remain structured and no
    # email address or credential can leak through ``record.__dict__``.
    event: dict[str, Any] = {"event": message, **(extra or {})}
    _redact_pii(logger, "log", event)
    redacted_extra = {key: value for key, value in event.items() if key != "event"}

    try:
        logger_disabled = logger.disabled
    except AttributeError:
        logger_disabled = False
    if is_logger_enabled(logger, level) and not logger_disabled:
        target = logging.getLogger(__name__)
    else:
        target = logging.getLogger()
    target.log(
        level,
        message,
        extra=redacted_extra,
        exc_info=exc_info,
        stacklevel=3,
    )


RESET_TOKEN_EXPIRY_MINUTES = 45


def build_reset_email_content(
    link: str, full_name: str = "", *, locale: str | None = None
) -> tuple[str, str, str]:
    resolved_locale = resolve_locale(locale=locale)
    name_suffix = f", {full_name}" if full_name else ""
    subject = translate("email.reset.subject", locale=resolved_locale)
    heading = translate("email.reset.heading", locale=resolved_locale)
    greeting = translate(
        "email.reset.greeting", locale=resolved_locale, name=name_suffix
    )
    instructions = translate(
        "email.reset.instructions",
        locale=resolved_locale,
        minutes=RESET_TOKEN_EXPIRY_MINUTES,
    )
    button = translate("email.reset.button", locale=resolved_locale)
    ignore = translate("email.reset.ignore", locale=resolved_locale)
    button_style = (
        "display:inline-block;padding:10px 16px;background:#1d5fff;"
        "color:#fff;border-radius:8px;text-decoration:none"
    )
    html = (
        f'<div style="font-family:Inter,Arial,sans-serif">\n'
        f"  <h2>{heading}</h2>\n"
        f"  <p>{greeting}</p>\n"
        f"  <p>{instructions}</p>\n"
        f'  <p><a href="{link}" style="{button_style}">{button}</a></p>\n'
        f"  <p>{ignore}</p>\n"
        "</div>\n"
    )
    plain = translate(
        "email.reset.plain",
        locale=resolved_locale,
        link=link,
        minutes=RESET_TOKEN_EXPIRY_MINUTES,
    )
    return subject, plain, html


def _redact_sensitive_query(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return "[redacted]"
    redacted_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in {"token", "code"}:
            redacted_items.append((key, "***redacted***"))
        else:
            redacted_items.append((key, value))
    sanitized_query = urlencode(redacted_items, doseq=True)
    sanitized = parts._replace(query=sanitized_query)
    result = urlunsplit(sanitized)
    return result or "[redacted]"


def send_reset_email(
    to_email: str, link: str, full_name: str = "", *, locale: str | None = None
) -> None:
    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    mail_from = settings.mail_from or "no-reply@example.com"
    security = (
        settings.smtp_security or ("starttls" if settings.smtp_starttls else "none")
    ).lower()

    msg = EmailMessage()
    subject, plain, html = build_reset_email_content(link, full_name, locale=locale)
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        if user and security == "none" and not settings.is_development:
            _log_event(
                logging.ERROR,
                "password.reset_email.insecure_smtp",
                extra={
                    "email": to_email,
                    "smtp_security": security,
                    "environment": settings.environment,
                },
            )
            return
        if not host or not port:
            safe_link = _redact_sensitive_query(link)
            _log_event(
                logging.WARNING,
                "password.reset_email.fallback",
                extra={"email": to_email, "link": safe_link},
            )
            return

        context = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        elif security == "starttls":
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except (
        OSError,
        smtplib.SMTPException,
    ):  # RZ-25-01 + RZ-22-01: narrowed — SMTP/network errors
        safe_link = _redact_sensitive_query(link)
        _log_event(
            logging.ERROR,
            "password.reset_email.error",
            extra={"email": to_email, "link": safe_link},
            exc_info=True,
        )


def build_lockout_email_content(
    full_name: str = "", *, locale: str | None = None
) -> tuple[str, str, str]:
    resolved_locale = resolve_locale(locale=locale)
    name_suffix = f", {full_name}" if full_name else ""
    subject = translate("email.lockout.subject", locale=resolved_locale)
    heading = translate("email.lockout.heading", locale=resolved_locale)
    greeting = translate(
        "email.lockout.greeting", locale=resolved_locale, name=name_suffix
    )
    body = translate("email.lockout.body", locale=resolved_locale)
    action = translate("email.lockout.action", locale=resolved_locale)

    html = (
        f'<div style="font-family:Inter,Arial,sans-serif">\n'
        f"  <h2>{heading}</h2>\n"
        f"  <p>{greeting}</p>\n"
        f"  <p>{body}</p>\n"
        f"  <p>{action}</p>\n"
        f"</div>\n"
    )
    plain = translate(
        "email.lockout.plain",
        locale=resolved_locale,
    )
    return subject, plain, html


def send_lockout_email(
    to_email: str, full_name: str = "", *, locale: str | None = None
) -> None:
    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    mail_from = settings.mail_from or "no-reply@example.com"
    security = (
        settings.smtp_security or ("starttls" if settings.smtp_starttls else "none")
    ).lower()

    msg = EmailMessage()
    subject, plain, html = build_lockout_email_content(full_name, locale=locale)
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        if user and security == "none" and not settings.is_development:
            _log_event(
                logging.ERROR,
                "auth.lockout_email.insecure_smtp",
                extra={
                    "email": to_email,
                    "smtp_security": security,
                    "environment": settings.environment,
                },
            )
            return
        if not host or not port:
            _log_event(
                logging.WARNING,
                "auth.lockout_email.fallback",
                extra={"email": to_email},
            )
            return

        context = ssl.create_default_context()
        if security == "ssl":
            with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        elif security == "starttls":
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except (
        OSError,
        smtplib.SMTPException,
    ):  # RZ-25-01 + RZ-22-01: narrowed — SMTP/network errors
        _log_event(
            logging.ERROR,
            "auth.lockout_email.error",
            extra={"email": to_email},
            exc_info=True,
        )
