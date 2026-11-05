"""Safe exception snapshots preserve diagnostics without representation hooks."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.logging import (
    _format_safe_exc_info,
    _safe_exception_attributes,
    _safe_exception_snapshot,
)


def snapshot(exception: BaseException) -> dict[str, Any]:
    attributes = _safe_exception_attributes(exception)
    assert attributes["exception.type"] in attributes["exception.stacktrace"]
    return _safe_exception_snapshot(
        exception,
        BaseException.__dict__["__traceback__"].__get__(exception),
        seen=set(),
    )


class Opaque:
    def __str__(self) -> str:
        raise AssertionError("opaque str hook")

    def __repr__(self) -> str:
        raise AssertionError("opaque repr hook")

    def __bool__(self) -> bool:
        raise AssertionError("opaque truth hook")


@pytest.mark.parametrize(
    "control",
    [None, False, True, (None, None, None), ("invalid", None, None), Opaque()],
)
def test_absent_or_invalid_exception_controls_do_not_render(control: Any) -> None:
    assert _safe_exception_attributes(control) == {}
    assert _format_safe_exc_info(
        None, "info", {"event": "safe", "exc_info": control}
    ) == {"event": "safe"}


def test_false_control_does_not_reveal_an_active_exception() -> None:
    try:
        raise ValueError({"authorization": "synthetic-value"})
    except ValueError:
        assert _safe_exception_attributes(False) == {}


def test_direct_exception_control_uses_actual_type_and_safe_arguments() -> None:
    error = ValueError({"authorization": "synthetic-value", "opaque": Opaque()})
    attributes = _safe_exception_attributes(error)
    assert attributes["exception.type"] == "ValueError"
    assert json.loads(attributes["exception.message"]) == {
        "args": [{"authorization": "[REDACTED]", "opaque": "[REDACTED]"}]
    }
    assert attributes["exception.stacktrace"] == (
        'ValueError: {"args":[{"authorization":"[REDACTED]","opaque":"[REDACTED]"}]}'
    )
    assert snapshot(error) == {
        "type": "ValueError",
        "args": ({"authorization": "[REDACTED]", "opaque": "[REDACTED]"},),
        "frames": [],
    }


def test_empty_exception_arguments_keep_the_type() -> None:
    attributes = _safe_exception_attributes(ValueError())
    assert attributes["exception.type"] == "ValueError"
    assert attributes["exception.message"] == ""
    assert attributes["exception.stacktrace"] == "ValueError"


@pytest.mark.parametrize("suppressed", [True, False])
def test_context_is_preserved_only_when_not_suppressed(suppressed: bool) -> None:
    inner = ValueError({"authorization": "synthetic-value"})
    outer = RuntimeError("safe outer")
    outer.__context__ = inner
    outer.__suppress_context__ = suppressed
    details = snapshot(outer)
    rendered = _safe_exception_attributes(outer)["exception.stacktrace"]
    if suppressed:
        assert "context" not in details
        assert rendered == "RuntimeError: safe outer"
    else:
        assert details["context"]["type"] == "ValueError"
        assert details["context"]["args"] == ({"authorization": "[REDACTED]"},)
        assert (
            "During handling of the above exception, another exception occurred:"
            in rendered
        )
    assert "synthetic-value" not in json.dumps(details)


def test_explicit_cause_takes_precedence_over_implicit_context() -> None:
    outer = RuntimeError("safe outer")
    outer.__cause__ = ValueError("cause")
    outer.__context__ = TypeError("context")
    details = snapshot(outer)
    assert details["cause"]["type"] == "ValueError"
    assert "context" not in details


def test_deep_exception_chain_is_bounded_without_recursion_failure() -> None:
    error = ValueError("safe root")
    for _ in range(64):
        outer = ValueError("safe outer")
        outer.__cause__ = error
        error = outer
    details = snapshot(error)
    assert (
        "ValueError: [exception chain truncated]"
        in _safe_exception_attributes(error)["exception.stacktrace"]
    )
    depth = 0
    while "cause" in details:
        depth += 1
        details = details["cause"]
    assert depth == 32
    assert details == {"type": "ValueError", "truncated": True}


def test_repeated_group_child_is_not_mistaken_for_a_cycle() -> None:
    child = ValueError({"authorization": "synthetic-value"})
    error = ExceptionGroup("safe group", [child, child])
    details = snapshot(error)
    rendered = _safe_exception_attributes(error)["exception.stacktrace"]
    assert rendered.count("ValueError:") == 2
    assert "[exception cycle omitted]" not in rendered
    expected = {
        "type": "ValueError",
        "args": ({"authorization": "[REDACTED]"},),
        "frames": [],
    }
    assert details["exceptions"] == [expected, expected]


class HostileGroup(ExceptionGroup):
    @property
    def exceptions(self) -> tuple[Exception, ...]:
        raise AssertionError("group property must not be called")


def test_exception_group_children_are_read_without_custom_properties() -> None:
    details = snapshot(HostileGroup("safe", [ValueError("child")]))
    assert details["type"] == "HostileGroup"
    assert details["exceptions"][0]["type"] == "ValueError"


def test_exception_notes_follow_the_same_structured_redaction() -> None:
    error = ValueError("safe")
    error.__notes__ = [{"authorization": "synthetic-value"}, Opaque(), "mail a@b.cc"]
    details = snapshot(error)
    assert details["notes"] == [
        {"authorization": "[REDACTED]"},
        "[REDACTED]",
        "mail [REDACTED]",
    ]
    rendered = _safe_exception_attributes(error)["exception.stacktrace"]
    assert '{"note":{"authorization":"[REDACTED]"}}' in rendered
    assert "mail [REDACTED]" in rendered


def test_non_list_exception_note_is_rendered_without_iterating_its_characters() -> None:
    error = ValueError("safe")
    error.__notes__ = "mail a@b.cc"
    assert (
        _safe_exception_attributes(error)["exception.stacktrace"]
        == "ValueError: safe\nmail [REDACTED]"
    )


def test_traceback_snapshot_never_reads_source_lines_or_frame_locals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "exception_probe.py"
    source.write_text(
        "def fail():\n"
        "    local_secret = 'synthetic-value'\n"
        "    raise ValueError('safe message')  # synthetic-value\n",
        encoding="utf-8",
    )
    fail = runpy.run_path(str(source))["fail"]
    try:
        fail()
    except ValueError:
        attributes = _safe_exception_attributes(sys.exc_info())
        _, error, traceback = sys.exc_info()
        details = _safe_exception_snapshot(error, traceback, seen=set())
    assert "synthetic-value" not in json.dumps(attributes)
    assert "local_secret" not in json.dumps(attributes)
    frames = details["frames"]
    assert frames[-1] == {"file": str(source), "line": 3, "function": "fail"}
    assert all(set(frame) == {"file", "line", "function"} for frame in frames)
    assert (
        f'  File "{source}", line 3, in fail\nValueError: safe message'
        in attributes["exception.stacktrace"]
    )
