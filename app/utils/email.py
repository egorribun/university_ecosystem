import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from app.core.config import settings
from app.core.localization import resolve_locale, translate

logger = logging.getLogger(__name__)


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

    target = (
        logger
        if logger.isEnabledFor(level) and not logger.disabled
        else logging.getLogger()
    )
    target.log(level, message, extra=extra, exc_info=exc_info, stacklevel=3)


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
    except Exception:
        safe_link = _redact_sensitive_query(link)
        _log_event(
            logging.ERROR,
            "password.reset_email.error",
            extra={"email": to_email, "link": safe_link},
            exc_info=True,
        )
