from __future__ import annotations

import subprocess
from itertools import product
from pathlib import Path

import pytest

from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as stand_tests


def test_cleanup_records_are_closed_bounded_and_conflicts_are_unknown() -> None:
    parse = getattr(evidence, "_live_playwright_push_cleanup_observations", None)
    assert callable(parse)
    valid = (
        "UE_LIVE_PUSH_CLEANUP_V1 project=desktop retry=0 case=topics "
        "current-user-row=removed original-recipient=unknown\n"
    )
    expected = ("desktop", 0, "topics", "removed")
    assert parse(valid + valid) == [expected]
    assert parse(valid.replace("removed", "not-found")) == [
        ("desktop", 0, "topics", "not-found")
    ]
    assert parse(valid + valid.replace("removed", "not-found") + valid) == [
        ("desktop", 0, "topics", "unknown")
    ]
    assert parse(valid.replace("\n", "\r\n")) == [expected]
    for row in (
        valid[:-1],
        valid[:-1] + " private-token\n",
        "private " + valid,
        valid.replace("case=topics", "case=private-user"),
        valid.replace(
            "current-user-row=removed", "current-user-row=https://private.invalid"
        ),
        valid.replace("original-recipient=unknown", "original-recipient=match"),
        valid.replace("retry=0", "retry=2"),
        valid.replace("case=topics", "case=topics\x1b"),
        "x" * 200 + valid,
    ):
        assert parse(row) == []


def test_cleanup_records_have_finite_identity_cap() -> None:
    rows = [
        f"UE_LIVE_PUSH_CLEANUP_V1 project={project} retry={retry} case={case} "
        f"current-user-row={row} original-recipient=unknown\n"
        for project, retry, case, row in product(
            ("desktop", "mobile"),
            (0, 1),
            ("topics", "chat", "reply"),
            ("removed", "not-found", "unknown"),
        )
    ]
    records = evidence._live_playwright_push_cleanup_observations("".join(rows))
    assert len(records) == 12
    assert all(record[3] == "unknown" for record in records)


def test_runner_relays_only_closed_cleanup_classes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    row = (
        "UE_LIVE_PUSH_CLEANUP_V1 project=mobile retry=1 case=reply "
        "current-user-row=not-found original-recipient=unknown\n"
    )
    private = "private endpoint user payload token"
    stand = stand_tests.live_stand
    result = subprocess.CompletedProcess(
        stand._live_e2e_command(mode="smoke"),
        1,
        stdout=(row + private + "\n" + row.rstrip() + " " + private + "\n").encode(),
        stderr=(row + private + "\n").encode(),
    )
    stand_tests._patch_live_playwright_result(monkeypatch, result)
    with pytest.raises(stand.StandError, match="exit code 1"):
        stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    captured = capsys.readouterr()
    assert captured.out.count("live E2E push cleanup project=mobile") == 1
    assert (
        "retry=1 case=reply current-user-row=not-found original-recipient=unknown"
        in captured.out
    )
    assert private not in captured.out + captured.err
    assert captured.err == ""
