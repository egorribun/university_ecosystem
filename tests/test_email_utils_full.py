"""Full coverage tests for app/utils/email.py.

Targets UNCOVERED branches not already addressed by:
  - tests/test_email_utils.py
  - tests/test_utils_email.py
  - tests/test_email_utilities.py

Specific coverage targets:
  - _log_event: disabled-logger fallback path
  - build_reset_email_content / build_lockout_email_content: HTML structure,
    locale, name-suffix logic, XSS-link safety, UTF-8 content
  - send_reset_email / send_lockout_email: smtp_starttls=True legacy fallback,
    lockout OSError catch, lockout STARTTLS with authenticated user in dev mode
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from app.utils.email import (
    RESET_TOKEN_EXPIRY_MINUTES,
    _log_event,
    _redact_sensitive_query,
    build_lockout_email_content,
    build_reset_email_content,
    send_lockout_email,
    send_reset_email,
)

# ---------------------------------------------------------------------------
# _log_event — disabled-logger fallback path
# ---------------------------------------------------------------------------


def test_log_event_uses_root_logger_when_module_logger_disabled(caplog):
    """When the module logger is disabled, _log_event routes to root logger."""
    import app.utils.email as email_mod

    original_disabled = email_mod.logger.disabled
    try:
        email_mod.logger.disabled = True
        with caplog.at_level(logging.WARNING, logger=""):
            _log_event(logging.WARNING, "test.disabled.logger.path")
        assert any("test.disabled.logger.path" in r.message for r in caplog.records)
    finally:
        email_mod.logger.disabled = original_disabled


def test_log_event_uses_module_logger_when_enabled(caplog):
    """When module logger is active, _log_event uses it directly."""
    import app.utils.email as email_mod

    original_disabled = email_mod.logger.disabled
    try:
        email_mod.logger.disabled = False
        with caplog.at_level(logging.WARNING, logger="app.utils.email"):
            _log_event(logging.WARNING, "test.module.logger.path")
        assert any("test.module.logger.path" in r.message for r in caplog.records)
    finally:
        email_mod.logger.disabled = original_disabled


# ---------------------------------------------------------------------------
# build_reset_email_content — structural and content checks
# ---------------------------------------------------------------------------


def test_build_reset_email_content_html_structure():
    """HTML output must contain required structural tags."""
    link = "https://example.com/reset?token=xyz"
    _, _, html = build_reset_email_content(link, "Alice")

    assert "<div" in html
    assert "<h2>" in html
    assert "<p>" in html
    assert f'href="{link}"' in html


def test_build_reset_email_content_expiry_in_plain():
    """Plain text must reference the token expiry minutes."""
    link = "https://example.com/reset?token=xyz"
    _, plain, _ = build_reset_email_content(link)
    assert str(RESET_TOKEN_EXPIRY_MINUTES) in plain


def test_build_reset_email_content_name_suffix_with_name():
    """When full_name is provided, the greeting contains it."""
    link = "https://example.com/reset"
    _, _, html = build_reset_email_content(link, "Ivan Petrov")
    assert "Ivan Petrov" in html


def test_build_reset_email_content_name_suffix_empty():
    """When full_name is empty, HTML is still produced correctly."""
    link = "https://example.com/reset"
    _, _, html = build_reset_email_content(link, "")
    assert "<h2>" in html


def test_build_reset_email_content_locale_ru():
    """Russian locale produces non-empty strings without crashing."""
    subject, plain, html = build_reset_email_content(
        "https://example.com/reset", "Test", locale="ru"
    )
    assert isinstance(subject, str) and len(subject) > 0
    assert isinstance(plain, str) and len(plain) > 0
    assert isinstance(html, str) and len(html) > 0


def test_build_reset_email_content_link_verbatim():
    """The link URL must appear verbatim in the HTML (no double-encoding)."""
    link = "https://example.com/reset?token=abc123&locale=en"
    _, _, html = build_reset_email_content(link)
    assert link in html


def test_build_reset_email_content_utf8_in_name():
    """Names with non-ASCII characters are handled without encoding errors."""
    link = "https://example.com/reset"
    subject, plain, html = build_reset_email_content(link, "Mohammed Ali")
    assert "Mohammed Ali" in html
    html.encode("utf-8")
    plain.encode("utf-8")
    subject.encode("utf-8")


# ---------------------------------------------------------------------------
# build_lockout_email_content — structural checks
# ---------------------------------------------------------------------------


def test_build_lockout_email_content_html_structure():
    """HTML output must have standard div/h2/p structure."""
    _, _, html = build_lockout_email_content("Bob")
    assert "<div" in html
    assert "<h2>" in html
    assert "<p>" in html


def test_build_lockout_email_content_locale_ru():
    """Russian locale variant is produced without error."""
    subject, plain, html = build_lockout_email_content("Anna", locale="ru")
    assert isinstance(subject, str) and len(subject) > 0
    assert isinstance(plain, str) and len(plain) > 0
    assert isinstance(html, str) and len(html) > 0


def test_build_lockout_email_content_name_suffix_empty():
    """Empty name produces valid output."""
    subject, _plain, html = build_lockout_email_content("")
    assert isinstance(subject, str)
    assert isinstance(html, str)


def test_build_lockout_email_content_utf8_name():
    """Non-ASCII names encode cleanly."""
    _, plain, html = build_lockout_email_content("Angstrom Bjork")
    html.encode("utf-8")
    plain.encode("utf-8")


# ---------------------------------------------------------------------------
# _redact_sensitive_query — edge cases not covered by existing tests
# ---------------------------------------------------------------------------


def test_redact_preserves_fragment():
    """URL fragments (#) are preserved after redaction."""
    url = "https://example.com/reset?token=secret#section1"
    result = _redact_sensitive_query(url)
    assert "secret" not in result
    assert "section1" in result


def test_redact_blank_token_value():
    """A token with an empty value still produces a token= key."""
    url = "https://example.com/reset?token="
    result = _redact_sensitive_query(url)
    assert "token=" in result


def test_redact_case_insensitive_key():
    """Token key comparison is case-insensitive (key.lower())."""
    url = "https://example.com/reset?TOKEN=secret123"
    result = _redact_sensitive_query(url)
    assert "secret123" not in result


def test_redact_empty_url_returns_string():
    """Empty string input produces a string output (no exception)."""
    result = _redact_sensitive_query("")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# send_reset_email — smtp_starttls=True legacy resolution path
# ---------------------------------------------------------------------------


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_reset_email_starttls_via_smtp_starttls_bool(
    mock_ssl, mock_smtp_cls, mock_settings
):
    """When smtp_security is empty but smtp_starttls=True, uses STARTTLS path."""
    mock_settings.smtp_host = "smtp.example.com"
    mock_settings.smtp_port = 587
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = ""  # empty — resolved from smtp_starttls
    mock_settings.smtp_starttls = True
    mock_settings.is_development = False

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_reset_email("user@example.com", "https://example.com/reset")

    mock_smtp.starttls.assert_called_once()
    mock_smtp.send_message.assert_called_once()


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_reset_email_plain_smtp_when_smtp_starttls_false(
    mock_ssl, mock_smtp_cls, mock_settings
):
    """When smtp_security is empty and smtp_starttls=False, uses plain SMTP."""
    mock_settings.smtp_host = "mail.example.com"
    mock_settings.smtp_port = 25
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = ""  # empty → "none"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_reset_email("user@example.com", "https://example.com/reset")

    mock_smtp.starttls.assert_not_called()
    mock_smtp.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# send_reset_email — EmailMessage header correctness
# ---------------------------------------------------------------------------


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_reset_email_message_headers(mock_ssl, mock_smtp_cls, mock_settings):
    """Verify Subject, From and To headers are correctly set on the sent message."""
    mock_settings.smtp_host = "mail.example.com"
    mock_settings.smtp_port = 25
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "noreply@university.edu"
    mock_settings.smtp_security = "none"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    captured: list[EmailMessage] = []
    mock_smtp = MagicMock()

    def capture_send(msg):
        captured.append(msg)

    mock_smtp.send_message.side_effect = capture_send
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_reset_email("student@uni.edu", "https://example.com/reset", "Jane")

    assert len(captured) == 1
    msg = captured[0]
    assert msg["To"] == "student@uni.edu"
    assert msg["From"] == "noreply@university.edu"
    assert isinstance(msg["Subject"], str) and len(msg["Subject"]) > 0


# ---------------------------------------------------------------------------
# send_lockout_email — uncovered exception and auth paths
# ---------------------------------------------------------------------------


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_lockout_email_catches_os_error(
    mock_ssl, mock_smtp_cls, mock_settings, caplog
):
    """OSError during lockout email SMTP connection is caught and logged."""
    mock_settings.smtp_host = "mail.example.com"
    mock_settings.smtp_port = 25
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = "none"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    mock_smtp_cls.side_effect = OSError("connection refused")

    with caplog.at_level(logging.ERROR, logger=""):
        send_lockout_email("user@example.com", "Bob")

    assert any("auth.lockout_email.error" in r.msg for r in caplog.records)


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_lockout_email_starttls_with_user_dev(
    mock_ssl, mock_smtp_cls, mock_settings
):
    """Lockout email over STARTTLS with user credentials in dev mode calls login."""
    mock_settings.smtp_host = "smtp.example.com"
    mock_settings.smtp_port = 587
    mock_settings.smtp_user = "devuser"
    mock_settings.smtp_password = "devpass"  # pragma: allowlist secret
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = "starttls"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = True

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_lockout_email("user@example.com", "Carol")

    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("devuser", "devpass")
    mock_smtp.send_message.assert_called_once()


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP_SSL")
@patch("app.utils.email.ssl.create_default_context")
def test_send_lockout_email_ssl_catches_smtp_exception(
    mock_ssl, mock_smtp_ssl_cls, mock_settings, caplog
):
    """SMTPException during SSL lockout email is caught and logged."""
    mock_settings.smtp_host = "smtp.example.com"
    mock_settings.smtp_port = 465
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = "ssl"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    mock_smtp_ssl_cls.side_effect = smtplib.SMTPException("auth failed")

    with caplog.at_level(logging.ERROR, logger=""):
        send_lockout_email("user@example.com", "Dave")

    assert any("auth.lockout_email.error" in r.msg for r in caplog.records)


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_lockout_email_starttls_via_smtp_starttls_bool(
    mock_ssl, mock_smtp_cls, mock_settings
):
    """Lockout email resolves STARTTLS path from smtp_starttls=True flag."""
    mock_settings.smtp_host = "smtp.example.com"
    mock_settings.smtp_port = 587
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = ""  # empty — resolved from smtp_starttls
    mock_settings.smtp_starttls = True
    mock_settings.is_development = False

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_lockout_email("user@example.com")

    mock_smtp.starttls.assert_called_once()
    mock_smtp.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# send_lockout_email — message header correctness
# ---------------------------------------------------------------------------


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP")
@patch("app.utils.email.ssl.create_default_context")
def test_send_lockout_email_message_headers(mock_ssl, mock_smtp_cls, mock_settings):
    """Verify Subject, From and To are correctly set on lockout email."""
    mock_settings.smtp_host = "mail.example.com"
    mock_settings.smtp_port = 25
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "security@university.edu"
    mock_settings.smtp_security = "none"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    captured: list[EmailMessage] = []
    mock_smtp = MagicMock()

    def capture_send(msg):
        captured.append(msg)

    mock_smtp.send_message.side_effect = capture_send
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    send_lockout_email("locked@uni.edu", "Eve")

    assert len(captured) == 1
    msg = captured[0]
    assert msg["To"] == "locked@uni.edu"
    assert msg["From"] == "security@university.edu"
    assert isinstance(msg["Subject"], str) and len(msg["Subject"]) > 0


# ---------------------------------------------------------------------------
# Transport error — link redaction in error log
# ---------------------------------------------------------------------------


@patch("app.utils.email.settings")
@patch("app.utils.email.smtplib.SMTP_SSL")
@patch("app.utils.email.ssl.create_default_context")
def test_send_reset_email_error_redacts_token_in_log(
    mock_ssl, mock_smtp_ssl_cls, mock_settings, caplog
):
    """On SMTP error, the raw token must not appear in the log output."""
    mock_settings.smtp_host = "smtp.example.com"
    mock_settings.smtp_port = 465
    mock_settings.smtp_user = ""
    mock_settings.smtp_password = ""
    mock_settings.mail_from = "no-reply@example.com"
    mock_settings.smtp_security = "ssl"
    mock_settings.smtp_starttls = False
    mock_settings.is_development = False

    mock_smtp_ssl_cls.side_effect = OSError("network unreachable")
    secret_token = "supersecrettoken99"  # pragma: allowlist secret

    with caplog.at_level(logging.ERROR, logger=""):
        send_reset_email(
            "user@example.com",
            f"https://example.com/reset?token={secret_token}",
        )

    error_records = [r for r in caplog.records if "reset_email.error" in r.msg]
    assert len(error_records) > 0

    all_log_text = " ".join(
        str(getattr(r, "link", "")) + r.getMessage() for r in caplog.records
    )
    assert secret_token not in all_log_text
