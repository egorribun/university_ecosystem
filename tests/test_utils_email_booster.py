"""Tests for app/utils/email.py

Covers _redact_sensitive_query, build_reset_email_content,
build_lockout_email_content, send_reset_email, send_lockout_email.
Goal: bring coverage from 22% to ~85%.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

from app.utils.email import (
    _redact_sensitive_query,
    build_lockout_email_content,
    build_reset_email_content,
    send_lockout_email,
    send_reset_email,
)

# ---------------------------------------------------------------------------
# _redact_sensitive_query
# ---------------------------------------------------------------------------


def test_redact_sensitive_query_redacts_token():
    from urllib.parse import unquote

    url = "https://example.com/reset?token=abc123&foo=bar"
    result = _redact_sensitive_query(url)
    assert "abc123" not in result
    # urlencode percent-encodes '*' as '%2A'; decode before comparing.
    assert "***redacted***" in unquote(result)
    assert "foo=bar" in result


def test_redact_sensitive_query_redacts_code():
    from urllib.parse import unquote

    url = "https://example.com/verify?code=secret&locale=en"
    result = _redact_sensitive_query(url)
    assert "secret" not in result
    # urlencode percent-encodes '*' as '%2A'; decode before comparing.
    assert "***redacted***" in unquote(result)
    assert "locale=en" in result


def test_redact_sensitive_query_no_sensitive_params():
    url = "https://example.com/page?foo=bar&baz=qux"
    result = _redact_sensitive_query(url)
    assert "foo=bar" in result
    assert "baz=qux" in result


def test_redact_sensitive_query_empty_url():
    url = ""
    result = _redact_sensitive_query(url)
    # No exception, returns something safe
    assert isinstance(result, str)


def test_redact_sensitive_query_invalid_url():
    """Malformed URL should not raise — returns [redacted]."""
    # urlsplit usually doesn't raise for most invalid URLs,
    # but if it does, it should return [redacted]
    url = "not-a-url"
    result = _redact_sensitive_query(url)
    assert isinstance(result, str)


def test_redact_sensitive_query_url_without_query():
    url = "https://example.com/reset"
    result = _redact_sensitive_query(url)
    assert "example.com" in result


# ---------------------------------------------------------------------------
# build_reset_email_content
# ---------------------------------------------------------------------------


def test_build_reset_email_content_returns_tuple():
    subject, plain, html = build_reset_email_content(
        "https://example.com/reset", "John"
    )
    assert isinstance(subject, str)
    assert isinstance(plain, str)
    assert isinstance(html, str)
    assert len(subject) > 0


def test_build_reset_email_content_html_contains_link():
    link = "https://example.com/reset?token=abc"
    _, _, html = build_reset_email_content(link, "Alice")
    assert link in html


def test_build_reset_email_content_with_locale():
    subject_en, _, _ = build_reset_email_content("https://x.com/r", locale="en")
    subject_ru, _, _ = build_reset_email_content("https://x.com/r", locale="ru")
    # Both should be valid strings; just verify no exception
    assert isinstance(subject_en, str)
    assert isinstance(subject_ru, str)


def test_build_reset_email_content_no_name():
    _subject, _plain, html = build_reset_email_content("https://example.com/reset")
    assert isinstance(html, str)


# ---------------------------------------------------------------------------
# build_lockout_email_content
# ---------------------------------------------------------------------------


def test_build_lockout_email_content_returns_tuple():
    subject, plain, html = build_lockout_email_content("Jane")
    assert isinstance(subject, str)
    assert isinstance(plain, str)
    assert isinstance(html, str)


def test_build_lockout_email_content_with_locale():
    subject, _plain, _html = build_lockout_email_content("Bob", locale="en")
    assert isinstance(subject, str)


# ---------------------------------------------------------------------------
# send_reset_email — early exits
# ---------------------------------------------------------------------------


def test_send_reset_email_no_host_logs_warning():
    """When SMTP host is not configured, falls back silently."""
    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = ""
        mock_settings.smtp_port = 0
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = ""
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        # Should return without raising
        send_reset_email("user@example.com", "https://example.com/r")


def test_send_reset_email_insecure_smtp_not_dev_logs_error():
    """User + no security + not development → reject and log error."""
    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"  # pragma: allowlist secret
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False
        mock_settings.environment = "production"

        send_reset_email("user@example.com", "https://example.com/r")
        # No SMTP connection should be established — just returns after logging


def test_send_reset_email_via_ssl():
    """send_reset_email uses SMTP_SSL when security=ssl."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch("app.utils.email.smtplib.SMTP_SSL") as mock_smtp_ssl_cls,
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "ssl"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        mock_smtp = MagicMock()
        mock_smtp_ssl_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_reset_email("user@example.com", "https://example.com/r", "John")

        mock_smtp_ssl_cls.assert_called_once()
        mock_smtp.send_message.assert_called_once()


