"""Tests for email utility module.

Coverage targets:
- build_reset_email_content: content generation, localization
- _redact_sensitive_query: redaction logic
- send_reset_email: SMTP paths (no host, SSL, STARTTLS, normal)
"""

import logging
from unittest.mock import patch

from app.utils.email import (
    _redact_sensitive_query,
    build_reset_email_content,
    send_reset_email,
)

# ============================================================
# build_reset_email_content tests
# ============================================================


def test_build_reset_email_content_default():
    """Test generating reset email content with default locale."""
    link = "https://example.com/reset?token=123"
    subject, plain, html = build_reset_email_content(link, "John Doe")

    # John Doe is used in HTML greeting but not necessarily in PLAIN
    # (depending on translation)
    assert "John Doe" in html
    assert link in plain
    assert link in html
    assert isinstance(subject, str)
    assert len(subject) > 0


def test_build_reset_email_content_no_name():
    """Test generating reset email content without a name."""
    link = "https://example.com/reset?token=123"
    _subject, plain, html = build_reset_email_content(link)

    # Check that name placeholder isn't leaking raw (like ", ")
    # if translation doesn't handle it
    # We just want to ensure it doesn't crash
    assert link in plain
    assert link in html


# ============================================================
# _redact_sensitive_query tests
# ============================================================


def test_redact_sensitive_query_redact():
    """Test redacting sensitive query parameters."""
    url = "https://example.com/reset?token=secret123&code=abcd&other=visible"
    redacted = _redact_sensitive_query(url)

    # The string ***redacted*** becomes URL encoded
    expected_token = "token=%2A%2A%2Aredacted%2A%2A%2A"
    expected_code = "code=%2A%2A%2Aredacted%2A%2A%2A"

    assert expected_token in redacted
    assert expected_code in redacted
    assert "other=visible" in redacted


def test_redact_sensitive_query_invalid():
    """Test handles invalid URL."""
    assert _redact_sensitive_query("not-a-url") == "not-a-url"


# ============================================================
# send_reset_email tests
# ============================================================


@patch("app.utils.email.settings")
def test_send_reset_email_no_host(mock_settings, caplog):
    """Test send_reset_email with no SMTP host configured (log fallback)."""
    mock_settings.smtp_host = None
    mock_settings.smtp_port = None
    mock_settings.is_development = False

    with caplog.at_level(logging.WARNING, logger=""):
        send_reset_email("user@example.com", "https://example.com/reset?token=secret")

    assert any("password.reset_email.fallback" in r.msg for r in caplog.records)


@patch("app.utils.email.settings")
@patch("smtplib.SMTP_SSL")
def test_send_reset_email_ssl(mock_smtp_ssl, mock_settings):
    """Test send_reset_email with SSL."""
    mock_settings.smtp_host = "smtp.gmail.com"
    mock_settings.smtp_port = 465
    mock_settings.smtp_security = "ssl"
    mock_settings.smtp_user = "user"
    mock_settings.smtp_password = "password"

    instance = mock_smtp_ssl.return_value.__enter__.return_value

    send_reset_email("user@example.com", "https://example.com/reset")

    instance.login.assert_called_once_with("user", "password")
    instance.send_message.assert_called_once()


@patch("app.utils.email.settings")
@patch("smtplib.SMTP")
def test_send_reset_email_starttls(mock_smtp, mock_settings):
    """Test send_reset_email with STARTTLS."""
    mock_settings.smtp_host = "smtp.gmail.com"
    mock_settings.smtp_port = 587
    mock_settings.smtp_security = "starttls"
    mock_settings.smtp_user = "user"
    mock_settings.smtp_password = "password"

    instance = mock_smtp.return_value.__enter__.return_value

    send_reset_email("user@example.com", "https://example.com/reset")

    instance.starttls.assert_called_once()
    instance.login.assert_called_once()
    instance.send_message.assert_called_once()


@patch("app.utils.email.settings")
@patch("smtplib.SMTP")
def test_send_reset_email_plain(mock_smtp, mock_settings):
    """Test send_reset_email without security."""
    mock_settings.smtp_host = "localhost"
    mock_settings.smtp_port = 25
    mock_settings.smtp_security = "none"
    mock_settings.smtp_user = None

    instance = mock_smtp.return_value.__enter__.return_value

    send_reset_email("user@example.com", "https://example.com/reset")

    instance.login.assert_not_called()
    instance.send_message.assert_called_once()


@patch("app.utils.email.settings")
@patch("smtplib.SMTP")
def test_send_reset_email_error(mock_smtp, mock_settings, caplog):
    """Test exception handling in send_reset_email."""
    mock_settings.smtp_host = "localhost"
    mock_settings.smtp_port = 25
    mock_settings.smtp_security = "none"
    mock_settings.smtp_user = None
    mock_settings.is_development = False

    # Use OSError which is caught by the except clause (not bare Exception)
    mock_smtp.side_effect = OSError("SMTP Offline")

    with caplog.at_level(logging.ERROR, logger=""):
        send_reset_email("user@example.com", "https://example.com/reset")

    assert any("password.reset_email.error" in r.msg for r in caplog.records)
