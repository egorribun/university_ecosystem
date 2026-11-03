"""Canonical identifiers survive redaction; phone numbers beside them still do not."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.core.logging import _redact_free_text, _redact_pii

_REDACTED = "[REDACTED]"
_SEED = "20261103"
_SAMPLE_SIZE = 5000


def _seeded_uuid4s(count: int) -> list[uuid.UUID]:
    """Deterministic version-4 identifiers derived from a fixed seed."""
    return [
        uuid.UUID(
            bytes=hashlib.sha256(f"{_SEED}:{index}".encode()).digest()[:16],
            version=4,
        )
        for index in range(count)
    ]


def test_seeded_uuid4_values_survive_the_structured_field_path() -> None:
    for identifier in _seeded_uuid4s(_SAMPLE_SIZE):
        text = str(identifier)
        event = _redact_pii(
            None,
            "info",
            {"event": "x", "request_id": text, "user_id": text, "chat_id": text},
        )
        assert event["request_id"] == text
        assert event["user_id"] == text
        assert event["chat_id"] == text


def test_seeded_uuid4_values_survive_the_free_text_path() -> None:
    for identifier in _seeded_uuid4s(_SAMPLE_SIZE):
        text = str(identifier)
        assert _redact_free_text(text) == text
        assert _redact_free_text(f"request {text} done") == f"request {text} done"
        assert _redact_free_text(text.upper()) == text.upper()
        assert _redact_free_text(identifier.hex) == identifier.hex


@pytest.mark.parametrize(
    ("template", "phone"),
    [
        ("{id} call +7 916 123 45 67", "+7 916 123 45 67"),
        ("{id} call 555-123-4567", "555-123-4567"),
        ("call 555-123-4567 {id}", "555-123-4567"),
        ("call 555-123-4567 {id} and more", "555-123-4567"),
    ],
)
def test_phone_next_to_an_identifier_is_still_redacted(
    template: str, phone: str
) -> None:
    identifier = str(uuid.UUID(int=0x0123456789ABCDEF0123456789ABCDEF, version=4))
    result = _redact_free_text(template.format(id=identifier))
    assert identifier in result
    assert phone not in result
    assert _REDACTED in result


def test_phone_next_to_a_compact_identifier_is_still_redacted() -> None:
    compact = uuid.UUID(int=0x0123456789ABCDEF0123456789ABCDEF).hex
    result = _redact_free_text(f"{compact} call 555-123-4567")
    assert compact in result
    assert "555-123-4567" not in result


def test_identifier_containing_phone_digits_is_not_partially_redacted() -> None:
    identifier = "d8d22522-91d1-4bf9-8f5f-85474fc4b611"
    assert _redact_free_text(identifier) == identifier
    assert _redact_free_text(f"id={identifier}.") == f"id={identifier}."
