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
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any
from uuid import UUID

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
# The explicit seven-digit alternatives cover common local numbers such as
# ``555-0199`` (with or without a country code) that are otherwise too short
# for the general international-number shape.  Their trailing guard avoids
# redacting only a prefix of a longer number with an extension/group.
_PHONE_RE = re.compile(
    r"(?<![.\d])(?<!\d[\s.-])"  # no embedded numeric group
    r"(?:"
    r"\+\d{1,3}[\s-]?\(?\d{3}\)?[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}"
    r"|8[\s-]?\(?\d{3}\)?[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}"
    r"|(?:\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]"
    r"\d{3}[\s.-]\d{4}(?:[\s-]\d{1,5})?"  # 10-digit + extension
    r"|\+\d{1,3}[\s-]?\d{3}[\s-]\d{4}(?![\s-]\d)"  # country + local
    r"|(?:\+\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s.-]?"  # optional country/area
    r"\d{3,4}[\s.-]?\d{2,4}"  # first + second groups
    r"|\(?\d{3}\)?[\s-]\d{4}(?:[\s-]\d{1,5})?"  # local + extension
    r")"
    r"(?!\d|[.-]\d|[\s-]\d)"  # no numeric or numeric-separator suffix
)
_NON_PHONE_CONTEXT_RE = re.compile(
    r"(?:\b(?:version|ver|build|release|id|identifier|ticket|record)\b|"
    r"(?<![A-Za-z0-9])v)\s*[:=#-]?\s*$",
    re.IGNORECASE,
)
_PHONE_CONTEXT_RE = re.compile(
    r"\b(?:call|phone|telephone|tel|mobile|cell|contact|dial)\b"
    r"\s*[:=#-]?\s*$",
    re.IGNORECASE,
)
_PII_FIELD_NAMES = frozenset(
    {
        "email",
        "phone",
        "phone_number",
        "mobile_phone",
        "ssn",
        "password",
        "password_hash",
        "secret",
        "secret_key",
        "credential",
        "credentials",
        "client_secret",
        "credit_card",
        "card_number",
        "passport",
        "token",
        "authorization",
        "proxy_authorization",
        "access_token",
        "refresh_token",
        "reset_token",
        "id_token",
        "session_token",
        "session",
        "session_id",
        "session_cookie",
        "csrf_token",
        "csrf_hmac_secret",
        "x_csrf_token",
        "cookie",
        "set_cookie",
        "api_key",
        "x_api_key",
        "private_key",
        "signing_key",
        "jwt_signing_keys",
        "jwt_signing_key_registry",
        "vapid_private_key",
        "spicedb_preshared_key",
        "storage_s3_secret_access_key",
        "mfa_totp_encryption_keys",
        "mfa_email_otp_hmac_keys",
        "mfa_email_delivery_keks",
        "mfa_trusted_device_hmac_keys",
        "imgproxy_key",
        "imgproxy_salt",
        "database_url",
        "database_read_replica_url",
        "cache_redis_url",
        "revocation_redis_url",
        "rate_limit_storage_uri",
        "nats_url",
        "cwv_manual_tester_user_ids",
        "internal_signature",
        "x_internal_signature",
        "otp",
        "otpauth_url",
        "one_time_code",
        "recovery_code",
        "ticket",
        "nonce",
        "signature",
    }
)
_PII_REPLACEMENT = "[REDACTED]"


def _normalize_field_name(value: str) -> str:
    """Normalize snake/kebab/camel/Pascal-case keys for PII matching."""

    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


def _is_pii_field_name(value: object) -> bool:
    """Return whether a structured field name is credential/PII-bearing."""

    if not isinstance(value, str):
        return False
    normalized = _normalize_field_name(value)
    # Match terminal words, not metadata such as token_type or secret_name.
    return normalized in _PII_FIELD_NAMES or normalized.endswith(
        ("_token", "_secret", "_password")
    )


def _redact_free_text(value: str) -> str:
    """Redact emails and phone numbers while preserving explicit numeric tokens."""

    redacted = _EMAIL_RE.sub(_PII_REPLACEMENT, value)

    def replace_phone(match: re.Match[str]) -> str:
        prefix = redacted[: match.start()]
        explicit_non_phone_context = _NON_PHONE_CONTEXT_RE.search(prefix) is not None
        dotted_without_phone_context = "." in match.group() and not (
            match.group().startswith("+")
            or _PHONE_CONTEXT_RE.search(prefix) is not None
        )
        if explicit_non_phone_context or dotted_without_phone_context:
            return match.group()
        return _PII_REPLACEMENT

    return _PHONE_RE.sub(replace_phone, redacted)


