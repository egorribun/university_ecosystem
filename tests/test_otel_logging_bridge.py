"""The real OTel export boundary must not bypass central log redaction."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import StringIO
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common._internal._log_encoder import encode_logs
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

import app.core.logging as logging_mod
import app.core.observability as observability


@pytest.fixture(autouse=True)
def restore_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    root = logging.getLogger()
    handlers = root.handlers[:]
    formatters = [(handler, handler.formatter) for handler in handlers]
    level = root.level
    logger_class = logging.getLoggerClass()
    configuration = structlog.get_config()
    context = structlog.contextvars.get_contextvars()
    monkeypatch.setattr(logging_mod, "_configured", False)
    structlog.contextvars.clear_contextvars()
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        for handler, formatter in formatters:
            handler.setFormatter(formatter)
        logging.setLoggerClass(logger_class)
        structlog.configure(**configuration)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(**context)


@contextmanager
def pipeline(
    *, json_output: bool = True, otel_first: bool = False
) -> Iterator[tuple[InMemoryLogRecordExporter, StringIO]]:
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider(shutdown_on_exit=False)
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    output = StringIO()
    console = logging.StreamHandler(output)
    root = logging.getLogger()
    root.addHandler(console)
    root.setLevel(logging.INFO)
    logging_mod.configure_logging(json_output=json_output)
    # The existing SDK constructor is deprecated. Assert that known upstream
    # warning explicitly; export-time warnings are never filtered or suppressed.
    with pytest.warns(DeprecationWarning, match="LoggingHandler"):
        handler = observability.LoggingHandler(logger_provider=provider)
    if otel_first:
        root.handlers.insert(0, handler)
    else:
        root.addHandler(handler)
    try:
        yield exporter, output
        wire = encode_logs(exporter.get_finished_logs()).SerializeToString()
        assert wire
        assert b"a@b.cc" not in wire
        assert b"+1 555 123 4567" not in wire
        assert b"synthetic-value" not in wire
    finally:
        root.removeHandler(handler)
        root.removeHandler(console)
        handler.close()
        console.close()
        provider.shutdown()


def exported(exporter: InMemoryLogRecordExporter, name: str) -> Any:
    matches = [
        item.log_record
        for item in exporter.get_finished_logs()
        if item.instrumentation_scope.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def structured_exception_args(text: str, exception_type: str) -> list[Any]:
    prefix = f"{exception_type}: "
    line = next(
        line.strip() for line in text.splitlines() if line.strip().startswith(prefix)
    )
    return json.loads(line.removeprefix(prefix))["args"]


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("otel_first", [True, False], ids=["otel-first", "otel-last"])
def test_native_export_omits_transport_fields_without_mutating_console_record(
    caplog: pytest.LogCaptureFixture, json_output: bool, otel_first: bool
) -> None:
    name = "otel-bridge-native"
    payload = {"note": "mail a@b.cc", "attempts": [1, 2]}
    with pipeline(json_output=json_output, otel_first=otel_first) as (sink, console):
        logging_mod.bind_context(request_id="public-request", email="a@b.cc")
        logging_mod.get_logger(name).info("bridge probe", payload=payload)
        record = exported(sink, name)
        assert record.body["message"] == "bridge probe"
        assert record.body["request_id"] == "public-request"
        assert record.body["email"] == "[REDACTED]"
        assert record.body["payload"] == {
            "note": "mail [REDACTED]",
            "attempts": [1, 2],
        }
        assert {"_logger", "_name", "_record", "_from_structlog"}.isdisjoint(
            record.attributes
        )
        assert record.attributes["code.function.name"] == (
            "test_native_export_omits_transport_fields_without_mutating_console_record"
        )
        assert record.attributes["code.line.number"] > 0
        assert record.severity_text == "INFO"
        assert "bridge probe" in console.getvalue()
        assert "a@b.cc" not in console.getvalue()
        assert len(sink.get_finished_logs()) == 1
    assert payload == {"note": "mail a@b.cc", "attempts": [1, 2]}
    source = next(r for r in caplog.records if r.name == name)
    assert isinstance(source.__dict__["_logger"], logging.Logger)
    assert source.__dict__["_name"] == "info"
    assert not [r for r in caplog.records if "Invalid type" in r.getMessage()]


def test_stdlib_body_and_nested_extras_are_redacted_without_mutation() -> None:
    name = "otel-bridge-stdlib"
    payload = {"authorization": "synthetic-value", "items": [{"email": "a@b.cc"}]}
    with pipeline() as (sink, _):
        logging_mod.get_stdlib_logger(name).warning(
            "contact %s or %s",
            "a@b.cc",
            "+1 555 123 4567",
            extra={"payload": payload, "authorization": "synthetic-value", "count": 7},
        )
        record = exported(sink, name)
        assert record.body == "contact [REDACTED] or [REDACTED]"
        assert record.attributes["authorization"] == "[REDACTED]"
        assert record.attributes["payload"] == {
            "authorization": "[REDACTED]",
            "items": ({"email": "[REDACTED]"},),
        }
        assert record.attributes["count"] == 7
        assert record.severity_text == "WARN"
    assert payload == {
        "authorization": "synthetic-value",
        "items": [{"email": "a@b.cc"}],
    }


class OpaquePayload:
    def __str__(self) -> str:
        raise AssertionError("opaque __str__ must not be invoked")

    def __repr__(self) -> str:
        raise AssertionError("opaque __repr__ must not be invoked")


@pytest.mark.parametrize("message", ["payload %s", OpaquePayload()])
def test_opaque_values_never_reach_sdk_stringification(message: Any) -> None:
    name = "otel-bridge-opaque"
    with pipeline() as (sink, _):
        # Send directly to the installed OTel handler: unrelated legacy stream
        # formatters are outside this export-boundary contract.
        handler = observability.LoggingHandler
        active = next(h for h in logging.getLogger().handlers if isinstance(h, handler))
        args = (OpaquePayload(),) if isinstance(message, str) else ()
        record = logging.LogRecord(name, logging.INFO, __file__, 1, message, args, None)
        record.payload = OpaquePayload()
        active.handle(record)
        result = exported(sink, name)
        assert result.body == ("payload [REDACTED]" if args else "[REDACTED]")
        assert result.attributes["payload"] == "[REDACTED]"
        assert record.msg is message
        assert record.args == args


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_exception_exports_keep_diagnostics_without_contact_data(
    json_output: bool, native: bool
) -> None:
    name = "otel-bridge-exception"
    with pipeline(json_output=json_output) as (sink, _):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        try:
            raise ValueError("mail a@b.cc or phone +1 555 123 4567")
        except ValueError:
            logger.exception("operation failed")
        record = exported(sink, name)
        serialized = json.dumps(
            {"body": record.body, "attributes": dict(record.attributes)}
        )
        assert "a@b.cc" not in serialized
        assert "+1 555 123 4567" not in serialized
        assert "ValueError" in serialized
        assert "operation failed" in serialized
        assert "[REDACTED]" in serialized
        assert record.severity_text == "ERROR"
        if native:
            assert "exc_info" not in record.body
            assert "ValueError" in record.body["exception"]
        else:
            assert record.attributes["exception.type"] == "ValueError"
            assert record.attributes["exception.message"] == (
                "mail [REDACTED] or phone [REDACTED]"
            )


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_exception_structured_credentials_are_redacted_before_stringification(
    json_output: bool,
    native: bool,
) -> None:
    name = "otel-bridge-structured-exception"
    payload = {
        "authorization": "synthetic-value",
        "count": 7,
        "opaque": OpaquePayload(),
    }
    error = ValueError(payload)
    with pipeline(json_output=json_output) as (sink, console):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        try:
            raise error
        except ValueError:
            logger.exception("operation failed")
        result = exported(sink, name)
        text = (
            result.body["exception"]
            if native
            else result.attributes["exception.stacktrace"]
        )
        assert text.startswith("Traceback (most recent call last):")
        assert structured_exception_args(text, "ValueError") == [
            {"authorization": "[REDACTED]", "count": 7, "opaque": "[REDACTED]"}
        ]
        assert (
            "in test_exception_structured_credentials_are_redacted_before_stringification"
            in text
        )
        assert "synthetic-value" not in console.getvalue()
        assert "ValueError" in console.getvalue()
        assert "opaque __repr__" not in console.getvalue()
    assert error.args[0] is payload
    assert payload["authorization"] == "synthetic-value"


class HostileException(ValueError):
    def __str__(self) -> str:
        raise AssertionError("exception __str__ must not be called")

    def __repr__(self) -> str:
        raise AssertionError("exception __repr__ must not be called")

    def __getattribute__(self, name: str) -> Any:
        if name in {
            "args",
            "__traceback__",
            "__cause__",
            "__context__",
            "__suppress_context__",
            "__notes__",
            "__dict__",
        }:
            raise AssertionError("exception attribute hooks must not be called")
        return super().__getattribute__(name)


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_exception_representation_and_attribute_hooks_are_never_called(
    json_output: bool,
    native: bool,
) -> None:
    name = "otel-bridge-hostile-exception"
    error = HostileException({"authorization": "synthetic-value", "count": 7})
    with pipeline(json_output=json_output) as (sink, console):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        invoked_hook = False
        try:
            raise error
        except HostileException:
            try:
                logger.exception("operation failed")
            except AssertionError:
                invoked_hook = True
        # Assert outside the active except block, so a broken implementation
        # cannot make pytest stringify the intentionally hostile exception.
        assert not invoked_hook, "logging invoked an opaque exception hook"
        result = exported(sink, name)
        text = (
            result.body["exception"]
            if native
            else result.attributes["exception.stacktrace"]
        )
        assert text.startswith("Traceback (most recent call last):")
        assert structured_exception_args(text, "HostileException") == [
            {"authorization": "[REDACTED]", "count": 7}
        ]
        assert "synthetic-value" not in console.getvalue()
        assert "HostileException" in console.getvalue()


@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_exception_groups_keep_redacted_causes_notes_and_child_types(
    native: bool,
) -> None:
    name = "otel-bridge-exception-group"
    cause = ValueError({"authorization": "synthetic-value"})
    cause.add_note("contact a@b.cc")
    outer = RuntimeError("safe outer")
    outer.__cause__ = cause
    group = ExceptionGroup("safe group", [outer, TypeError("safe child")])
    with pipeline() as (sink, console):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        try:
            raise group
        except ExceptionGroup:
            logger.exception("operation failed")
        result = exported(sink, name)
        text = (
            result.body["exception"]
            if native
            else result.attributes["exception.stacktrace"]
        )
        assert "ExceptionGroup: safe group (2 sub-exceptions)" in text
        assert "RuntimeError: safe outer" in text
        assert structured_exception_args(text, "ValueError") == [
            {"authorization": "[REDACTED]"}
        ]
        assert "contact [REDACTED]" in text
        assert "TypeError: safe child" in text
        assert (
            text.index("ValueError:")
            < text.index("The above exception was the direct cause")
            < text.index("RuntimeError:")
        )
        assert "synthetic-value" not in console.getvalue()


@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_cyclic_exception_cause_does_not_break_export(native: bool) -> None:
    name = "otel-bridge-exception-cycle"
    error = ValueError("safe reason")
    error.__cause__ = error
    with pipeline() as (sink, _):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        try:
            raise error
        except ValueError:
            logger.exception("operation failed")
        result = exported(sink, name)
        text = (
            result.body["exception"]
            if native
            else result.attributes["exception.stacktrace"]
        )
        assert "ValueError: [exception cycle omitted]" in text
        assert "ValueError: safe reason" in text


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_exception_rendering_preserves_numeric_argument_structure(
    json_output: bool,
    native: bool,
) -> None:
    name = "otel-bridge-numeric-exception"
    error = ValueError({"count": 1234567})
    with pipeline(json_output=json_output) as (sink, console):
        logger = (
            logging_mod.get_logger(name)
            if native
            else logging_mod.get_stdlib_logger(name)
        )
        try:
            raise error
        except ValueError:
            logger.exception("operation failed")
        result = exported(sink, name)
        text = (
            result.body["exception"]
            if native
            else result.attributes["exception.stacktrace"]
        )
        assert structured_exception_args(text, "ValueError") == [{"count": 1234567}]
        if json_output:
            assert structured_exception_args(
                json.loads(console.getvalue())["exception"], "ValueError"
            ) == [{"count": 1234567}]


def test_structured_stdlib_body_keeps_safe_scalars_and_redacts_nested_controls() -> (
    None
):
    name = "otel-bridge-structured"
    value = {
        "count": 7,
        "ok": True,
        "none": None,
        "ratio": 0.5,
        "uuid": UUID("01234567-89ab-cdef-0123-456789abcdef"),
        "at": datetime(2026, 11, 5, tzinfo=UTC),
        "nested": {"_record": OpaquePayload(), "exc_info": OpaquePayload()},
    }
    with pipeline() as (sink, _):
        active = next(
            h
            for h in logging.getLogger().handlers
            if isinstance(h, observability.LoggingHandler)
        )
        active.handle(
            logging.LogRecord(name, logging.INFO, __file__, 1, value, (), None)
        )
        record = exported(sink, name)
        assert record.body == {
            "count": 7,
            "ok": True,
            "none": None,
            "ratio": 0.5,
            "uuid": "01234567-89ab-cdef-0123-456789abcdef",
            "at": "2026-11-05T00:00:00+00:00",
            "nested": {"_record": "[REDACTED]", "exc_info": "[REDACTED]"},
        }


def test_trace_correlation_survives_export_redaction() -> None:
    name = "otel-bridge-trace"
    context = trace.SpanContext(
        trace_id=17, span_id=23, is_remote=False, trace_flags=trace.TraceFlags(1)
    )
    with pipeline() as (sink, _), trace.use_span(trace.NonRecordingSpan(context)):
        logging_mod.get_logger(name).info("trace probe")
        record = exported(sink, name)
        assert record.trace_id == 17
        assert record.span_id == 23
        assert record.trace_flags == 1


def test_contacts_joined_by_positional_formatting_are_redacted() -> None:
    name = "otel-bridge-interpolation"
    with pipeline() as (sink, _):
        logging_mod.get_stdlib_logger(name).info("%s@%s", "a", "b.cc")
        assert exported(sink, name).body == "[REDACTED]"


def test_redacted_numeric_mapping_arguments_keep_the_log_without_raw_fallback() -> None:
    name = "otel-bridge-numeric-secret"
    arguments = {"otp": 123456, "count": 7}
    with pipeline() as (sink, _):
        logging_mod.get_stdlib_logger(name).info(
            "otp=%(otp)06d count=%(count)d", arguments
        )
        result = exported(sink, name)
        assert result.body == {
            "message": "otp=%(otp)06d count=%(count)d",
            "arguments": {"otp": "[REDACTED]", "count": 7},
        }
        assert (
            b"123456" not in encode_logs(sink.get_finished_logs()).SerializeToString()
        )
    assert arguments == {"otp": 123456, "count": 7}


@pytest.mark.parametrize("count", [-1, 1114112])
def test_numeric_character_overflow_keeps_safe_structured_export(
    count: int, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "otel-bridge-character-overflow"
    arguments = {"otp": 123456, "count": count}
    with pipeline() as (sink, console):
        logging_mod.get_stdlib_logger(name).info("value=%(count)c", arguments)
        assert exported(sink, name).body == {
            "message": "value=%(count)c",
            "arguments": {"otp": "[REDACTED]", "count": count},
        }
        assert "123456" not in console.getvalue()
        assert (
            b"123456" not in encode_logs(sink.get_finished_logs()).SerializeToString()
        )
        assert capsys.readouterr().err == ""
    assert arguments == {"otp": 123456, "count": count}


@pytest.mark.parametrize("count", [-1, 1114112])
def test_numeric_formatter_overflow_keeps_safe_message_and_attributes(
    count: int, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "otel-bridge-formatter-overflow"
    with pipeline() as (sink, _):
        handler = next(
            h
            for h in logging.getLogger().handlers
            if isinstance(h, observability.LoggingHandler)
        )
        handler.setFormatter(logging.Formatter("%(count)c %(message)s"))
        logging_mod.get_stdlib_logger(name).info(
            "event", extra={"otp": 123456, "count": count}
        )
        result = exported(sink, name)
        assert result.body == "event"
        assert result.attributes["otp"] == "[REDACTED]"
        assert result.attributes["count"] == count
        assert (
            b"123456" not in encode_logs(sink.get_finished_logs()).SerializeToString()
        )
        assert capsys.readouterr().err == ""


def test_handler_formatter_cannot_reintroduce_sensitive_extras() -> None:
    name = "otel-bridge-formatter"
    with pipeline() as (sink, _):
        handler = next(
            h
            for h in logging.getLogger().handlers
            if isinstance(h, observability.LoggingHandler)
        )
        handler.setFormatter(logging.Formatter("%(message)s auth=%(authorization)s"))
        logging_mod.get_stdlib_logger(name).info(
            "event", extra={"authorization": "synthetic-value"}
        )
        result = exported(sink, name)
        assert result.body == "event auth=[REDACTED]"
        assert result.attributes["authorization"] == "[REDACTED]"


def test_numeric_formatter_keeps_safe_message_and_structured_attributes() -> None:
    name = "otel-bridge-numeric-formatter"
    with pipeline() as (sink, _):
        handler = next(
            h
            for h in logging.getLogger().handlers
            if isinstance(h, observability.LoggingHandler)
        )
        handler.setFormatter(logging.Formatter("%(message)s otp=%(otp)06d"))
        logging_mod.get_stdlib_logger(name).info("event", extra={"otp": 123456})
        result = exported(sink, name)
        assert result.body == "event"
        assert result.attributes["otp"] == "[REDACTED]"
        assert (
            b"123456" not in encode_logs(sink.get_finished_logs()).SerializeToString()
        )


def test_cyclic_extras_are_cut_without_mutating_shared_values() -> None:
    name = "otel-bridge-cycles"
    shared = {"email": "a@b.cc", "count": 3}
    payload: dict[str, Any] = {"left": shared, "right": shared}
    payload["cycle"] = payload
    with pipeline() as (sink, _):
        logging_mod.get_stdlib_logger(name).info("cycle probe", extra={"data": payload})
        assert exported(sink, name).attributes["data"] == {
            "left": {"email": "[REDACTED]", "count": 3},
            "right": {"email": "[REDACTED]", "count": 3},
            "cycle": "[REDACTED]",
        }
    assert shared == {"email": "a@b.cc", "count": 3}
    assert payload["left"] is payload["right"] is shared
    assert payload["cycle"] is payload


def test_observability_installs_redacting_handler_in_real_batch_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    sink = InMemoryLogRecordExporter()
    settings = SimpleNamespace(
        enable_otel=True,
        enable_otel_logs=True,
        enable_otel_metrics=False,
        otel_service_name="bridge-test",
        environment="testing",
        service_version="1.0.0",
        otel_trace_sampler_ratio=1.0,
        otel_exporter_otlp_headers="",
        otel_exporter_otlp_endpoint="",
    )
    monkeypatch.setattr(observability, "settings", settings)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    for field in ("_otel_shutdown", "_otel_configured", "_sqlalchemy_instrumented"):
        monkeypatch.setattr(observability, field, False)
    for field in (
        "_otel_tracer_provider",
        "_otel_meter_provider",
        "_otel_logger_provider",
        "_otel_logging_handler",
    ):
        monkeypatch.setattr(observability, field, None)
    monkeypatch.setattr(observability, "OTLPLogExporter", lambda **_: sink)
    monkeypatch.setattr(
        observability, "OTLPSpanExporter", lambda **_: InMemorySpanExporter()
    )
    monkeypatch.setattr(observability, "BatchSpanProcessor", SimpleSpanProcessor)
    # Keep providers, the real batch log processor, and the handler real. Only
    # replace network sinks, unrelated instrumentation, and write-once globals.
    for name in (
        "SQLAlchemyInstrumentor",
        "RedisInstrumentor",
        "HTTPXClientInstrumentor",
    ):
        monkeypatch.setattr(
            observability, name, lambda: SimpleNamespace(instrument=lambda **_: None)
        )
    monkeypatch.setattr(observability.trace, "set_tracer_provider", lambda _: None)
    monkeypatch.setattr(observability.metrics, "set_meter_provider", lambda _: None)
    monkeypatch.setattr(observability, "set_logger_provider", lambda _: None)
    monkeypatch.setattr(observability, "set_global_textmap", lambda _: None)
    try:
        with pytest.warns(DeprecationWarning, match="LoggingHandler"):
            observability._configure_otel(SimpleNamespace(sync_engine=object()))
        logging.getLogger().setLevel(logging.INFO)
        logging_mod.get_stdlib_logger("otel-configured-pipeline").info(
            "mail a@b.cc", extra={"authorization": "synthetic-value"}
        )
        assert observability._otel_logger_provider.force_flush()
        result = exported(sink, "otel-configured-pipeline")
        assert result.body == "mail [REDACTED]"
        assert result.attributes["authorization"] == "[REDACTED]"
        wire = encode_logs(sink.get_finished_logs()).SerializeToString()
        assert b"a@b.cc" not in wire and b"synthetic-value" not in wire
    finally:
        observability.shutdown_observability()


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
def test_owned_diagnostic_keeps_its_closed_schema_in_exports(json_output: bool) -> None:
    name = "app.core.request_failure_diagnostic"
    with pipeline(json_output=json_output) as (sink, _):
        logging_mod.bind_context(user_id="unrelated-private-context")
        logging_mod.get_logger(name).error(
            "request_failure_diagnostic",
            diagnostic_request_id="owned-request",
            diagnostic_category="database",
            diagnostic_kind="OperationalError",
            diagnostic_sqlstate="08006",
        )
        record = exported(sink, name)
        assert record.body == {
            "message": "request_failure_diagnostic",
            "logger": name,
            "diagnostic_request_id": "owned-request",
            "diagnostic_category": "database",
            "diagnostic_kind": "OperationalError",
            "diagnostic_sqlstate": "08006",
        }


@pytest.mark.parametrize("otel_first", [True, False])
def test_user_exception_mapping_keeps_its_structure_and_numeric_types(
    otel_first: bool,
) -> None:
    name = "otel-bridge-user-exception-field"
    payload = {
        "type": "user-domain-error",
        "args": (1234567890123, {"authorization": "synthetic-value"}),
        "frames": [],
        "attempts": 7,
    }
    expected = {
        "type": "user-domain-error",
        "args": [1234567890123, {"authorization": "[REDACTED]"}],
        "frames": [],
        "attempts": 7,
    }
    with pipeline(otel_first=otel_first) as (sink, output):
        logging_mod.get_logger(name).warning("safe failure", exception=payload)
        record = exported(sink, name)
        assert record.body["exception"] == expected
        assert json.loads(output.getvalue())["exception"] == expected
    assert payload["args"] == (1234567890123, {"authorization": "synthetic-value"})


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("otel_first", [True, False], ids=["otel-first", "otel-last"])
def test_owned_diagnostic_discards_exception_snapshot_without_breaking_logging(
    json_output: bool, otel_first: bool
) -> None:
    name = "app.core.request_failure_diagnostic"
    diagnostic = {
        "diagnostic_request_id": "owned-request",
        "diagnostic_category": "database",
        "diagnostic_kind": "OperationalError",
        "diagnostic_sqlstate": "08006",
    }
    with pipeline(json_output=json_output, otel_first=otel_first) as (sink, output):
        logging_mod.bind_context(email="a@b.cc", user_id="private-context")
        try:
            raise ValueError({"authorization": "synthetic-value"})
        except ValueError:
            logging_mod.get_logger(name).exception(
                "request_failure_diagnostic", **diagnostic
            )
        expected = {
            "message": "request_failure_diagnostic",
            "logger": name,
            **diagnostic,
        }
        assert exported(sink, name).body == expected
        assert json.loads(output.getvalue()) == expected
        assert len(sink.get_finished_logs()) == 1


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("otel_first", [True, False], ids=["otel-first", "otel-last"])
def test_outbox_deferral_receipt_has_closed_schema_on_every_sink(
    json_output: bool, otel_first: bool
) -> None:
    name = "app.workers.outbox"
    event_id = "10000000-0000-4000-8000-000000000005"
    expected = {
        "message": "outbox_event_deferred",
        "logger": name,
        "stored_event_id": event_id,
    }
    with pipeline(json_output=json_output, otel_first=otel_first) as (sink, console):
        try:
            raise ValueError("private-exception")
        except ValueError:
            logging_mod.get_logger(name).bind(
                payload="private-content", user_id="private-user"
            ).info("outbox_event_deferred", stored_event_id=event_id, exc_info=True)
        record = exported(sink, name)
        assert record.body == expected
        assert json.loads(console.getvalue()) == expected
        assert not any(key.startswith("exception.") for key in record.attributes)
        wire = encode_logs(sink.get_finished_logs()).SerializeToString()
        for private in (b"private-content", b"private-user", b"private-exception"):
            assert private not in wire


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("otel_first", [True, False], ids=["otel-first", "otel-last"])
def test_outbox_native_record_drops_real_exception_attributes(
    json_output: bool, otel_first: bool
) -> None:
    name = "app.workers.outbox"
    expected = {
        "message": "outbox_event_deferred",
        "logger": name,
        "stored_event_id": "10000000-0000-4000-8000-000000000005",
    }
    with pipeline(json_output=json_output, otel_first=otel_first) as (sink, console):
        try:
            raise ValueError("private-native-exception")
        except ValueError as error:
            record = logging.LogRecord(
                name,
                logging.INFO,
                __file__,
                1,
                dict(expected),
                (),
                (ValueError, error, error.__traceback__),
            )
        record.__dict__.update(
            _logger=logging.getLogger(name),
            _name="info",
            payload="private-native-extra",
        )
        logging.getLogger().handle(record)
        emitted = exported(sink, name)
        assert emitted.body == expected
        assert not any(key.startswith("exception.") for key in emitted.attributes)
        assert json.loads(console.getvalue()) == expected
        wire = encode_logs(sink.get_finished_logs()).SerializeToString()
        assert b"private-native-exception" not in wire
        assert b"private-native-extra" not in wire
