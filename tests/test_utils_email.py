from email.message import EmailMessage

import pytest

from app.utils import email as email_utils


@pytest.fixture(autouse=True)
def reset_email_settings(monkeypatch):
    """Reset settings that the email helper relies on for each test."""
    monkeypatch.setattr(email_utils.settings, "smtp_host", "")
    monkeypatch.setattr(email_utils.settings, "smtp_port", 0)
    monkeypatch.setattr(email_utils.settings, "smtp_user", "")
    monkeypatch.setattr(email_utils.settings, "smtp_password", "")
    monkeypatch.setattr(email_utils.settings, "smtp_security", "none")
    monkeypatch.setattr(email_utils.settings, "smtp_starttls", False)
    monkeypatch.setattr(email_utils.settings, "mail_from", "no-reply@example.com")
    yield


def test_send_reset_email_logs_fallback_when_missing_server(monkeypatch):
    monkeypatch.setattr(
        email_utils,
        "build_reset_email_content",
        lambda *args, **kwargs: ("Subject", "Plain", "<p>html</p>"),
    )

    log_calls: list[tuple[int, str]] = []

    def tracking_log_event(level, message, **kwargs):
        log_calls.append((level, message))

    monkeypatch.setattr(email_utils, "_log_event", tracking_log_event)

    email_utils.send_reset_email(
        "student@example.com",
        "https://example.com/reset?token=super-secret",
        "Student Name",
    )

    messages = [msg for _, msg in log_calls]
    assert "password.reset_email.fallback" in messages


def test_send_reset_email_uses_starttls(monkeypatch):
    sent_messages: list[EmailMessage] = []
    calls: list[str] = []

    class DummySMTP:
        def __init__(self, host: str, port: int, timeout: int = 0):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, *, context):
            assert context is not None
            calls.append("starttls")

        def login(self, user, password):
            calls.append("login")
            assert user == "smtp-user"
            assert password == "smtp-pass"

        def send_message(self, msg):
            calls.append("send_message")
            sent_messages.append(msg)

    monkeypatch.setattr(email_utils.smtplib, "SMTP", DummySMTP)
    monkeypatch.setattr(
        email_utils,
        "build_reset_email_content",
        lambda *args, **kwargs: ("Subject", "Plain", "<p>html</p>"),
    )

    monkeypatch.setattr(email_utils.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_utils.settings, "smtp_port", 587)
    monkeypatch.setattr(email_utils.settings, "smtp_user", "smtp-user")
    monkeypatch.setattr(email_utils.settings, "smtp_password", "smtp-pass")
    monkeypatch.setattr(email_utils.settings, "smtp_security", "starttls")

    email_utils.send_reset_email(
        "student@example.com",
        "https://example.com/reset?token=super-secret",
        "Student Name",
    )

    assert sent_messages, "Expected send_message to be invoked"
    msg = sent_messages[0]
    assert isinstance(msg, EmailMessage)
    assert msg["To"] == "student@example.com"
    assert msg["Subject"] == "Subject"
    assert "Plain" in msg.get_body(preferencelist=("plain",)).get_content()
    assert "starttls" in calls
    assert "send_message" in calls


def test_send_reset_email_insecure_smtp_error(monkeypatch):
    log_calls = []

    def tracking_log_event(level, message, **kwargs):
        log_calls.append((level, message))

    monkeypatch.setattr(email_utils, "_log_event", tracking_log_event)

    monkeypatch.setattr(email_utils.settings, "smtp_user", "smtp-user")
    monkeypatch.setattr(email_utils.settings, "smtp_security", "none")
    monkeypatch.setattr(email_utils.settings, "is_development", False)

    email_utils.send_reset_email(
        "student@example.com",
        "https://example.com/reset?token=super-secret",
        "Student Name",
    )
    messages = [msg for _, msg in log_calls]
    assert "password.reset_email.insecure_smtp" in messages


def test_redact_sensitive_query():
    # 1. Successful redaction of token and code
    url = "http://example.com?token=secret123&code=mycode&other=public"
    redacted = email_utils._redact_sensitive_query(url)
    assert "token=%2A%2A%2Aredacted%2A%2A%2A" in redacted
    assert "code=%2A%2A%2Aredacted%2A%2A%2A" in redacted
    assert "other=public" in redacted

    # 2. ValueError raising in urlsplit (covers line 80-81)
    from unittest.mock import patch

    with patch("urllib.parse.urlsplit", side_effect=ValueError("bad")):
        assert email_utils._redact_sensitive_query("http://example.com") == "[redacted]"
