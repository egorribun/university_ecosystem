"""AUD-452: log payloads are copied and unsupported representations stay opaque."""

from __future__ import annotations

import json
import logging
import sys
from collections import UserDict
from collections.abc import Callable, Mapping
from contextvars import Context
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from types import MappingProxyType, SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, SecretStr, field_serializer

import app.core.logging as logging_mod

REDACTED = "[REDACTED]"
MARKER = "synthetic-private-value"


class _Unrenderable:
    def __str__(self) -> str:
        raise AssertionError("Logging must not call an unsupported __str__")

    def __repr__(self) -> str:
        raise AssertionError("Logging must not call an unsupported __repr__")

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise AssertionError("Logging must not invoke copy hooks")

    def __bool__(self) -> bool:
        raise AssertionError("Logging must not truth-test unsupported controls")

    @property
    def name(self) -> str:
        raise AssertionError("Logging must not inspect a counterfeit log record")

    @property
    def model_dump(self) -> Any:
        raise AssertionError("Logging must not discover serializer properties")

    @property
    def password(self) -> str:
        raise AssertionError("Logging must not inspect arbitrary properties")


class _UnrenderableStringKey(str):
    __hash__ = str.__hash__

    def __str__(self) -> str:
        raise AssertionError("Logging must not coerce unsupported field names")

    def __repr__(self) -> str:
        raise AssertionError("Logging must not render unsupported field names")

    def __eq__(self, other: object) -> bool:
        raise AssertionError("Logging must not compare unsupported control names")


class _PrivateModel(BaseModel):
    password: str
    status: str

    @field_serializer("password")
    def serialize_password(self, value: str) -> str:
        raise AssertionError("Logging must not run model serializers")

    @property
    def unsafe_property(self) -> str:
        raise AssertionError("Logging must not inspect model properties")

    def __str__(self) -> str:
        raise AssertionError("Logging must not render model strings")

    def __repr__(self) -> str:
        raise AssertionError("Logging must not render model representations")


@dataclass(frozen=True)
class _PrivateDataclass:
    password: str = field(repr=False)
    status: str = "public-diagnostic"

    @property
    def unsafe_property(self) -> str:
        raise AssertionError("Logging must not inspect dataclass properties")


@dataclass(frozen=True, slots=True)
class _PrivateSlottedDataclass:
    password: str = field(repr=False)
    status: str = "public-diagnostic"


