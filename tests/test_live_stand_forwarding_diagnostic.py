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


def read_receipt_record():
    return dict(
        schema=3,
        scenario="read-receipt-peer",
        project="desktop",
        attempt=0,
        sockets=3,
        closedSockets=2,
        latestUnclosedJoinSent=True,
        chatFrames=1,
        matchingFrames=0,
        socketsCapped=False,
        framesCapped=False,
    )


def test_read_receipt_uses_both_existing_redaction_boundaries():
    expected = read_receipt_record()
    assert evidence._live_playwright_reconnect_diagnostics(line(expected)) == [expected]
    assert evidence._live_playwright_reconnect_diagnostics(
        line(expected, retained=True), retained=True
    ) == [expected]
    capped = expected | dict(
        sockets=32, socketsCapped=True, chatFrames=32, framesCapped=True
    )
    assert evidence._live_playwright_reconnect_diagnostics(line(capped)) == [capped]
    empty = expected | dict(
        sockets=0, closedSockets=0, latestUnclosedJoinSent=False, chatFrames=0
    )
    assert evidence._live_playwright_reconnect_diagnostics(line(empty)) == [empty]


@pytest.mark.parametrize(
    "delta",
    [
        {"extra": "private"},
        {"schema": True},
        {"schema": 2},
        {"scenario": "private"},
        {"project": "private"},
        {"attempt": 2},
        {"attempt": True},
        {"sockets": -1},
        {"sockets": 33},
        {"sockets": True},
        {"closedSockets": 4},
        {"matchingFrames": 2},
        {"sockets": 0, "closedSockets": 0, "latestUnclosedJoinSent": False},
        {"chatFrames": "private"},
        {"latestUnclosedJoinSent": "private"},
        {"socketsCapped": True},
        {"framesCapped": True},
        {"closedSockets": 3},
    ],
)
def test_read_receipt_rejects_nonfinite_or_inconsistent_records(delta):
    for retained in (False, True):
        assert (
            evidence._live_playwright_reconnect_diagnostics(
                line(read_receipt_record() | delta, retained), retained=retained
            )
            == []
        )


def test_read_receipt_preserves_prior_schemas_and_existing_cap():
    old, forwarding, receipt = reconnect_record(), record(), read_receipt_record()
    rows = [
        old,
        forwarding,
        receipt,
        receipt | {"attempt": 1},
        receipt | {"project": "mobile"},
    ]
    assert (
        evidence._live_playwright_reconnect_diagnostics("".join(map(line, rows)))
        == rows[:4]
    )
    for malformed in (
        None,
        [],
        {},
        {k: v for k, v in receipt.items() if k != "matchingFrames"},
    ):
        assert evidence._live_playwright_reconnect_diagnostics(line(malformed)) == []


@pytest.mark.parametrize("failed", [False, True])
def test_read_receipt_runner_only_retains_valid_failure_evidence(
    failed, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        live_stand,
        "_live_playwright_reconnect_diagnostics",
        evidence._live_playwright_reconnect_diagnostics,
    )
    monkeypatch.setattr(
        live_stand.fast_preflight,
        "run_check",
        lambda *a, **kw: SimpleNamespace(
            status="failed" if failed else "passed",
            exit_code=1 if failed else 0,
            stdout=line(read_receipt_record()) + "private-body\n  1 passed (1s)\n",
            stderr="private-error\n",
        ),
    )
    if failed:
        with pytest.raises(live_stand.StandError):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    output = capsys.readouterr().out
    assert "private" not in output
    assert evidence._live_playwright_reconnect_diagnostics(output, retained=True) == (
        [read_receipt_record()] if failed else []
    )
