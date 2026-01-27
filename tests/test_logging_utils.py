from app.utils.logging import REDACTED_VALUE, redact_sensitive_mapping


def test_redact_sensitive_mapping_empty():
    assert redact_sensitive_mapping(None) == {}
    assert redact_sensitive_mapping({}) == {}


def test_redact_sensitive_mapping_all_redacted():
    data = {"password": "secret", "token": "123", "user": "admin"}  # NOSONAR
    redacted = redact_sensitive_mapping(data)
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["token"] == REDACTED_VALUE
    assert redacted["user"] == REDACTED_VALUE


def test_redact_sensitive_mapping_with_allowlist():
    data = {"password": "secret", "user": "admin", "theme": "dark"}  # NOSONAR
    allowlist = ["user", "theme"]
    redacted = redact_sensitive_mapping(data, allowlist=allowlist)
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["user"] == "admin"
    assert redacted["theme"] == "dark"


def test_redact_sensitive_mapping_case_insensitive():
    data = {"Password": "secret", "USER": "admin"}  # NOSONAR
    allowlist = ["user"]
    redacted = redact_sensitive_mapping(data, allowlist=allowlist)
    assert redacted["Password"] == REDACTED_VALUE
    assert redacted["USER"] == "admin"


def test_redact_sensitive_mapping_preserves_original():
    data = {"key": "val"}
    redacted = redact_sensitive_mapping(data)
    assert data["key"] == "val"
    assert redacted["key"] == REDACTED_VALUE
