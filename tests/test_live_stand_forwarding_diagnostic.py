import json
from types import SimpleNamespace

import pytest

from scripts import live_stand
from scripts import live_stand_playwright_evidence as evidence
from tests.test_aud429_live_workflow import _embedded_python, _execute_guard
from tests.test_live_stand_reconnect_diagnostic import _record as reconnect_record


def record():
    return dict(
        schema=2,
        scenario="forwarding-source-receive",
        project="desktop",
        attempt=0,
        sockets=1,
        joinSentSockets=1,
        openJoinSentSockets=1,
        sourceFrames=0,
        sourceFramesAfterJoinSent=0,
        sourceAccepted=True,
        socketsCapped=False,
        framesCapped=False,
    )


def line(value, retained=False):
    return (
        ("live E2E reconnect " if retained else "UE_LIVE_RECONNECT_V1 ")
        + json.dumps(value)
        + "\n"
    )


def test_both_boundaries():
    parsed = evidence._live_playwright_reconnect_diagnostics(line(record()))
    assert parsed == [record()]
    assert (
        evidence._live_playwright_reconnect_diagnostics(
            line(parsed[0], True), retained=True
        )
        == parsed
    )


@pytest.mark.parametrize(
    "delta",
    [
        {"extra": "secret"},
        {"project": "private@example.test"},
        {"schema": True},
        {"attempt": True},
        {"sockets": 33},
        {"sockets": -1},
        {"sourceFrames": 1.5},
        {"sourceAccepted": 1},
        {"framesCapped": "false"},
        {"joinSentSockets": 2},
        {"openJoinSentSockets": 2},
        {"sourceFramesAfterJoinSent": 1},
        {"sourceFrames": "https://private"},
        {"message": "x" * 5000},
    ],
)
def test_rejects_invalid(delta):
    for retained in (False, True):
        assert (
            evidence._live_playwright_reconnect_diagnostics(
                line(record() | delta, retained), retained=retained
            )
            == []
        )


def test_raw_invalid_and_cap():
    valid = line(record())
    for raw in (
        valid.rstrip("\n"),
        valid.replace('"schema": 2', '"schema": 2, "schema": 2'),
        valid.replace('"schema": 2', '"schema": NaN'),
        " " + valid,
        valid.replace('"schema": 2', '"schema": 2' + " " * 5000),
    ):
        assert evidence._live_playwright_reconnect_diagnostics(raw) == []
    rows = [
        record() | dict(project=p, attempt=a)
        for p in ("desktop", "mobile")
        for a in (0, 1)
    ]
    assert (
        evidence._live_playwright_reconnect_diagnostics(
            "".join(line(r) for r in rows) * 2
        )
        == rows
    )


def test_mixed_schema_cap_preserves_v1():
    old = reconnect_record()
    assert evidence._live_playwright_reconnect_diagnostics(line(old)) == [old]
    rows = [
        old,
        record(),
        record() | {"attempt": 1},
        record() | {"project": "mobile"},
        old | {"attempt": 1},
    ]
    assert (
        evidence._live_playwright_reconnect_diagnostics("".join(map(line, rows)))
        == rows[:4]
    )


def test_real_runner_and_workflow_boundary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        live_stand,
        "_live_playwright_reconnect_diagnostics",
        evidence._live_playwright_reconnect_diagnostics,
    )
    monkeypatch.setattr(
        live_stand.fast_preflight,
        "run_check",
        lambda *a, **kw: SimpleNamespace(
            status="failed",
            exit_code=1,
            stdout=line(record()) + "private-body\n",
            stderr="private-error\n",
        ),
    )
    with pytest.raises(live_stand.StandError):
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    result = capsys.readouterr()
    assert "private" not in result.out + result.err
    assert evidence._live_playwright_reconnect_diagnostics(
        result.out, retained=True
    ) == [record()]
    raw, safe = tmp_path / "raw.txt", tmp_path / "safe.txt"
    raw.write_text(result.out)
    guarded = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        raw,
        str(safe),
        "1",
    )
    assert guarded.returncode != 0
    assert evidence._live_playwright_reconnect_diagnostics(
        safe.read_text(), retained=True
    ) == [record()]
    assert "private" not in safe.read_text()


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        1,
        {},
        record() | {"schema": 1},
        record() | {"scenario": "secret"},
        record() | {"attempt": 2},
        {k: v for k, v in record().items() if k != "sourceAccepted"},
    ],
)
def test_rejects_wrong_shape(value):
    assert evidence._live_playwright_reconnect_diagnostics(line(value)) == []
