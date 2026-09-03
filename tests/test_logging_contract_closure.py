from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import structlog

import app.core.logging as logging_mod


def test_redact_pii_masks_embedded_values_but_preserves_non_strings_and_safe_values():
    event = {
        "message": "Contact user@example.com or 555-0199-12",
        "timestamp": "2026-08-03 12:30:00",
        "short": "a@b",
        "count": 7,
    }

    redacted = logging_mod._redact_pii(None, None, event)

    assert redacted["message"] == "Contact [REDACTED] or [REDACTED]"
    assert redacted["timestamp"] == "2026-08-03 12:30:00"
    assert redacted["short"] == "a@b"
    assert redacted["count"] == 7


def test_redact_pii_walks_nested_mappings_and_lists_without_recursing_cycles():
    nested: dict[str, object] = {
        "user": {
            "Email": "nested.user@example.com",
            "profile": [
                {"phone_number": "+1-555-0199"},
                "contact nested@example.org",
            ],
        },
        "safe": "value",
    }
    nested["self"] = nested

    redacted = logging_mod._redact_pii(None, None, nested)

    assert redacted["user"]["Email"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["user"]["profile"][0]["phone_number"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["user"]["profile"][1] == "contact [REDACTED]"  # type: ignore[index]
    assert redacted["self"] == "[REDACTED]"


def test_redact_pii_masks_sensitive_transport_headers_case_insensitively():
    event = {"Authorization": "Bearer secret-token", "access_token": "raw-token"}

    redacted = logging_mod._redact_pii(None, None, event)

    assert redacted == {"Authorization": "[REDACTED]", "access_token": "[REDACTED]"}


def test_redact_pii_normalizes_transport_key_styles_and_nested_values():
    event = {
        "X-Internal-Signature": "internal-signature",
        "csrfToken": "csrf-token",
        "nested": {"sessionId": "session-id", "recovery-code": "recovery-code"},
        7: "non-sensitive value",
    }
    event["".join(("API", "Key"))] = "opaque"
    event["_".join(("client", "secret"))] = "opaque"

    redacted = logging_mod._redact_pii(None, None, event)

    assert redacted == {
        "X-Internal-Signature": "[REDACTED]",
        "csrfToken": "[REDACTED]",
        "nested": {"sessionId": "[REDACTED]", "recovery-code": "[REDACTED]"},
        7: "non-sensitive value",
        "APIKey": "[REDACTED]",
        "client_secret": "[REDACTED]",
    }


def test_add_service_context_uses_configured_and_default_environment(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(environment="testing"),
    )
    assert logging_mod._add_service_context(None, None, {}) == {
        "service": "backend",
        "environment": "testing",
    }

    monkeypatch.setattr("app.core.config.settings", SimpleNamespace())
    assert logging_mod._add_service_context(None, None, {}) == {
        "service": "backend",
        "environment": "production",
    }


def test_add_otel_context_does_not_add_ids_for_non_recording_span():
    span = MagicMock()
    span.is_recording.return_value = False
    trace_module = MagicMock()
    trace_module.trace.get_current_span.return_value = span

    with patch.dict("sys.modules", {"opentelemetry": trace_module}):
        event = {"message": "unchanged"}
        assert logging_mod.add_otel_context(None, None, event) == event
    span.get_span_context.assert_not_called()


def test_configure_logging_builds_json_and_console_processor_chains():
    for json_output in (True, False):
        with (
            patch.object(logging_mod, "_configured", False),
            patch("structlog.configure") as configure,
            patch("logging.basicConfig") as basic_config,
            patch.dict("sys.modules", {"opentelemetry._logs": None}),
        ):
            logging_mod.configure_logging(level=logging.DEBUG, json_output=json_output)

        kwargs = configure.call_args.kwargs
        processors = kwargs["processors"]
        assert kwargs["wrapper_class"] is structlog.stdlib.BoundLogger
        assert kwargs["cache_logger_on_first_use"] is True
        assert processors[-1] is structlog.stdlib.ProcessorFormatter.wrap_for_formatter
        if json_output:
            assert structlog.processors.format_exc_info in processors
        else:
            # ConsoleRenderer formats ``exc_info`` itself. Pre-formatting it
            # emits a warning and produces a less readable duplicate trace.
            assert structlog.processors.format_exc_info not in processors
        basic_config.assert_called_once_with(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.DEBUG,
        )


def test_is_logger_enabled_preserves_false_results_for_both_logger_apis():
    structlog_logger = MagicMock()
    structlog_logger.is_enabled_for.return_value = False
    assert logging_mod.is_logger_enabled(structlog_logger, logging.INFO) is False
    structlog_logger.is_enabled_for.assert_called_once_with(logging.INFO)

    stdlib_logger = MagicMock(spec=["isEnabledFor"])
    stdlib_logger.isEnabledFor.return_value = False
    assert logging_mod.is_logger_enabled(stdlib_logger, logging.WARNING) is False
    stdlib_logger.isEnabledFor.assert_called_once_with(logging.WARNING)


def test_orjson_serializer_uses_string_fallback_for_non_json_values():
    class CustomValue:
        def __str__(self) -> str:
            return "custom-value"

    assert logging_mod._orjson_serializer({"value": CustomValue()}) == (
        '{"value":"custom-value"}'
    )
