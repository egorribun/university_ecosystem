"""Closed, payload-free diagnostics for the real Profile clipboard failure."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import live_stand
from scripts import live_stand_playwright_evidence as evidence
from tests import test_live_stand as contracts

ROW = (
    "UE_LIVE_SNACKBAR_CLIPBOARD_V1 project=desktop permission=prompt "
    "secure=true focused=false clipboard=true hydrated=true enabled=true alerts=0\n"
)


def test_snackbar_diagnostic_accepts_closed_record_and_crlf() -> None:
    expected = [ROW.removeprefix("UE_LIVE_SNACKBAR_CLIPBOARD_V1 ").rstrip()]
    assert evidence._live_playwright_snackbar_clipboard_diagnostics(ROW) == expected
    assert (
        evidence._live_playwright_snackbar_clipboard_diagnostics(
            ROW.replace("\n", "\r\n")
        )
        == expected
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("desktop", "private-user"),
        ("prompt", "private-permission"),
        ("secure=true", "secure=1"),
        ("focused=false", "focused=null"),
        ("clipboard=true", "clipboard=payload"),
        ("hydrated=true", "hydrated=yes"),
        ("enabled=true", "enabled=0"),
        ("alerts=0", "alerts=-1"),
        ("alerts=0", "alerts=1000"),
        ("alerts=0", "alerts=01"),
        ("\n", ""),
        ("\n", " private-token\n"),
        ("\n", "\x1b[0m\n"),
    ],
)
def test_snackbar_diagnostic_rejects_non_protocol_text(old: str, new: str) -> None:
    assert (
        evidence._live_playwright_snackbar_clipboard_diagnostics(ROW.replace(old, new))
        == []
    )


def test_snackbar_diagnostic_deduplicates_and_caps_run_records() -> None:
    rows = [ROW.replace("alerts=0", f"alerts={i}") for i in range(8)]
    assert evidence._live_playwright_snackbar_clipboard_diagnostics(
        "".join(row * 2 for row in rows)
    ) == [
        row.removeprefix("UE_LIVE_SNACKBAR_CLIPBOARD_V1 ").rstrip() for row in rows[:4]
    ]


@pytest.mark.parametrize("code", [0, 1])
def test_snackbar_diagnostic_only_prints_sanitized_failed_run(
    code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    completed = subprocess.CompletedProcess(
        live_stand._live_e2e_command(mode="smoke"),
        code,
        stdout=("private-payload\n" + ROW + ROW.replace("prompt", "private")).encode(),
        stderr=b"private-error",
    )
    contracts._patch_live_playwright_result(monkeypatch, completed)
    if code:
        with pytest.raises(live_stand.StandError):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    printed = capsys.readouterr()
    assert "private" not in printed.out + printed.err
    retained = "live E2E snackbar clipboard " + ROW.split(" ", 1)[1]
    assert (retained in printed.out) is bool(code)
    assert printed.err == ""