def _redact_nested(value: Any, *, seen: set[int]) -> Any:
    """Copy supported structured values, redacting fields without caller mutation.

    Only mappings, lists and tuples are traversed. Other payload objects stay
    opaque: do not discover their properties or call representation, model or
    copy hooks. The scalar exceptions are the concrete UUID/datetime metadata
    used by application loggers and ordinary JSON scalar values. Mapping entries
    with non-native-string keys are omitted without converting field names.
    Classification uses actual types, not instance __class__ properties.

    The seen set tracks only active ancestors, so cycles are cut without treating
    repeated references to the same non-cyclic payload as secret or cyclic.
    """
    value_type = type(value)
    if issubclass(value_type, str):
        return _redact_free_text(value)
    if value is None or value_type in (bool, int, float, UUID, datetime):
        return value
    if not issubclass(value_type, Mapping | list | tuple):
        return _PII_REPLACEMENT

    marker = id(value)
    if marker in seen:
        return _PII_REPLACEMENT
    seen.add(marker)
    try:
        if issubclass(value_type, Mapping):
            return {
                key: (
                    _PII_REPLACEMENT
                    if _is_pii_field_name(key)
                    else _redact_nested(item, seen=seen)
                )
                for key, item in value.items()
                if type(key) is str
            }
        items = [_redact_nested(item, seen=seen) for item in value]
        return tuple(items) if issubclass(value_type, tuple) else items
    finally:
        seen.discard(marker)


def _is_valid_logging_control(key: str, value: Any) -> bool:
    """Recognize actual framework types without reading instance properties."""
    value_type = type(value)
    if key == "exc_info":
        if value_type is bool or issubclass(value_type, BaseException):
            return True
        if not issubclass(value_type, tuple) or len(value) != 3:
            return False
        exception_type, exception, traceback = value
        return (
            issubclass(type(exception_type), type)
            and issubclass(exception_type, BaseException)
            and issubclass(type(exception), BaseException)
            and (traceback is None or issubclass(type(traceback), TracebackType))
        )
    if key == "_record":
        return issubclass(value_type, logging.LogRecord)
    if key == "_from_structlog":
        return value_type is bool
    # ProcessorFormatter passes a preformatted stdlib stack string; native
    # structlog calls pass a bool. Do not truth-test other object values.
    return value_type in (bool, str)


def _redact_pii(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Return a redacted event without changing caller-owned data.

    Sensitive fields are replaced entirely; string values retain email/phone
    masking. Genuine top-level logging controls remain available to subsequent
    processors. Invalid controls are dropped, not rendered or truth-tested.
    Nested values never gain a control exemption from their field names. Only
    native string keys are retained, matching the configured renderers' contract.
    """
    redacted: dict[str, Any] = {}
    seen = {id(event_dict)}
    for key, value in event_dict.items():
        if type(key) is not str:
            continue
        if key in ("exc_info", "_record", "_from_structlog", "stack_info"):
            if _is_valid_logging_control(key, value):
                redacted[key] = value
            continue
        redacted[key] = (
            _PII_REPLACEMENT
            if _is_pii_field_name(key)
            else _redact_nested(value, seen=seen)
        )
    return redacted


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
    renderer: Any
    if json_output:
        # Production: JSON output with orjson (fastest serializer)
        renderer = structlog.processors.JSONRenderer(serializer=_orjson_serializer)
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            # JSON needs a serializable exception string. ConsoleRenderer
            # handles ``exc_info`` itself and warns if it is pre-formatted.
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        factory: Any = structlog.stdlib.LoggerFactory()
    else:
        # Development: keep rich tracebacks, but never render frame locals.
        # Locals routinely contain credentials, reset links and request payloads;
        # showing them would bypass the structured-log redaction processors.
        safe_traceback = structlog.dev.RichTracebackFormatter(show_locals=False)
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=safe_traceback,
        )
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        factory = structlog.stdlib.LoggerFactory()

    structlog.configure(
        processors=processors,
        logger_factory=factory,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to bridge into structlog.  Existing stdlib
    # loggers (including auth/audit modules that have not yet migrated to
    # ``get_logger``) must pass through the same redaction/context chain.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    foreign_pre_chain = list(shared_processors)
    if json_output:
        foreign_pre_chain.append(structlog.processors.format_exc_info)
    processor_formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=foreign_pre_chain,
    )
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setFormatter(processor_formatter)

    # OpenTelemetry logger ownership lives in ``app.core.observability``.
    # Keeping provider creation out of this low-level structlog setup prevents
    # a hidden second BatchLogRecordProcessor from leaking exporter threads.


def _log_json_default(value: Any) -> str:
    """Keep known scalar metadata usable in the stdlib JSON fallback."""
    if type(value) in (UUID, datetime):
        return str(value)
    return _PII_REPLACEMENT


def _orjson_serializer(obj: dict[str, Any], **kwargs: Any) -> str:
    """Serialize redacted events without invoking unknown representations."""
    return orjson.dumps(obj, default=_log_json_default).decode("utf-8")


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    from typing import cast

    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def get_stdlib_logger(name: str | None = None) -> logging.Logger:
    """Return a stdlib logger whose records are processed by our bridge.

    A small number of compatibility-facing emitters (notably the audit
    service) intentionally pass a JSON audit payload as ``record.msg`` so
    existing log consumers can parse it losslessly.  They still use this
    helper rather than calling ``logging.getLogger`` directly: once
    :func:`configure_logging` installs ``ProcessorFormatter`` on the root
    handlers, these records receive the same redaction, context and renderer
    chain as native structlog events.
    """
    return logging.getLogger(name)


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
    "get_stdlib_logger",
    "is_logger_enabled",
]