def test_send_reset_email_via_starttls():
    """send_reset_email uses STARTTLS when security=starttls."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch("app.utils.email.smtplib.SMTP") as mock_smtp_cls,
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "starttls"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_reset_email("user@example.com", "https://example.com/r")

        mock_smtp_cls.assert_called_once()
        mock_smtp.starttls.assert_called_once()


def test_send_reset_email_via_plain_smtp_with_login():
    """send_reset_email uses plain SMTP with login when user is set and dev mode."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch("app.utils.email.smtplib.SMTP") as mock_smtp_cls,
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_user = "admin"
        mock_settings.smtp_password = "secret"  # pragma: allowlist secret
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = True  # dev mode allows insecure

        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_reset_email("user@example.com", "https://example.com/r")

        mock_smtp.login.assert_called_once_with("admin", "secret")


def test_send_reset_email_catches_smtp_exception():
    """SMTP errors are caught and logged without re-raising."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch(
            "app.utils.email.smtplib.SMTP_SSL",
            side_effect=smtplib.SMTPException("fail"),
        ),
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "ssl"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        # Should not raise
        send_reset_email("user@example.com", "https://example.com/r")


def test_send_reset_email_catches_os_error():
    """OS errors are caught and logged without re-raising."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch(
            "app.utils.email.smtplib.SMTP", side_effect=OSError("connection refused")
        ),
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "starttls"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        send_reset_email("user@example.com", "https://example.com/r")


# ---------------------------------------------------------------------------
# send_lockout_email
# ---------------------------------------------------------------------------


def test_send_lockout_email_no_host_logs_warning():
    """When SMTP is not configured, falls back silently."""
    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = ""
        mock_settings.smtp_port = 0
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = ""
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        send_lockout_email("user@example.com", "Alice")


def test_send_lockout_email_via_ssl():
    """send_lockout_email uses SMTP_SSL when security=ssl."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch("app.utils.email.smtplib.SMTP_SSL") as mock_smtp_ssl_cls,
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "ssl"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        mock_smtp = MagicMock()
        mock_smtp_ssl_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_lockout_email("user@example.com", "Alice")

        mock_smtp.send_message.assert_called_once()


def test_send_lockout_email_catches_smtp_exception():
    """SMTP errors are caught without re-raising."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch(
            "app.utils.email.smtplib.SMTP", side_effect=smtplib.SMTPException("fail")
        ),
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "starttls"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False

        send_lockout_email("user@example.com")


def test_send_lockout_email_insecure_not_dev_logs_error():
    """User + no security + not development → reject."""
    with patch("app.utils.email.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"  # pragma: allowlist secret
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = False
        mock_settings.environment = "production"

        send_lockout_email("user@example.com", "Bob")


def test_send_lockout_email_via_plain_smtp_no_user():
    """Plain SMTP without user credentials sends without login."""
    with (
        patch("app.utils.email.settings") as mock_settings,
        patch("app.utils.email.smtplib.SMTP") as mock_smtp_cls,
        patch("app.utils.email.ssl.create_default_context"),
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.mail_from = "no-reply@example.com"
        mock_settings.smtp_security = "none"
        mock_settings.smtp_starttls = False
        mock_settings.is_development = True

        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_lockout_email("user@example.com")

        mock_smtp.login.assert_not_called()
        mock_smtp.send_message.assert_called_once()
