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
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import structlog

from app.core.orjson_utils import orjson

if TYPE_CHECKING:
    from collections.abc import Callable

    from structlog.typing import EventDict

# Module-level flag to prevent double configuration
_configured = False


# ---------------------------------------------------------------------------
# RZ-29-02: PII redaction processor — strips emails, phones, and sensitive
# field values from structured log events before they reach the renderer.
# This is a defense-in-depth measure; application code should avoid logging
# PII in the first place, but this processor catches accidental leaks.
# ---------------------------------------------------------------------------
# RZ-30-03: Require ≥2-char TLD and word boundaries to avoid masking
# `redis@10.0.0.1`, `user@host`, and version strings.
_EMAIL_LOCAL_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.+-"
)
_EMAIL_DOMAIN_RE = re.compile(
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
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
    r"(?<![A-Za-z0-9])v)$",
    re.IGNORECASE,
)
_PHONE_CONTEXT_RE = re.compile(
    r"\b(?:call|phone|telephone|tel|mobile|cell|contact|dial)\b$",
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


# Only canonical hyphenated UUIDs (8-4-4-4-12) bounded by non-alphanumeric
# characters are copied verbatim, so request and entity ids survive intact. Any
# other run, including a compact 32-hex string, goes through phone redaction.
# A UUID glued to an alphanumeric character is not protected. Accepted gaps: a
# phone-like digit run inside a canonical UUID shape is not redacted, and the
# phone pattern never matches inside a longer digit run.
_UUID_RE = re.compile(
    r"(?<![0-9A-Za-z])"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
    r"(?![0-9A-Za-z])",
    re.ASCII,
)


def _redact_emails(text: str) -> str:
    """Match each local-part run once, including runs after an address."""

    parts: list[str] = []
    cursor = 0
    position = 0
    while position < len(text):
        if text[position] not in _EMAIL_LOCAL_CHARACTERS:
            position += 1
            continue

        previous = text[position - 1] if position else ""
        previous_is_word = previous.isalnum() or previous == "_"
        boundary: int | None = None
        while position < len(text) and text[position] in _EMAIL_LOCAL_CHARACTERS:
            character = text[position]
            is_word = character.isalnum() or character == "_"
            if boundary is None and previous_is_word != is_word:
                boundary = position
            previous_is_word = is_word
            position += 1

        if boundary is None or position == len(text) or text[position] != "@":
            continue
        domain = _EMAIL_DOMAIN_RE.match(text, position + 1)
        if domain is not None:
            parts.append(text[cursor:boundary])
            parts.append(_PII_REPLACEMENT)
            position = domain.end()
            cursor = position
    parts.append(text[cursor:])
    return "".join(parts)


def _has_phone_context(text: str, end: int, pattern: re.Pattern[str]) -> bool:
    """Inspect only the bounded keyword immediately before a phone number."""

    while end and text[end - 1].isspace():
        end -= 1
    if end and text[end - 1] in ":=#-":
        end -= 1
        while end and text[end - 1].isspace():
            end -= 1
    # The longest context keyword is "identifier" (10 characters). The regex
    # still checks the preceding character for a word boundary or lookbehind.
    return pattern.search(text, max(0, end - 10), end) is not None


def _mask_phone_numbers(text: str) -> str:
    """Redact phone numbers in one UUID-free segment."""

    def replace_phone(match: re.Match[str]) -> str:
        explicit_non_phone_context = _has_phone_context(
            text, match.start(), _NON_PHONE_CONTEXT_RE
        )
        dotted_without_phone_context = "." in match.group() and not (
            match.group().startswith("+")
            or _has_phone_context(text, match.start(), _PHONE_CONTEXT_RE)
        )
        if explicit_non_phone_context or dotted_without_phone_context:
            return match.group()
        return _PII_REPLACEMENT

    return _PHONE_RE.sub(replace_phone, text)


def _redact_free_text(value: str) -> str:
    """Redact emails and phone numbers while preserving canonical UUIDs.

    Canonical UUID spans are copied verbatim and phone matching runs only between
    them, so a phone pattern can never be taken from inside a UUID and a phone
    number placed next to a UUID is still redacted.
    """

    redacted = _redact_emails(value)
    parts: list[str] = []
    cursor = 0
    for uuid_match in _UUID_RE.finditer(redacted):
        parts.append(_mask_phone_numbers(redacted[cursor : uuid_match.start()]))
        parts.append(uuid_match.group())
        cursor = uuid_match.end()
    parts.append(_mask_phone_numbers(redacted[cursor:]))
    return "".join(parts)


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


def _exception_control(value: Any) -> tuple[BaseException, TracebackType | None] | None:
    """Resolve real exception controls without consulting instance hooks."""
    if issubclass(type(value), BaseException):
        traceback = BaseException.__dict__["__traceback__"].__get__(value)
        return value, traceback
    if value is True:
        _, exception, traceback = sys.exc_info()
        return (exception, traceback) if exception is not None else None
    if issubclass(type(value), tuple) and _is_valid_logging_control("exc_info", value):
        return value[1], value[2]
    return None


def _safe_exception_snapshot(
    exception: BaseException,
    traceback: TracebackType | None,
    *,
    seen: set[int],
) -> dict[str, Any]:
    """Keep redacted arguments and frame locations, never source or locals.

    Built-in descriptors bypass custom exception attribute/representation hooks.
    A bounded ancestor set cuts cyclic or excessively deep exception chains.
    """
    type_name = type.__dict__["__name__"].__get__(type(exception))
    details: dict[str, Any] = {"type": _redact_free_text(type_name)}
    marker = id(exception)
    if marker in seen:
        return {**details, "cycle": True}
    if len(seen) >= 32:
        return {**details, "truncated": True}
    seen.add(marker)
    try:
        args = BaseException.__dict__["args"].__get__(exception)
        details["args"] = _redact_nested(args, seen=set())
        frames = []
        while traceback is not None:
            code = traceback.tb_frame.f_code
            frames.append(
                {
                    "file": _redact_free_text(code.co_filename),
                    "line": traceback.tb_lineno,
                    "function": _redact_free_text(code.co_name),
                }
            )
            traceback = traceback.tb_next
        details["frames"] = frames
        state = BaseException.__dict__["__dict__"].__get__(exception)
        if "__notes__" in state:
            details["notes"] = _redact_nested(state["__notes__"], seen=set())
        cause = BaseException.__dict__["__cause__"].__get__(exception)
        context = BaseException.__dict__["__context__"].__get__(exception)
        suppressed = BaseException.__dict__["__suppress_context__"].__get__(exception)
        linked = cause if cause is not None else None if suppressed else context
        if linked is not None:
            details["cause" if cause is not None else "context"] = (
                _safe_exception_snapshot(
                    linked,
                    BaseException.__dict__["__traceback__"].__get__(linked),
                    seen=seen,
                )
            )
        if issubclass(type(exception), BaseExceptionGroup):
            children = BaseExceptionGroup.__dict__["exceptions"].__get__(exception)
            details["exceptions"] = [
                _safe_exception_snapshot(
                    child,
                    BaseException.__dict__["__traceback__"].__get__(child),
                    seen=seen,
                )
                for child in children
            ]
        return details
    finally:
        seen.remove(marker)


class _ExceptionSnapshot(dict[str, Any]):
    """Internal marker, created only after structured exception redaction."""


def _exception_message(details: Mapping[str, Any]) -> str:
    args = details["args"]
    children = details.get("exceptions")
    if children:
        args = args[:1]
    message = (
        ""
        if not args
        else args[0]
        if len(args) == 1 and type(args[0]) is str
        else _orjson_serializer({"args": args})
    )
    if children:
        message += f" ({len(children)} sub-exceptions)"
    return message


def _render_safe_exception(details: Mapping[str, Any]) -> str:
    """Render conventional traceback text from the already-safe snapshot."""
    type_name = details["type"]
    if details.get("cycle"):
        return f"{type_name}: [exception cycle omitted]"
    if details.get("truncated"):
        return f"{type_name}: [exception chain truncated]"
    lines: list[str] = []
    if "cause" in details:
        lines.extend(
            (
                _render_safe_exception(details["cause"]),
                "",
                "The above exception was the direct cause of the following exception:",
                "",
            )
        )
    elif "context" in details:
        lines.extend(
            (
                _render_safe_exception(details["context"]),
                "",
                "During handling of the above exception, another exception occurred:",
                "",
            )
        )
    if details["frames"]:
        lines.append("Traceback (most recent call last):")
        for frame in details["frames"]:
            lines.append(
                f'  File "{frame["file"]}", line {frame["line"]}, in {frame["function"]}'
            )
    message = _exception_message(details)
    lines.append(f"{type_name}: {message}" if message else type_name)
    notes = details.get("notes", ())
    if not isinstance(notes, list | tuple):
        notes = (notes,)
    for note in notes:
        lines.append(note if type(note) is str else _orjson_serializer({"note": note}))
    for number, child in enumerate(details.get("exceptions", ()), start=1):
        lines.append(f"+---------------- {number} ----------------")
        lines.extend(f"  {line}" for line in _render_safe_exception(child).splitlines())
    return "\n".join(lines)


def _safe_exception_attributes(value: Any) -> dict[str, str]:
    resolved = _exception_control(value)
    if resolved is None:
        return {}
    exception, traceback = resolved
    details = _safe_exception_snapshot(exception, traceback, seen=set())
    return {
        "exception.type": cast(str, details["type"]),
        "exception.message": _exception_message(details),
        "exception.stacktrace": _render_safe_exception(details),
    }


def _format_safe_exc_info(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    resolved = _exception_control(event_dict.pop("exc_info", None))
    if resolved is not None:
        # Keep the snapshot structured until each sink's final renderer. A
        # later free-text redaction pass must not corrupt serialized numbers.
        exception, traceback = resolved
        event_dict["exception"] = _ExceptionSnapshot(
            _safe_exception_snapshot(exception, traceback, seen=set())
        )
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


# Closed schema of the request-failure diagnostic event. The owned NATS consumer
# (scripts/owned_nats_failure_diagnostic.py) must accept exactly these keys; a
# test asserts that equality so the two copies cannot drift silently.
REQUEST_FAILURE_DIAGNOSTIC_FIELDS: tuple[str, ...] = (
    "message",
    "logger",
    "diagnostic_request_id",
    "diagnostic_category",
    "diagnostic_kind",
    "diagnostic_sqlstate",
)


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
        _format_safe_exc_info,
    ]

    processors: list[Any]
    renderer: Any
    if json_output:
        # Production: JSON output with orjson (fastest serializer)
        renderer = structlog.processors.JSONRenderer(serializer=_orjson_serializer)
        processors = [
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        factory: Any = structlog.stdlib.LoggerFactory()
    else:
        # The shared chain renders safe exception snapshots in both modes.
        # Keep locals disabled as defense in depth for direct renderer usage.
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

    def render_event(logger: Any, method_name: str, event_dict: EventDict) -> str:
        # This producer owns a finite, privacy-safe schema. Keep its diagnostic
        # JSON machine-readable in development too, without changing log mode
        # or rendering inherited request/user/exception context into the event.
        if (
            event_dict.get("logger") == "app.core.request_failure_diagnostic"
            and event_dict.get("message") == "request_failure_diagnostic"
        ):
            return _orjson_serializer(
                {
                    key: event_dict[key]
                    for key in REQUEST_FAILURE_DIAGNOSTIC_FIELDS
                    if key in event_dict
                }
            )
        exception = event_dict.get("exception")
        if type(exception) is _ExceptionSnapshot:
            event_dict["exception"] = _render_safe_exception(exception)
        rendered: str = renderer(logger, method_name, event_dict)
        return rendered

    processor_formatter = structlog.stdlib.ProcessorFormatter(
        processor=render_event,
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
