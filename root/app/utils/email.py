import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


logger = logging.getLogger(__name__)


def _build_html(link: str, full_name: str) -> str:
    name = f", {full_name}" if full_name else ""
    return (
        "<div style=\"font-family:Inter,Arial,sans-serif\">"
        "<h2>Сброс пароля</h2>"
        f"<p>Здравствуйте{name}!</p>"
        "<p>Вы запросили сброс пароля в Экосистеме ГУУ. Ссылка действует 45 минут.</p>"
        f"<p><a href=\"{link}\" style=\"display:inline-block;padding:10px 16px;"
        "background:#1d5fff;color:#fff;border-radius:8px;text-decoration:none\">"
        "Сбросить пароль</a></p>"
        "<p>Если вы не запрашивали сброс, проигнорируйте это письмо.</p>"
        "</div>"
    )


def send_reset_email(to_email: str, link: str, full_name: str = "") -> None:
    host = settings.smtp_host or ""
    port = int(settings.smtp_port or 0)
    user = settings.smtp_user or ""
    password = settings.smtp_password or ""
    starttls = bool(settings.smtp_starttls)
    mail_from = settings.mail_from or "no-reply@example.com"

    if not host or not port:
        logger.warning("SMTP server is not configured for password reset emails")
        return

    msg = EmailMessage()
    msg["Subject"] = "Сброс пароля — Экосистема ГУУ"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(f"Ссылка для сброса пароля: {link}\nОна действует 45 минут.")
    msg.add_alternative(_build_html(link, full_name), subtype="html")

    context = ssl.create_default_context()

    try:
        if starttls:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
    except Exception as exc:
        logger.error(
            "Failed to send password reset email", extra={"recipient": to_email}, exc_info=exc
        )
