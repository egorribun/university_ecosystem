import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings
from app.localization import translate
from app.localization import resolve_locale

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
    html = f"""
  <div style="font-family:Inter,Arial,sans-serif">
    <h2>{heading}</h2>
    <p>{greeting}</p>
    <p>{instructions}</p>
    <p><a href="{link}" style="display:inline-block;padding:10px 16px;background:#1d5fff;color:#fff;border-radius:8px;text-decoration:none">{button}</a></p>
    <p>{ignore}</p>
  </div>
  """
    plain = translate(
        "email.reset.plain",
        locale=resolved_locale,
        link=link,
        minutes=RESET_TOKEN_EXPIRY_MINUTES,
    )
    return subject, plain, html


def send_reset_email(
    to_email: str, link: str, full_name: str = "", *, locale: str | None = None
) -> None:
    host = settings.smtp_host
    port = settings.smtp_port
    user = settings.smtp_user
    password = settings.smtp_password
    starttls = settings.smtp_starttls
    mail_from = settings.mail_from

    msg = EmailMessage()
    subject, plain, html = build_reset_email_content(
        link, full_name, locale=locale
    )
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if starttls:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=context)
            if user:
                s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(host, port, context=context) as s:
            if user:
                s.login(user, password)
            s.send_message(msg)
