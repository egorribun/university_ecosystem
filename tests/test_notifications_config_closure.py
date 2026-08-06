"""Behavioral coverage closure for notification settings validation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError


def _settings(**overrides):
    from app.core.config.notifications import NotificationSettings

    values = {
        "_allow_missing": True,
        "environment": "testing",
        "database_url": "sqlite+aiosqlite:///./test.db",
        "secret_key": "local-targeted-test-secret-32-chars",
        **overrides,
    }
    return NotificationSettings(**values)


def test_webpush_subject_accepts_mailto_https_and_local_http() -> None:
    assert _settings(vapid_subject="mailto:User@Example.COM").WEBPUSH_SUBJECT == (
        "mailto:user@example.com"
    )
    assert _settings(
        vapid_subject=" https://push.example.test/app "
    ).WEBPUSH_SUBJECT == ("https://push.example.test/app")
    assert _settings(vapid_subject="http://localhost:8000").WEBPUSH_SUBJECT == (
        "http://localhost:8000"
    )
    assert _settings(vapid_subject=" ").WEBPUSH_SUBJECT == (
        "mailto:no-reply@example.com"
    )


@pytest.mark.parametrize(
    "subject, message",
    [
        ("", "must not be empty"),
        ("mailto:not-an-email", "valid email"),
        ("ftp://example.test", "https or http"),
        ("https://", "include a host"),
        ("http://example.test", "localhost"),
    ],
)
def test_webpush_subject_rejects_invalid_values(subject: str, message: str) -> None:
    from app.core.config.notifications import _validate_webpush_subject

    with pytest.raises(ValueError, match=message):
        _validate_webpush_subject(subject)


def test_notification_topics_are_normalized_deduplicated_and_cached() -> None:
    settings = _settings(notifications_allowed_push_topics=" News, events,news, ")
    assert settings.notifications_allowed_push_topics == ["news", "events"]
    assert settings.notifications_allowed_push_topics_set == frozenset(
        {"news", "events"}
    )
    assert settings.notifications_allowed_push_topics_list == ["news", "events"]


def test_notification_topics_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="at least one topic"):
        _settings(notifications_allowed_push_topics=" , ")


def test_smtp_security_normalization_and_validation() -> None:
    assert _settings(smtp_security=" SSL ").smtp_security == "ssl"
    assert _settings(smtp_security=None).smtp_security == "none"
    with pytest.raises(ValidationError, match="one of: none, ssl, starttls"):
        _settings(smtp_security="tls")


def test_smtp_user_security_validator_covers_dev_and_production_paths() -> None:
    from app.core.config.notifications import NotificationSettings

    assert (
        NotificationSettings._validate_smtp_user_security(
            "user",
            SimpleNamespace(
                data={"smtp_security": "starttls", "environment": "production"}
            ),
        )
        == "user"
    )
    assert (
        NotificationSettings._validate_smtp_user_security(
            "",
            SimpleNamespace(
                data={"smtp_security": "none", "environment": "production"}
            ),
        )
        == ""
    )
    with pytest.raises(ValueError, match="cannot be used"):
        NotificationSettings._validate_smtp_user_security(
            "user",
            SimpleNamespace(
                data={"smtp_security": "none", "environment": "production"}
            ),
        )
    assert (
        NotificationSettings._validate_smtp_user_security(
            "user",
            SimpleNamespace(data={"smtp_security": "none", "environment": "testing"}),
        )
        == "user"
    )


def test_notification_secret_file_validators_and_cached_keys(
    tmp_path, monkeypatch
) -> None:
    from app.core.config.notifications import NotificationSettings

    vapid_file = tmp_path / "vapid.key"
    smtp_file = tmp_path / "smtp.password"
    vapid_file.write_text("vapid-from-file\n", encoding="utf-8")
    smtp_file.write_text("smtp-from-file\n", encoding="utf-8")
    monkeypatch.setenv("VAPID_PRIVATE_KEY_FILE", str(vapid_file))
    monkeypatch.setenv("SMTP_PASSWORD_FILE", str(smtp_file))
    assert NotificationSettings._load_vapid_key("plain") == "vapid-from-file"
    assert NotificationSettings._load_smtp_password("plain") == "smtp-from-file"

    settings = _settings(vapid_public_key="public", vapid_private_key="private")
    assert settings.VAPID_PUBLIC_KEY == "public"
    assert settings.VAPID_PRIVATE_KEY == "vapid-from-file"


def test_notification_retention_batch_size_validator() -> None:
    from app.core.config.notifications import NotificationSettings

    assert NotificationSettings._validate_notifications_retention_batch_size(2) == 2
    with pytest.raises(ValueError, match="greater than zero"):
        NotificationSettings._validate_notifications_retention_batch_size(0)
