"""Closed, bounded reconnect evidence across both redaction boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import live_stand
from scripts import live_stand_playwright_evidence as evidence
from tests.test_aud429_live_workflow import _embedded_python, _execute_guard


def _record() -> dict:
    return {
        "schema": 1,
        "scenario": "direct-message-replay",
        "project": "desktop",
        "attempt": 0,
        "stage": "old-close-wait",
        "selected": 1,
        "sessions": 1,
        "sessionsCapped": False,
        "joined": True,
        "closed": False,
        "elapsedMs": 15000,
        "elapsedCapped": False,
        "offlineEvents": 1,
        "onlineEvents": 0,
        "online": False,
        "probe": "unique",
        "nativeState": 2,
        "buffered": "zero",
        "eventsCapped": False,
        "sampleAfterFailureMs": 10,
        "events": [
            {"sequence": 1, "kind": "socket-created", "session": 1, "elapsedMs": 0}
        ],
    }


def _parse(output: str, *, retained: bool = False) -> list[dict]:
    parser = getattr(evidence, "_live_playwright_reconnect_diagnostics", None)
    assert callable(parser), "the closed reconnect parser must exist"
    return parser(output, retained=retained)


def _line(record: dict | None = None, *, retained: bool = False) -> str:
    prefix = "live E2E reconnect " if retained else "UE_LIVE_RECONNECT_V1 "
    return (
        prefix
        + json.dumps(_record() if record is None else record, separators=(",", ":"))
        + "\n"
    )


def test_reconnect_evidence_survives_both_redaction_boundaries(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    assert _parse(_line()) == [_record()]
    monkeypatch.setattr(
        live_stand.fast_preflight,
        "run_check",
        lambda *args, **kwargs: SimpleNamespace(
            status="failed",
            exit_code=1,
            stdout=_line() + "private-body\n",
            stderr="private-error\n",
        ),
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    rendered = capsys.readouterr()
    assert rendered.err == ""
    assert _parse(rendered.out, retained=True) == [_record()]
    assert "private" not in rendered.out
    raw = tmp_path / "raw.txt"
    safe = tmp_path / "safe.txt"
    raw.write_text(rendered.out, encoding="utf-8")
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        raw,
        str(safe),
        "1",
    )
    assert result.returncode != 0
    assert _parse(safe.read_text(), retained=True) == [_record()]
    assert "private" not in safe.read_text()


@pytest.mark.parametrize(
    "change",
    [
        {"schema": True},
        {"project": "desktop\nprivate"},
        {"attempt": 2},
        {"selected": 2},
        {"sessions": True},
        {"sessionsCapped": 1},
        {"elapsedMs": 120001},
        {"elapsedMs": float("nan")},
        {"elapsedMs": float("inf")},
        {"offlineEvents": "1"},
        {"offlineEvents": 33},
        {"nativeState": 4},
        {"nativeState": True},
        {"probe": "private"},
        {"probe": "unavailable"},
        {"buffered": "secret"},
        {"private": "token"},
        {"stage": "old-close-wait token=secret"},
        {
            "events": [
                {
                    "sequence": 1,
                    "kind": "socket-created",
                    "session": 1,
                    "elapsedMs": 0,
                    "private": "secret",
                }
            ]
        },
        {
            "events": [
                {"sequence": 2, "kind": "socket-created", "session": 1, "elapsedMs": 0}
            ]
        },
        {
            "events": [
                {
                    "sequence": 1,
                    "kind": "socket-created",
                    "session": 1,
                    "elapsedMs": 15001,
                }
            ]
        },
    ],
)
def test_reconnect_parser_rejects_unknown_or_out_of_domain_fields(change: dict) -> None:
    assert _parse(_line({**_record(), **change})) == []


@pytest.mark.parametrize(
    "kind",
    [
        "truncated",
        "prefix",
        "suffix",
        "duplicate",
        "oversize",
        "cr",
        "unicode",
        "escape",
    ],
)
def test_reconnect_framing_rejects_injection_and_partial_records(
    kind: str, tmp_path: Path
) -> None:
    line = _line()
    invalid = {
        "truncated": line[:-1],
        "prefix": "private " + line,
        "suffix": line[:-1] + " private\n",
        "duplicate": line.replace('"schema":1', '"schema":1,"schema":1'),
        "oversize": line.replace('"schema":1', '"schema":1' + " " * 4096),
        "cr": "private\r" + line,
        "unicode": "private\u2028" + line,
        "escape": "\x1b[31m" + line,
    }[kind]
    assert _parse(invalid) == []
    raw = tmp_path / "raw.txt"
    safe = tmp_path / "safe.txt"
    raw.write_text(
        invalid.replace("UE_LIVE_RECONNECT_V1 ", "live E2E reconnect "),
        encoding="utf-8",
    )
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        raw,
        str(safe),
        "1",
    )
    assert result.returncode != 0
    assert _parse(safe.read_text(), retained=True) == []
    assert "private" not in safe.read_text()


def test_reconnect_parser_caps_records_and_never_repeats_an_attempt() -> None:
    records = []
    for project in ("desktop", "mobile"):
        for attempt in (0, 1):
            records.append({**_record(), "project": project, "attempt": attempt})
    assert _parse("".join(_line(record) * 2 for record in records)) == records
    changed = {**_record(), "elapsedMs": 16000}
    assert _parse(_line() + _line(changed)) == [_record()]


@pytest.mark.parametrize(
    ("exit_code", "stream"), [(0, "stdout"), (0, "stderr"), (1, "stderr")]
)
def test_reconnect_reporter_discards_success_and_stderr_rows(
    exit_code, stream, tmp_path, monkeypatch, capsys
) -> None:
    values = {"stdout": "", "stderr": "", stream: _line()}
    monkeypatch.setattr(
        live_stand.fast_preflight,
        "run_check",
        lambda *args, **kwargs: SimpleNamespace(
            status="passed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            **values,
        ),
    )
    if exit_code:
        with pytest.raises(live_stand.StandError):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert "live E2E reconnect " not in printed.out
    assert printed.err == ""


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        {"sampleAfterFailureMs": -1},
        {"sampleAfterFailureMs": True},
        {"sampleAfterFailureMs": 1001},
        {"sampleAfterFailureMs": None},
        {"attempt": True},
        {"sessions": -1},
        {"sessions": 33},
        {"selected": True},
        {"sessionsCapped": True},
        {"elapsedCapped": True},
        {"eventsCapped": True},
        {"online": 0},
        {"joined": 1},
        {"closed": None},
        {"events": {}},
        {"selected": 0},
        {"elapsedMs": -1},
        {"schema": 1.0},
        {
            "events": [
                {
                    "sequence": True,
                    "kind": "socket-created",
                    "session": 1,
                    "elapsedMs": 0,
                }
            ]
        },
        {
            "events": [
                {"sequence": 1, "kind": "socket-created", "session": 0, "elapsedMs": 0}
            ]
        },
        {
            "events": [
                {"sequence": 1, "kind": "offline-called", "session": 1, "elapsedMs": 0}
            ]
        },
        {
            "events": [
                {"sequence": 1, "kind": "room-joined", "session": True, "elapsedMs": 0}
            ]
        },
        {"events": [{"sequence": 1, "kind": "private", "session": 1, "elapsedMs": 0}]},
        {
            "events": [
                {
                    "sequence": 1,
                    "kind": "socket-created",
                    "session": 1,
                    "elapsedMs": True,
                }
            ]
        },
        {
            "events": [
                {"sequence": 1, "kind": "socket-created", "session": 1, "elapsedMs": 2},
                {"sequence": 2, "kind": "room-joined", "session": 1, "elapsedMs": 1},
            ]
        },
    ],
)
def test_reconnect_domain_checks_apply_at_each_boundary(change, retained):
    assert (
        _parse(_line({**_record(), **change}, retained=retained), retained=retained)
        == []
    )


@pytest.mark.parametrize("retained", [False, True])
def test_reconnect_nested_duplicate_keys_controls_and_missing_keys(retained):
    line = _line(retained=retained)
    assert (
        _parse(
            line.replace('"sequence":1', '"sequence":1,"sequence":1'), retained=retained
        )
        == []
    )
    assert _parse(line.replace('"schema":1', '"schema":1\t'), retained=retained) == []
    assert _parse(line.replace('"schema":1,', ""), retained=retained) == []
    assert _parse(line.replace('"schema":1', '"schema":1\r'), retained=retained) == []
    assert _parse(line[:-1] + "\r\n", retained=retained) == [_record()]


@pytest.mark.parametrize(
    "probe", ["unique", "missing", "ambiguous", "overflow", "unavailable"]
)
def test_reconnect_accepts_each_closed_probe_state(probe):
    record = {**_record(), "probe": probe}
    if probe != "unique":
        record.update(nativeState=None, buffered=None)
    assert _parse(_line(record)) == [record]


def test_reconnect_accepts_unavailable_null_sampling_and_empty_observations():
    record = {
        **_record(),
        "selected": 0,
        "sessions": 0,
        "joined": False,
        "events": [],
        "probe": "unavailable",
        "sampleAfterFailureMs": None,
        "offlineEvents": None,
        "onlineEvents": None,
        "online": None,
        "nativeState": None,
        "buffered": None,
    }
    assert _parse(_line(record)) == [record]
    for key, value in (("offlineEvents", 0), ("onlineEvents", 0), ("online", False)):
        assert _parse(_line({**record, key: value})) == []


def test_reconnect_accepts_caps_and_rejects_excess_events():
    record = {
        **_record(),
        "sessions": 32,
        "sessionsCapped": True,
        "elapsedMs": 120000,
        "elapsedCapped": True,
        "eventsCapped": True,
        "sampleAfterFailureMs": 1000,
        "events": [
            {"sequence": i, "kind": "offline-called", "session": 0, "elapsedMs": i}
            for i in range(1, 25)
        ],
    }
    assert _parse(_line(record)) == [record]
    record["events"].append(
        {"sequence": 25, "kind": "online-called", "session": 0, "elapsedMs": 25}
    )
    assert _parse(_line(record)) == []


def test_reconnect_workflow_drops_diagnostics_on_success_without_changing_grade(
    tmp_path,
):
    raw, safe = tmp_path / "raw.txt", tmp_path / "safe.txt"
    summary = "live E2E counts passed=16\nlive E2E outcome=passed exit_code=0\n"
    raw.write_text(summary + _line(retained=True), encoding="utf-8")
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        raw,
        str(safe),
        "0",
    )
    assert result.returncode == 0
    assert safe.read_text() == summary