@pytest.mark.parametrize(
    "mapping_factory",
    [UserDict, MappingProxyType],
    ids=["user-dict", "mapping-proxy"],
)
def test_mapping_payloads_are_copied_without_losing_public_fields(
    mapping_factory: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> None:
    shared = {"password": MARKER, "note": "mail student@example.org"}
    items = [shared]
    backing = {"items": items, "status": "public-diagnostic", "count": 7}
    payload = mapping_factory(backing)

    result = logging_mod._redact_nested(payload, seen=set())

    assert result == {
        "items": [{"password": REDACTED, "note": f"mail {REDACTED}"}],
        "status": "public-diagnostic",
        "count": 7,
    }
    assert isinstance(result, dict)
    assert result is not payload
    assert result["items"] is not items
    assert result["items"][0] is not shared
    assert payload["items"] is items
    assert items[0] is shared
    assert shared == {"password": MARKER, "note": "mail student@example.org"}


@pytest.mark.parametrize(
    "mapping_factory",
    [UserDict, MappingProxyType],
    ids=["user-dict", "mapping-proxy"],
)
def test_mapping_back_edges_are_redacted_without_destroying_input_cycles(
    mapping_factory: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> None:
    backing: dict[str, Any] = {"status": "public-diagnostic"}
    payload = mapping_factory(backing)
    backing["self"] = payload
    if isinstance(payload, UserDict):
        payload["self"] = payload

    result = logging_mod._redact_nested(payload, seen=set())

    assert result == {"status": "public-diagnostic", "self": REDACTED}
    assert payload["self"] is payload
    assert backing["self"] is payload


@pytest.mark.parametrize(
    "factory",
    [
        _Unrenderable,
        lambda: _PrivateModel(password=MARKER, status="public-diagnostic"),
        lambda: _PrivateDataclass(password=MARKER),
        lambda: _PrivateSlottedDataclass(password=MARKER),
        lambda: SecretStr(MARKER),
    ],
    ids=["opaque", "model", "dataclass", "slotted-dataclass", "secret-string"],
)
def test_unsupported_payload_values_are_opaque_without_running_hooks(
    factory: Callable[[], Any],
) -> None:
    value = factory()

    result = logging_mod._redact_nested(value, seen=set())

    if not isinstance(result, str):
        pytest.fail("Unsupported payload was returned instead of an opaque marker")
    assert result == REDACTED
    if isinstance(value, SecretStr):
        assert value.get_secret_value() == MARKER
    elif isinstance(
        value, _PrivateModel | _PrivateDataclass | _PrivateSlottedDataclass
    ):
        assert value.password == MARKER


def test_copying_preserves_source_backed_scalar_metadata() -> None:
    user_id = UUID("3c3be1b0-0669-4f05-bf29-d73d3f7f838f")
    timestamp = datetime(2026, 10, 24, 10, 0, tzinfo=UTC)
    event = {
        "event": "public-diagnostic",
        "count": 7,
        "elapsed_seconds": 1.25,
        "enabled": True,
        "optional": None,
        "user_id": user_id,
        "timestamp": timestamp,
    }

    result = logging_mod._redact_pii(None, "info", event)

    assert result == event
    assert result is not event
    assert result["user_id"] is user_id
    assert result["timestamp"] is timestamp


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("origin", ["call", "bound", "context"])
def test_repeated_logs_copy_shared_payloads_before_both_renderers(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    origin: str,
) -> None:
    shared = {"password": MARKER, "note": "student@example.org"}
    mapping = UserDict({"first": shared, "second": shared, "count": 7})
    payload = {"mapping": mapping, "opaque": _Unrenderable()}
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    context = Context()

    try:
        logging_mod.configure_logging(json_output=json_output)
        logger = logging_mod.get_logger("audit-452-payload")
        if origin == "bound":
            logger = logger.bind(payload=payload)
        elif origin == "context":
            context.run(logging_mod.bind_context, payload=payload)
        for _ in range(2):
            if origin == "call":
                logger.info(
                    "payload inspected", payload=payload, status="public-diagnostic"
                )
            else:
                context.run(
                    logger.info, "payload inspected", status="public-diagnostic"
                )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert MARKER not in output
    assert "student@example.org" not in output
    assert output.count("payload inspected") == 2
    assert output.count("public-diagnostic") == 2
    assert output.count(REDACTED) == 10
    assert shared == {"password": MARKER, "note": "student@example.org"}
    assert mapping["first"] is mapping["second"] is shared
    assert payload["mapping"] is mapping
    if json_output:
        events = [json.loads(line) for line in output.splitlines()]
        assert len(events) == 2
        for event in events:
            assert event["payload"] == {
                "mapping": {
                    "first": {"password": REDACTED, "note": REDACTED},
                    "second": {"password": REDACTED, "note": REDACTED},
                    "count": 7,
                },
                "opaque": REDACTED,
            }


@pytest.mark.parametrize(
    "kind", ["true", "false", "exception", "tuple", "tuple-without-traceback"]
)
def test_redaction_preserves_top_level_exception_and_formatter_controls(
    kind: str,
) -> None:
    record = logging.LogRecord(
        "audit-452-control", logging.ERROR, __file__, 1, "event", (), None
    )
    try:
        raise ValueError("safe diagnostic failure")
    except ValueError:
        exc_info = sys.exc_info()
    exception_control = {
        "true": True,
        "false": False,
        "exception": exc_info[1],
        "tuple": exc_info,
        "tuple-without-traceback": (ValueError, exc_info[1], None),
    }[kind]
    event = {
        "event": "event",
        "exc_info": exception_control,
        "_record": record,
        "_from_structlog": False,
        "stack_info": False,
    }

    result = logging_mod._redact_pii(None, "error", event)

    assert result is not event
    assert result["exc_info"] is exception_control
    assert result["_record"] is record
    assert result["_from_structlog"] is False
    assert result["stack_info"] is False
    assert event["exc_info"] is exception_control
    assert event["_record"] is record


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        ("exc_info", _Unrenderable),
        ("exc_info", lambda: (ValueError, ValueError("safe diagnostic failure"))),
        ("exc_info", lambda: (ValueError, _Unrenderable(), None)),
        ("exc_info", lambda: (_Unrenderable(), ValueError("safe failure"), None)),
        ("exc_info", lambda: (str, ValueError("safe failure"), None)),
        (
            "exc_info",
            lambda: (
                ValueError,
                ValueError("safe diagnostic failure"),
                _Unrenderable(),
            ),
        ),
        ("_record", _Unrenderable),
        ("_from_structlog", _Unrenderable),
        ("stack_info", _Unrenderable),
    ],
    ids=[
        "opaque-exception",
        "short-exception-tuple",
        "invalid-exception-value",
        "invalid-exception-type",
        "nonexception-type",
        "invalid-traceback",
        "counterfeit-record",
        "opaque-origin",
        "opaque-stack-request",
    ],
)
def test_invalid_top_level_controls_are_discarded_without_running_hooks(
    field_name: str,
    factory: Callable[[], Any],
) -> None:
    value = factory()
    event = {"event": "public-diagnostic", field_name: value}

    result = logging_mod._redact_pii(None, "error", event)

    assert field_name not in result
    assert result["event"] == "public-diagnostic"
    assert event[field_name] is value


