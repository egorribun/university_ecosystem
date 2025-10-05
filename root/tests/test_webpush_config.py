import pytest

from app.core.config import Settings, _validate_webpush_subject


@pytest.mark.parametrize(
    "value,expected",
    [
        ("mailto:Admin@example.com", "mailto:admin@example.com"),
        ("https://example.com", "https://example.com"),
        ("http://localhost:8000", "http://localhost:8000"),
    ],
)
def test_validate_webpush_subject_accepts_supported_values(value, expected):
    assert _validate_webpush_subject(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        "mailto:",  # missing address
        "mailto:not-an-email",  # missing @
        "ws://example.com",  # unsupported scheme
        "https://",  # missing host
        "http://example.com",  # insecure host
    ],
)
def test_validate_webpush_subject_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        _validate_webpush_subject(value)


def test_settings_webpush_subject_defaults(monkeypatch):
    monkeypatch.delenv("VAPID_SUBJECT", raising=False)
    settings = Settings(vapid_subject="")
    assert settings.WEBPUSH_SUBJECT == "mailto:no-reply@example.com"


def test_settings_webpush_subject_invalid(monkeypatch):
    monkeypatch.setenv("VAPID_SUBJECT", "invalid-subject")
    settings = Settings()
    with pytest.raises(ValueError):
        _ = settings.WEBPUSH_SUBJECT
