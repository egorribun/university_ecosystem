"""Structured logging configuration using structlog.

This module configures structlog for high-performance structured JSON logging
with orjson renderer. It integrates with Python's standard logging module
and provides consistent log formatting across the application.

Key features:
- JSON output with orjson (fastest serializer)
- ISO 8601 timestamps in UTC
- Automatic context variable merging
- Request ID tracking via contextvars
- Exception formatting with tracebacks
"""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING, Any

import structlog

from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from collections.abc import Callable

# Module-level flag to prevent double configuration
_configured = False


# ---------------------------------------------------------------------------
# RZ-29-02: PII redaction processor — strips emails, phones, and sensitive
# field values from structured log events before they reach the renderer.
# This is a defense-in-depth measure; application code should avoid logging
# PII in the first place, but this processor catches accidental leaks.
# ---------------------------------------------------------------------------
# RZ-30-03: Tighter email regex — require ≥2-char TLD, word boundaries.
# Prevents false positives on `redis@10.0.0.1`, `user@host`, version strings.
_EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z]{2,})+\b"
)
# RZ-30-04: Anchored phone regex — negative lookbehind/lookahead reject
# timestamps (2026-03-25), IPs (192.168.1.1), and version-like sequences.
_PHONE_RE = re.compile(
    r"(?<![.\d])"  # no preceding dot/digit
    r"(?:\+\d{1,3}[\s-]?)?"  # optional country code
    r"\(?\d{2,4}\)?[\s.-]?"  # area code
    r"\d{3,4}[\s.-]?"  # first group
    r"\d{2,4}"  # second group
    r"(?![.\d])"  # no trailing dot/digit
)
_PII_FIELD_NAMES = frozenset(
    {
        "email",
        "phone",
        "phone_number",
        "ssn",
        "password",
        "secret",
        "credit_card",
        "card_number",
        "passport",
        "token",
    }
)
_PII_REPLACEMENT = "[REDACTED]"


def _redact_pii(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Redact PII from log event dicts.

    - Field-level: keys matching _PII_FIELD_NAMES are replaced entirely.
    - Value-level: email/phone patterns in string values are masked.
    """
    for key in list(event_dict):
        if key in _PII_FIELD_NAMES:
            event_dict[key] = _PII_REPLACEMENT
            continue
        value = event_dict[key]
        if isinstance(value, str) and len(value) > 5:
            value = _EMAIL_RE.sub(_PII_REPLACEMENT, value)
            value = _PHONE_RE.sub(_PII_REPLACEMENT, value)
            if value != event_dict[key]:
                event_dict[key] = value
    return event_dict


def add_otel_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add OpenTelemetry trace and span IDs to the log event."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            ctx = span.get_span_context()
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass
    return event_dict


def _add_service_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add static service context fields to every log record.

    MED-W19: Replaces the lambda-with-side-effect pattern.  Using a named
    function avoids the ``expr.update(...) or expr`` idiom which is
    non-obvious, harder to test, and cannot be inspected by structlog's
    processor introspection tools.
    """
    from app.core.config import settings  # deferred: avoid circular import

    event_dict["service"] = "backend"
    event_dict["environment"] = getattr(settings, "environment", "production")
    return event_dict


def configure_logging(
    *,
    level: int = logging.INFO,
    json_output: bool = True,
) -> None:
    """Configure structlog for the application.

    Args:
        level: Minimum log level (default: INFO)
        json_output: If True, output JSON; if False, output colored console
    """
    global _configured
    if _configured:
        return
    _configured = True

    # Shared processors for all logging — used by both structlog and stdlib (if bridged)
    shared_processors: list[Callable[..., Any]] = [
        # Pulls bound variables from structlog.contextvars into the event_dict.
        # This is where request_id, user_id, etc. are injected.
        structlog.contextvars.merge_contextvars,
        _redact_pii,  # RZ-29-02: strip PII before any renderer sees the data
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_otel_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        # Format stdlib-style positional arguments before EventRenamer moves
        # the event field to `message`. Without this, console/testing output
        # raises KeyError("event") for calls such as logger.info("size=%s", n).
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.EventRenamer("message"),
        # MED-W19: named processor instead of lambda with side-effect
        _add_service_context,
    ]

    processors: list[Any]
    if json_output:
        # Production: JSON output with orjson (fastest serializer)
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            # JSON needs a serializable exception string. ConsoleRenderer
            # handles ``exc_info`` itself and warns if it is pre-formatted.
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(serializer=_orjson_serializer),
        ]
        factory: Any = structlog.stdlib.LoggerFactory()
    else:
        # Development: keep rich tracebacks, but never render frame locals.
        # Locals routinely contain credentials, reset links and request payloads;
        # showing them would bypass the structured-log redaction processors.
        safe_traceback = structlog.dev.RichTracebackFormatter(show_locals=False)
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=safe_traceback,
            ),
        ]
        factory = structlog.stdlib.LoggerFactory()

    structlog.configure(
        processors=processors,
        logger_factory=factory,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to bridge into structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # MOD-6 (audit 2026-03-05): Bridge stdlib logging into the OTel SDK so that
    # every log record is correlated with active traces (trace_id / span_id) in
    # Grafana Tempo / OTLP backends. Requires opentelemetry-sdk ≥ 1.20.
    # Gracefully no-ops when OTel SDK is absent (dev, test environments).
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs._internal.export.otlp import OTLPLogExporter
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        _log_provider = LoggerProvider()
        set_logger_provider(_log_provider)
        _log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter())
        )
        # Instruments Python root logger → OTel bridge (adds trace_id / span_id
        # as log record attributes recognised by Grafana Tempo).
        LoggingInstrumentor().instrument(set_logging_format=False)
    except ImportError:
        # OTel SDK not installed (local dev / test) — structlog still works.
        pass


def _orjson_serializer(obj: dict[str, Any], **kwargs: Any) -> str:
    """Serialize log event to JSON string using orjson."""
    return orjson.dumps(obj, default=str).decode("utf-8")


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    from typing import cast

    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def bind_context(**kwargs: Any) -> None:
    """Bind context variables for the current async context.

    Bound variables will be included in all log messages within the
    current asyncio task.

    Example:
        bind_context(request_id="abc123", user_id=42)
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def is_logger_enabled(logger: Any, level: int) -> bool:
    """Check if a logger is enabled for a given level.

    Works for both standard logging.Logger (isEnabledFor) and
    structlog's make_filtering_bound_logger (is_enabled_for)
    at runtime, while bridging the gap between local and CI
    mypy environments.
    """
    # PEP 8 compliant method name used by structlog filtering
    if hasattr(logger, "is_enabled_for"):
        return bool(logger.is_enabled_for(level))
    # Standard library method name
    return bool(logger.isEnabledFor(level))


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


__all__ = [
    "bind_context",
    "clear_context",
    "configure_logging",
    "get_logger",
    "is_logger_enabled",
]
