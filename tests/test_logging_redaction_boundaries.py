"""Adversarial boundaries of the central redactor used by both export sinks."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import app.core.logging as logging_mod


class Opaque:
    def __str__(self) -> str:
        raise AssertionError("opaque string conversion")

    def __repr__(self) -> str:
        raise AssertionError("opaque representation")

    def __bool__(self) -> bool:
        raise AssertionError("opaque truth conversion")


def test_non_string_keys_are_dropped_without_coercion_or_caller_mutation() -> None:
    key = Opaque()
    event = {key: "synthetic-value", 7: "synthetic-value", "event": "safe"}
    assert not logging_mod._is_pii_field_name(key)
    assert not logging_mod._is_pii_field_name(7)
    assert logging_mod._redact_pii(None, "info", event) == {"event": "safe"}
    assert event[key] == event[7] == "synthetic-value"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("phone   : 555.123.4567", "phone   : [REDACTED]"),
        ("version   : 555.123.4567", "version   : 555.123.4567"),
    ],
)
def test_context_with_spacing_preserves_versions_but_masks_phone_numbers(
    message: str, expected: str
) -> None:
    assert logging_mod._redact_free_text(message) == expected


def test_uuid_metadata_survives_between_contacts_without_protecting_neighbors() -> None:
    message = (
        "a@b.cc 01234567-89ab-cdef-0123-456789abcdef phone +1 555 123 4567 "
        "fedcba98-7654-3210-fedc-ba9876543210 b@c.dd"
    )
    assert logging_mod._redact_free_text(message) == (
        "[REDACTED] 01234567-89ab-cdef-0123-456789abcdef phone [REDACTED] "
        "fedcba98-7654-3210-fedc-ba9876543210 [REDACTED]"
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("exc_info", Opaque()),
        ("exc_info", (ValueError, ValueError("safe"))),
        ("exc_info", (ValueError, ValueError("safe"), Opaque())),
        ("_record", Opaque()),
        ("_from_structlog", 1),
        ("stack_info", Opaque()),
    ],
)
def test_invalid_framework_controls_are_dropped_without_truth_or_repr_hooks(
    name: str, value: Any
) -> None:
    event = {"event": "safe", name: value}
    assert logging_mod._redact_pii(None, "info", event) == {"event": "safe"}
    assert event[name] is value


@pytest.mark.parametrize("stack", [True, False, "safe stack text"])
def test_valid_stack_controls_survive_until_the_stack_renderer(
    stack: bool | str,
) -> None:
    record = logging.LogRecord("safe", logging.INFO, __file__, 1, "safe", (), None)
    event = {
        "event": "safe",
        "stack_info": stack,
        "_record": record,
        "_from_structlog": False,
    }
    redacted = logging_mod._redact_pii(None, "info", event)
    assert redacted["stack_info"] is stack
    assert redacted["_record"] is record
    assert redacted["_from_structlog"] is False


def test_real_json_fallback_preserves_known_metadata_without_unknown_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path(logging_mod.__file__).with_name("orjson_utils.py")
    spec = importlib.util.spec_from_file_location("redaction_json_fallback", path)
    assert spec is not None and spec.loader is not None
    fallback = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, "orjson", None)
        spec.loader.exec_module(fallback)
    monkeypatch.setattr(logging_mod, "orjson", fallback.orjson)
    value = {
        "id": UUID("01234567-89ab-cdef-0123-456789abcdef"),
        "at": datetime(2026, 11, 5, tzinfo=UTC),
        "opaque": Opaque(),
    }
    assert json.loads(logging_mod._orjson_serializer(value)) == {
        "id": "01234567-89ab-cdef-0123-456789abcdef",
        "at": "2026-11-05 00:00:00+00:00",
        "opaque": "[REDACTED]",
    }
