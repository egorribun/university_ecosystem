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
import sys
from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import settings
from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from collections.abc import Callable

# Module-level flag to prevent double configuration
_configured = False


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
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_otel_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.EventRenamer("message"),
        # Add service context to every log record
        lambda _, __, event_dict: (
            event_dict.update({"service": "backend", "environment": getattr(settings, "environment", "production")}) or event_dict
        ),
    ]

    processors: list[Any]
    if json_output:
        # Production: JSON output with orjson (fastest serializer)
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.JSONRenderer(serializer=_orjson_serializer),
        ]
        factory: Any = structlog.stdlib.LoggerFactory()
    else:
        # Development: colored console output with better human readability
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
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


def _orjson_serializer(obj: dict[str, Any], **kwargs: Any) -> bytes:
    """Serialize log event to JSON bytes using orjson."""
    return orjson.dumps(obj)


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


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


__all__ = [
    "bind_context",
    "clear_context",
    "configure_logging",
    "get_logger",
]
