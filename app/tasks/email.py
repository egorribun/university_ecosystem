from app.core.tkq import broker
from app.utils.email import send_reset_email


@broker.task
def send_auth_email(
    to_email: str,
    link: str,
    full_name: str = "",
    locale: str | None = None,
) -> None:
    """Distributed task for sending authentication-related emails."""
    send_reset_email(to_email, link, full_name, locale=locale)
