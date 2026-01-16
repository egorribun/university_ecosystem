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
from typing import TYPE_CHECKING

import structlog

from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from collections.abc import Callable

# Module-level flag to prevent double configuration
_configured = False


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

    # Shared processors for all logging
    shared_processors: list[Callable] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Production: JSON output with orjson
        processors = [
            *shared_processors,
            structlog.processors.JSONRenderer(serializer=_orjson_serializer),
        ]
        factory = structlog.BytesLoggerFactory()
    else:
        # Development: colored console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        factory = structlog.PrintLoggerFactory()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=factory,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


def _orjson_serializer(obj: dict, **kwargs) -> bytes:
    """Serialize log event to JSON bytes using orjson."""
    return orjson.dumps(obj)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def bind_context(**kwargs) -> None:
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
    "configure_logging",
    "get_logger",
    "bind_context",
    "clear_context",
]
