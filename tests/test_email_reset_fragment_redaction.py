"""Reset-link credentials must not escape through email diagnostics."""

from __future__ import annotations

import logging
import secrets
import string
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.utils import email as email_utils


@pytest.fixture
def reset_token() -> str:
    # Alphabetic synthetic credentials cannot accidentally match phone redaction.
    return "".join(secrets.choice(string.ascii_letters) for _ in range(64))


@pytest.mark.parametrize("key", ["token", "TOKEN", "code", "CoDe", "%74oken"])
def test_reset_fragment_credentials_are_redacted(key: str, reset_token: str) -> None:
    link = (
        f"https://example.test/reset-password?locale=ru"
        f"#{key}={reset_token}&locale=en"
    )

    sanitized = email_utils._redact_sensitive_query(link)

    assert reset_token not in sanitized
    parsed = urlsplit(sanitized)
    assert parse_qs(parsed.query) == {"locale": ["ru"]}
    fragment = parse_qs(parsed.fragment)
    assert fragment["locale"] == ["en"]
    sensitive_values = [
        value
        for name, values in fragment.items()
        if name.lower() in {"token", "code"}
        for value in values
    ]
    assert sensitive_values == ["***redacted***"]


def test_reset_query_and_repeated_fragment_credentials_are_all_redacted(
    reset_token: str,
) -> None:
    link = (
        f"https://example.test/reset-password?token={reset_token}&locale=en"
        f"#token={reset_token}&token=&code={reset_token}&locale=ru"
    )

    sanitized = email_utils._redact_sensitive_query(link)

    assert reset_token not in sanitized
    parsed = urlsplit(sanitized)
    assert parse_qs(parsed.query) == {
        "token": ["***redacted***"],
        "locale": ["en"],
    }
    assert parse_qs(parsed.fragment) == {
        "token": ["***redacted***", "***redacted***"],
        "code": ["***redacted***"],
        "locale": ["ru"],
    }


@pytest.fixture
def local_smtp_settings(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    configured = SimpleNamespace(
        smtp_host="",
        smtp_port=0,
        smtp_user="",
        smtp_password="",
        smtp_security="none",
        smtp_starttls=False,
        mail_from="sender@example.test",
        is_development=True,
        environment="testing",
    )
    monkeypatch.setattr("app.core.config.settings", configured)
    monkeypatch.setattr(email_utils, "settings", configured)
    return configured


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "task"])
async def test_missing_smtp_diagnostics_do_not_log_reset_fragment_credentials(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    local_smtp_settings: SimpleNamespace,
    reset_token: str,
    asynchronous: bool,
) -> None:
    from app.tasks import email as email_tasks

    # Keep the actual redaction/logging bridge; only email body rendering is
    # irrelevant to this diagnostic boundary.
    monkeypatch.setattr(
        email_utils,
        "build_reset_email_content",
        lambda *_args, **_kwargs: ("Reset", "Plain", "<p>Reset</p>"),
    )
    link = f"https://example.test/reset-password#token={reset_token}"
    caplog.set_level(logging.WARNING)

    if asynchronous:
        handler = getattr(
            email_tasks.send_auth_email,
            "__wrapped__",
            email_tasks.send_auth_email,
        )
        await handler("student@example.test", link, "Student", locale="en")
    else:
        email_utils.send_reset_email(
            "student@example.test", link, "Student", locale="en"
        )

    records = [
        record
        for record in caplog.records
        if record.getMessage() == "password.reset_email.fallback"
    ]
    assert len(records) == 1
    assert reset_token not in repr(vars(records[0]))
    assert reset_token not in caplog.text
    fragment = parse_qs(urlsplit(records[0].link).fragment)
    assert fragment["token"] == ["***redacted***"]
