"""Privacy-preserving bridge from stdlib/structlog records to OpenTelemetry."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from opentelemetry._logs import LogRecord
from opentelemetry.sdk._logs import LoggingHandler

from app.core.logging import (
    REQUEST_FAILURE_DIAGNOSTIC_FIELDS,
    _ExceptionSnapshot,
    _format_safe_exc_info,
    _orjson_serializer,
    _redact_nested,
    _redact_pii,
    _render_safe_exception,
    _safe_exception_attributes,
)
from app.core.orjson_utils import orjson

_STRUCTLOG_TRANSPORT_FIELDS = frozenset(
    {"_logger", "_name", "_record", "_from_structlog"}
)
_STANDARD_LOG_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


def _redacted_value(value: Any) -> Any:
    # Reuse the central fail-closed traversal, including its cycle and opaque
    # object handling. The JSON round-trip converts allowed UUID/datetime
    # metadata into OTel-compatible scalars without arbitrary repr/str hooks.
    return orjson.loads(
        _orjson_serializer({"value": _redact_nested(value, seen=set())})
    )["value"]


class RedactingLoggingHandler(LoggingHandler):
    """Redact every export surface before the SDK validates or emits it."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return super().format(record)
        except (TypeError, ValueError, KeyError, OverflowError):
            # A formatter can also request numeric conversions of redacted
            # extras. Keep the safe message; structured extras remain in OTel
            # attributes. Never retry the raw record or encode a JSON envelope
            # that a later free-text pass could corrupt.
            return str(_redacted_value(record.msg))

    @staticmethod
    def _get_attributes(record: logging.LogRecord) -> dict[str, Any]:
        safe_record = logging.makeLogRecord(record.__dict__.copy())
        safe_record.exc_info = None
        sdk_attributes = cast(
            Mapping[str, Any], LoggingHandler._get_attributes(safe_record)
        )
        attributes = {
            key: value
            for key, value in sdk_attributes.items()
            if key not in _STRUCTLOG_TRANSPORT_FIELDS
        }
        result: dict[str, Any] = _redacted_value(attributes)
        result.update(_safe_exception_attributes(record.exc_info))
        return result

    def _translate(self, record: logging.LogRecord) -> LogRecord:
        # Other handlers still need structlog's transport metadata and the
        # original args/exception controls. Never sanitize their shared record
        # in place, and never mutate caller-owned structured payloads.
        safe_record = logging.makeLogRecord(record.__dict__.copy())
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_FIELDS
        }
        for key in extras:
            safe_record.__dict__.pop(key)
        # Formatters can read extras independently of _get_attributes. Sanitize
        # the copied record too, before any formatter has access to these values.
        safe_record.__dict__.update(_redacted_value(extras))
        exception_attributes = _safe_exception_attributes(record.exc_info)
        safe_record.__dict__.update(exception_attributes)
        safe_record.exc_info = None
        safe_record.exc_text = exception_attributes.get("exception.stacktrace")
        native = (
            issubclass(type(record.__dict__.get("_logger")), logging.Logger)
            and type(record.__dict__.get("_name")) is str
            and type(record.msg) is dict
        )
        if native:
            method_name = record.levelname.lower()
            has_snapshot = (
                type(cast(dict[str, Any], record.msg).get("exception"))
                is _ExceptionSnapshot
            )
            redacted = _redact_pii(None, method_name, cast(dict[str, Any], record.msg))
            # Also support native records emitted before the shared processor
            # chain. Resolve only validated controls into safe structured data.
            event = _format_safe_exc_info(None, method_name, redacted)
            has_snapshot = (
                has_snapshot or type(event.get("exception")) is _ExceptionSnapshot
            )
            event = {
                key: value
                for key, value in event.items()
                if key not in _STRUCTLOG_TRANSPORT_FIELDS
            }
            if (
                event.get("logger") == "app.core.request_failure_diagnostic"
                and event.get("message") == "request_failure_diagnostic"
            ):
                event = {
                    key: event[key]
                    for key in REQUEST_FAILURE_DIAGNOSTIC_FIELDS
                    if key in event
                }
                has_snapshot = False
            safe_record.msg = _redacted_value(event)
            safe_record.args = ()
        else:
            # Do not let stdlib interpolation or the SDK call repr/str on an
            # opaque payload. Keep tuples/mappings intact until interpolation.
            safe_record.msg = _redact_nested(record.msg, seen=set())
            safe_record.args = _redact_nested(record.args, seen=set())
            if safe_record.args:
                try:
                    safe_record.msg = safe_record.getMessage()
                except (TypeError, ValueError, KeyError, OverflowError):
                    # A sensitive numeric mapping value becomes a redaction
                    # string, which cannot satisfy %d. Preserve the safe event
                    # structure rather than dropping the log or retrying raw args.
                    safe_record.msg = {
                        "message": safe_record.msg,
                        "arguments": safe_record.args,
                    }
                safe_record.args = ()

        translated = super()._translate(safe_record)
        # Redact once more after positional interpolation and exception
        # formatting, when previously separated contact text may have joined.
        translated.body = _redacted_value(translated.body)
        # These strings were rendered from already-redacted structured args.
        # Do not run free-text masking over their serialized numeric values.
        cast(dict[str, Any], translated.attributes).update(exception_attributes)
        if native and isinstance(translated.body, dict):
            if has_snapshot:
                translated.body["exception"] = _render_safe_exception(
                    translated.body["exception"]
                )
        return translated