def test_nested_genuine_exception_and_record_values_are_not_privileged() -> None:
    record = logging.LogRecord(
        "audit-452-nested", logging.ERROR, __file__, 1, "event", (), None
    )
    try:
        raise ValueError("safe diagnostic failure")
    except ValueError:
        exc_info = sys.exc_info()
    payload = {
        "exc_info": exc_info[1],
        "_record": record,
        "details": {"exc_info": exc_info},
    }

    result = logging_mod._redact_nested(payload, seen=set())

    assert result == {
        "exc_info": REDACTED,
        "_record": REDACTED,
        "details": {"exc_info": (REDACTED, REDACTED, REDACTED)},
    }
    assert payload["exc_info"] is exc_info[1]
    assert payload["_record"] is record
    assert payload["details"]["exc_info"] is exc_info


def test_nested_control_names_do_not_authorize_object_representations() -> None:
    value = _Unrenderable()
    payload = {"exc_info": value, "_record": value}

    result = logging_mod._redact_nested(payload, seen=set())

    if any(not isinstance(item, str) for item in result.values()):
        pytest.fail("Nested control names bypassed opaque payload handling")
    assert result == {"exc_info": REDACTED, "_record": REDACTED}
    assert payload["exc_info"] is payload["_record"] is value


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize("native", [True, False], ids=["structlog", "stdlib"])
def test_copied_events_keep_positional_formatting_and_real_exception_output(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    native: bool,
) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)

    try:
        logging_mod.configure_logging(json_output=json_output)
        logger = (
            logging_mod.get_logger("audit-452-control")
            if native
            else logging_mod.get_stdlib_logger("audit-452-control")
        )
        logger.info("count=%d", 7)
        try:
            raise ValueError("safe diagnostic failure")
        except ValueError:
            logger.exception("operation failed")
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "count=7" in output
    assert "operation failed" in output
    assert "ValueError" in output
    assert "safe diagnostic failure" in output
    assert "_record" not in output
    assert "_from_structlog" not in output
    if json_output:
        first, second = [json.loads(line) for line in output.splitlines()]
        assert first["message"] == "count=7"
        assert second["message"] == "operation failed"
        assert "ValueError: safe diagnostic failure" in second["exception"]
        assert first["logger"] == second["logger"] == "audit-452-control"
        assert first["service"] == second["service"] == "backend"


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("disabled", [False, True], ids=["module", "root-fallback"])
def test_email_bridge_keeps_raw_record_extras_redacted_without_mutating_input(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    disabled: bool,
) -> None:
    import app.utils.email as email_mod

    module_logger = logging.getLogger(email_mod.__name__)
    monkeypatch.setattr(module_logger, "disabled", disabled)
    monkeypatch.setattr(email_mod, "logger", module_logger)
    shared = {"password": MARKER, "note": "student@example.org"}
    extra = {"email": "student@example.org", "details": [shared]}

    with caplog.at_level(logging.WARNING):
        email_mod._log_event(logging.WARNING, "email.payload.inspected", extra=extra)

    records = [
        record for record in caplog.records if record.msg == "email.payload.inspected"
    ]
    assert len(records) == 1
    record = records[0]
    assert record.email == REDACTED
    assert record.details == [{"password": REDACTED, "note": REDACTED}]
    assert record.name == ("root" if disabled else email_mod.__name__)
    assert record.details is not extra["details"]
    assert record.details[0] is not shared
    assert extra["email"] == "student@example.org"
    assert extra["details"][0] is shared
    assert shared == {"password": MARKER, "note": "student@example.org"}


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
def test_stdlib_stack_requests_survive_foreign_processor_redaction(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
) -> None:
    """ProcessorFormatter supplies a preformatted string, not a boolean."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)

    try:
        logging_mod.configure_logging(json_output=json_output)
        logging_mod.get_stdlib_logger("audit-452-stack").info(
            "stack requested", stack_info=True
        )
        output = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "stack requested" in output
    assert "Stack (most recent call last):" in output
    if json_output:
        rendered = json.loads(output)
        assert rendered["message"] == "stack requested"
        assert "Stack (most recent call last):" in rendered["stack"]
        assert rendered["logger"] == "audit-452-stack"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            UUID("3c3be1b0-0669-4f05-bf29-d73d3f7f838f"),
            "3c3be1b0-0669-4f05-bf29-d73d3f7f838f",
        ),
        (
            datetime(2026, 10, 24, 10, 0, tzinfo=UTC),
            "2026-10-24 10:00:00+00:00",
        ),
    ],
    ids=["uuid", "datetime"],
)
def test_json_fallback_preserves_known_scalar_metadata_without_unknown_hooks(
    monkeypatch: pytest.MonkeyPatch,
    value: UUID | datetime,
    expected: str,
) -> None:
    def dumps(obj: Any, *, default: Callable[[Any], Any]) -> bytes:
        return json.dumps(obj, default=default).encode("utf-8")

    monkeypatch.setattr(logging_mod, "orjson", SimpleNamespace(dumps=dumps))

    output = logging_mod._orjson_serializer({"value": value, "opaque": _Unrenderable()})

    assert json.loads(output) == {"value": expected, "opaque": REDACTED}


@pytest.mark.parametrize(
    "key_factory",
    [_Unrenderable, lambda: _UnrenderableStringKey("non-native-key")],
    ids=["opaque-key", "string-subclass-key"],
)
def test_non_native_field_names_are_discarded_before_control_matching(
    key_factory: Callable[[], Any],
) -> None:
    key = key_factory()
    value = _Unrenderable()
    record = logging.LogRecord(
        "audit-452-key", logging.INFO, __file__, 1, "event", (), None
    )
    event = {
        "event": "public-diagnostic",
        key: value,
        "count": 7,
        "password": MARKER,
        "exc_info": False,
        "_record": record,
        "_from_structlog": False,
        "stack_info": False,
    }

    result = logging_mod._redact_pii(None, "info", event)

    if any(type(field_name) is not str for field_name in result):
        pytest.fail("Unsupported field name reached the copied event")
    assert result == {
        "event": "public-diagnostic",
        "count": 7,
        "password": REDACTED,
        "exc_info": False,
        "_record": record,
        "_from_structlog": False,
        "stack_info": False,
    }
    assert result is not event
    assert len(event) == 8
    assert any(field_name is key for field_name in event)
    assert event[key] is value
    assert event["password"] == MARKER
    assert event["_record"] is record


@pytest.mark.parametrize(
    "mapping_factory",
    [dict, UserDict, MappingProxyType],
    ids=["dict", "user-dict", "mapping-proxy"],
)
@pytest.mark.parametrize(
    "key_factory",
    [_Unrenderable, lambda: _UnrenderableStringKey("non-native-key")],
    ids=["opaque-key", "string-subclass-key"],
)
def test_mapping_keys_cannot_bypass_opaque_payload_handling(
    mapping_factory: Callable[[dict[Any, Any]], Mapping[Any, Any]],
    key_factory: Callable[[], Any],
) -> None:
    key = key_factory()
    value = _Unrenderable()
    backing = {
        key: value,
        "status": "public-diagnostic",
        "count": 7,
        "password": MARKER,
        "note": "student@example.org",
        REDACTED: "literal-field-name",
    }
    payload = mapping_factory(backing)

    result = logging_mod._redact_nested(payload, seen=set())

    if any(type(field_name) is not str for field_name in result):
        pytest.fail("Unsupported field name reached the copied mapping")
    assert result == {
        "status": "public-diagnostic",
        "count": 7,
        "password": REDACTED,
        "note": REDACTED,
        REDACTED: "literal-field-name",
    }
    assert result is not payload
    assert len(payload) == len(backing) == 6
    assert any(field_name is key for field_name in payload)
    assert payload[key] is backing[key] is value
    assert payload["password"] == backing["password"] == MARKER
    assert payload["note"] == backing["note"] == "student@example.org"


@pytest.mark.usefixtures("preserve_logging_configuration")
@pytest.mark.parametrize("json_output", [True, False], ids=["json", "console"])
@pytest.mark.parametrize(
    "key_factory",
    [_Unrenderable, lambda: _UnrenderableStringKey("non-native-key")],
    ids=["opaque-key", "string-subclass-key"],
)
def test_non_native_mapping_keys_never_reach_configured_renderers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    json_output: bool,
    key_factory: Callable[[], Any],
) -> None:
    key = key_factory()
    payload = {
        key: "discarded-entry",
        "status": "public-diagnostic",
        "password": MARKER,
    }
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    monkeypatch.setattr(logging, "raiseExceptions", True)

    try:
        logging_mod.configure_logging(json_output=json_output)
        logging_mod.get_logger("audit-452-key").info(
            "mapping keys inspected", payload=payload
        )
        output = stream.getvalue()
        error_output = capsys.readouterr().err
    finally:
        root.removeHandler(handler)
        handler.close()

    assert "mapping keys inspected" in output
    assert "public-diagnostic" in output
    assert REDACTED in output
    assert MARKER not in output
    assert MARKER not in error_output
    assert "--- Logging error ---" not in error_output
    assert len(payload) == 3
    assert any(field_name is key for field_name in payload)
    assert payload[key] == "discarded-entry"
    assert payload["password"] == MARKER
    if json_output:
        rendered = json.loads(output)
        assert rendered["payload"] == {
            "status": "public-diagnostic",
            "password": REDACTED,
        }
