"""Exact PII redaction contract for structured log events."""

from __future__ import annotations

import json
import logging
from io import StringIO
from typing import Any

import pytest

import app.core.logging as logging_mod
from app.core.logging import (
    _normalize_field_name,
    _redact_free_text,
    _redact_nested,
    _redact_pii,
)

REDACTED = "[REDACTED]"


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("APIKey", "api_key"),
        ("accessToken", "access_token"),
        ("X-Api-Key", "x_api_key"),
        ("__Email__", "email"),
        ("sessionID", "session_id"),
        ("CSRFToken", "csrf_token"),
        ("Set-Cookie", "set_cookie"),
        ("refresh-token", "refresh_token"),
        ("PHONE", "phone"),
    ],
)
def test_field_names_normalize_across_naming_styles(raw: str, normalized: str) -> None:
    assert _normalize_field_name(raw) == normalized


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call +1 555 123 4567", f"call {REDACTED}"),
        ("reach me at 555-123-4567", f"reach me at {REDACTED}"),
        ("phone: 555.123.4567", f"phone: {REDACTED}"),
        ("+7 999.123.4567", REDACTED),
        ("write a@b.cc", f"write {REDACTED}"),
        # Explicit non-phone context and dotted numbers without phone context
        # (versions, build numbers) stay readable.
        ("build 555-0199", "build 555-0199"),
        ("see 555.123.4567", "see 555.123.4567"),
    ],
)
def test_free_text_redacts_contacts_but_keeps_numeric_identifiers(
    text: str, expected: str
) -> None:
    assert _redact_free_text(text) == expected


def test_the_shortest_email_is_redacted_inside_structures() -> None:
    assert _redact_nested("a@b.cc", seen=set()) == REDACTED


def test_nested_mappings_lists_and_tuples_are_redacted_in_place() -> None:
    payload: dict[str, Any] = {
        "user": {
            "password": "hunter2",  # pragma: allowlist secret
            "note": "mail a@b.cc",
        },
        "items": [["call 555-123-4567"], {"token": "t"}],
        "pair": ("a@b.cc", 5),
        "nested_pair": (("a@b.cc",), 5),
    }

    result = _redact_nested(payload, seen=set())

    assert result is payload
    assert payload == {
        "user": {"password": REDACTED, "note": f"mail {REDACTED}"},
        "items": [[f"call {REDACTED}"], {"token": REDACTED}],
        "pair": (REDACTED, 5),
        "nested_pair": ((REDACTED,), 5),
    }


def test_shared_values_are_redacted_every_time_they_appear() -> None:
    shared_dict = {"note": "a@b.cc"}
    shared_list = ["a@b.cc"]
    shared_tuple = ("a@b.cc",)
    payload = {
        "d1": shared_dict,
        "d2": shared_dict,
        "l1": shared_list,
        "l2": shared_list,
        "t1": shared_tuple,
        "t2": shared_tuple,
    }

    _redact_nested(payload, seen=set())

    assert payload["d2"] is shared_dict
    assert shared_dict == {"note": REDACTED}
    assert payload["l2"] is shared_list
    assert shared_list == [REDACTED]
    assert payload["t1"] == payload["t2"] == (REDACTED,)


def test_cycles_are_replaced_instead_of_recursing_forever() -> None:
    cyclic_dict: dict[str, Any] = {"note": "ok"}
    cyclic_dict["self"] = cyclic_dict
    cyclic_list: list[Any] = ["ok"]
    cyclic_list.append(cyclic_list)

    assert _redact_nested(cyclic_dict, seen=set()) == {"note": "ok", "self": REDACTED}
    assert _redact_nested(cyclic_list, seen=set()) == ["ok", REDACTED]


def test_event_dict_redaction_covers_fields_values_and_self_references() -> None:
    event: dict[str, Any] = {
        "event": "login for a@b.cc",
        "Authorization": "Bearer secret",  # pragma: allowlist secret
        "context": {"refreshToken": "r", "detail": "call 555-123-4567"},
    }
    event["loop"] = event

    result = _redact_pii(None, "info", event)

    assert result is event
    assert event == {
        "event": f"login for {REDACTED}",
        "Authorization": REDACTED,
        "context": {"refreshToken": REDACTED, "detail": f"call {REDACTED}"},
        "loop": REDACTED,
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "reset_token",
        "reset-token",
        "resetToken",
        "ResetToken",
        "RESET_TOKEN",
        "csrf_hmac_secret",
        "csrf-hmac-secret",
        "csrfHmacSecret",
        "CsrfHmacSecret",
        "CSRF_HMAC_SECRET",
    ],
)
def test_account_recovery_and_csrf_fields_are_redacted_at_every_depth(
    field_name: str,
) -> None:
    """AUD-359: credential-bearing fields must not fall back to text matching."""
    event = {
        field_name: "synthetic-value",
        "details": [{"nested": {field_name: "synthetic-value"}}],
    }

    assert _redact_pii(None, "info", event) == {
        field_name: REDACTED,
        "details": [{"nested": {field_name: REDACTED}}],
    }


def test_sensitive_field_matching_preserves_related_nonsecret_metadata() -> None:
    """AUD-359: fixing exact names must not mask all token/secret-prefixed keys."""
    event = {
        "event": "security configuration inspected",
        "reset_token_count": 7,
        "reset_token_expiry_minutes": 45,
        "csrf_hmac_secret_configured": True,
        "token_type": "Bearer",
        "secret_name": "csrf-signing-key",
        "details": {
            "resetTokenCount": 7,
            "csrfHmacSecretConfigured": True,
            "status": "configured",
        },
    }

    assert _redact_pii(None, "info", event) == {
        "event": "security configuration inspected",
        "reset_token_count": 7,
        "reset_token_expiry_minutes": 45,
        "csrf_hmac_secret_configured": True,
        "token_type": "Bearer",
        "secret_name": "csrf-signing-key",
        "details": {
            "resetTokenCount": 7,
            "csrfHmacSecretConfigured": True,
            "status": "configured",
        },
    }


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("field_name", ["reset_token", "csrf_hmac_secret"])
def test_account_recovery_and_csrf_values_never_reach_log_renderers(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    field_name: str,
) -> None:
    """Exercise the real configured processor chain and its emitted output."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    sensitive_value = "synthetic-value"

    try:
        logging_mod.configure_logging(json_output=json_output)
        logger = logging_mod.get_logger("audit-359-regression").bind(
            **{field_name: sensitive_value}
        )
        logger.info(
            "security configuration inspected",
            details={"items": [{field_name: sensitive_value}]},
            status="public-diagnostic",
        )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "security configuration inspected" in output
    assert "public-diagnostic" in output
    assert field_name in output
    assert sensitive_value not in output
    assert output.count(REDACTED) == 2
    if json_output:
        rendered = json.loads(output)
        assert rendered[field_name] == REDACTED
        assert rendered["details"] == {"items": [{field_name: REDACTED}]}
        assert rendered["status"] == "public-diagnostic"
