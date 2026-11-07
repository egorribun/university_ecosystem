"""Stdout must redact structured arguments before percent interpolation."""

from __future__ import annotations

import json
import logging
from collections import UserDict
from collections.abc import Iterator
from io import StringIO
from typing import Any

import pytest
import structlog

import app.core.logging as logging_mod


@pytest.fixture(params=[True, False], ids=["json", "console"])
def output(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[StringIO, bool]]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    logger_class = logging.getLoggerClass()
    config = structlog.get_config().copy()
    was_configured = structlog.is_configured()
    context = structlog.contextvars.get_contextvars()
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    monkeypatch.setattr(logging_mod, "_configured", False)
    structlog.contextvars.clear_contextvars()
    logging_mod.configure_logging(json_output=request.param)
    try:
        yield stream, request.param
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        handler.close()
        logging.setLoggerClass(logger_class)
        structlog.configure(**config)
        if not was_configured:
            structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(**context)


@pytest.fixture(params=[True, False], ids=["native", "stdlib"])
def logger(request: pytest.FixtureRequest, output: tuple[StringIO, bool]) -> Any:
    # Pytest adds its own unconfigured capture handlers after fixture setup.
    # Exercise the application's configured handler without sending raw
    # records to those unrelated formatters.
    underlying = logging.Logger("stdout-positional-redaction", logging.INFO)
    underlying.addHandler(logging.getLogger().handlers[0])
    underlying.propagate = False
    return structlog.wrap_logger(underlying) if request.param else underlying


@pytest.mark.parametrize("conversion", ["06d", "x", ".2f", "s", "r"])
@pytest.mark.parametrize("mapping_type", [dict, UserDict])
def test_sensitive_mapping_is_redacted_before_numeric_interpolation(
    output: tuple[StringIO, bool], logger: Any, conversion: str, mapping_type: Any
) -> None:
    arguments = mapping_type({"otp": 123456, "count": 1234567, "ratio": 1.25})
    template = f"otp=%(otp){conversion} count=%(count)d ratio=%(ratio).2f"
    logger.info(template, arguments)
    rendered = output[0].getvalue()
    assert rendered
    assert "otp=123456" not in rendered
    assert "otp=1e240" not in rendered
    assert "[REDACTED]" in rendered
    if output[1] and conversion not in ("s", "r"):
        event = json.loads(rendered)
        assert event["message"] == template
        assert event["positional_args"] == {
            "otp": "[REDACTED]",
            "count": 1234567,
            "ratio": 1.25,
        }
        assert type(event["positional_args"]["count"]) is int
        assert type(event["positional_args"]["ratio"]) is float
    assert arguments == {"otp": 123456, "count": 1234567, "ratio": 1.25}


@pytest.mark.parametrize(
    ("template", "arguments", "expected"),
    [
        (
            "count=%06d ratio=%.2f hex=%#x",
            (7, 1.25, 42),
            "count=000007 ratio=1.25 hex=0x2a",
        ),
        (
            "count=%(count)06d ratio=%(ratio).2f",
            ({"count": 7, "ratio": 1.25},),
            "count=000007 ratio=1.25",
        ),
        ("value=%*.*f %%", (6, 2, 1.25), "value=  1.25 %"),
        ("empty=%s", ({},), "empty={}"),
        ("untouched 100%", (), "untouched 100%"),
    ],
)
def test_valid_percent_formatting_is_preserved(
    output: tuple[StringIO, bool],
    logger: Any,
    template: str,
    arguments: tuple[Any, ...],
    expected: str,
) -> None:
    logger.info(template, *arguments)
    rendered = output[0].getvalue()
    if output[1]:
        event = json.loads(rendered)
        assert event["message"] == expected
        assert "positional_args" not in event
    else:
        assert expected in rendered


def test_nested_positional_mapping_does_not_leak_sensitive_values(
    output: tuple[StringIO, bool],
    logger: Any,
) -> None:
    payload = {"nested": [{"otp": 123456}], "count": 7}
    logger.info("payload=%s count=%d", payload, 3)
    rendered = output[0].getvalue()
    assert "123456" not in rendered
    assert "[REDACTED]" in rendered
    assert "count=3" in rendered
    assert payload == {"nested": [{"otp": 123456}], "count": 7}


def test_contacts_joined_by_interpolation_are_redacted(
    output: tuple[StringIO, bool],
    logger: Any,
) -> None:
    logger.info("contact=%s@%s", "a", "b.cc")
    rendered = output[0].getvalue()
    assert "a@b.cc" not in rendered
    assert "contact=[REDACTED]" in rendered


class Opaque:
    def __str__(self) -> str:
        raise AssertionError("unsafe string conversion")

    def __repr__(self) -> str:
        raise AssertionError("unsafe representation")

    def __int__(self) -> int:
        raise AssertionError("unsafe numeric conversion")


@pytest.mark.parametrize("template", ["payload=%s", "payload=%r", "payload=%d"])
def test_opaque_positional_values_never_reach_formatting_hooks(
    output: tuple[StringIO, bool],
    logger: Any,
    template: str,
) -> None:
    logger.info(template, Opaque())
    assert "[REDACTED]" in output[0].getvalue()


def test_opaque_message_is_redacted_before_stdlib_stringification(
    output: tuple[StringIO, bool],
    logger: Any,
) -> None:
    logger.info(Opaque())
    assert "[REDACTED]" in output[0].getvalue()


@pytest.mark.parametrize("template", ["value=%d", "value=%q", "value=%(missing)s"])
def test_invalid_interpolation_keeps_safe_diagnostics_without_logging_error(
    output: tuple[StringIO, bool],
    logger: Any,
    template: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger.info(template, {"otp": 123456, "count": 1234567})
    rendered = output[0].getvalue()
    assert rendered
    assert "[REDACTED]" in rendered
    assert "123456," not in rendered
    assert capsys.readouterr().err == ""
    if output[1]:
        event = json.loads(rendered)
        assert event["message"] == template
        assert event["positional_args"] == {"otp": "[REDACTED]", "count": 1234567}


def test_stdlib_formatter_does_not_mutate_shared_record_or_caller_mapping(
    output: tuple[StringIO, bool],
) -> None:
    arguments = {"otp": 123456, "count": 7}
    record = logging.LogRecord(
        "stdout-positional-redaction",
        logging.INFO,
        __file__,
        1,
        "otp=%(otp)d count=%(count)d",
        (arguments,),
        None,
    )
    original = record.__dict__.copy()
    formatter = logging.getLogger().handlers[0].formatter
    assert formatter is not None
    first = formatter.format(record)
    second = formatter.format(record)
    assert "123456" not in first + second
    assert record.__dict__ == original
    assert record.args is arguments
    assert arguments == {"otp": 123456, "count": 7}


@pytest.mark.parametrize("count", [-1, 1114112])
def test_character_overflow_preserves_safe_arguments_without_stderr_leaks(
    output: tuple[StringIO, bool],
    logger: Any,
    count: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = {"count": count, "otp": 123456}
    logger.info("value=%(count)c", arguments)
    rendered = output[0].getvalue()
    assert capsys.readouterr().err == ""
    assert rendered
    assert "123456" not in rendered
    assert "[REDACTED]" in rendered
    if output[1]:
        event = json.loads(rendered)
        assert event["message"] == "value=%(count)c"
        assert event["positional_args"] == {"count": count, "otp": "[REDACTED]"}
        assert type(event["positional_args"]["count"]) is int
    assert arguments == {"count": count, "otp": 123456}
