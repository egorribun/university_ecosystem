"""Closed footer-console protocol and sanitized live-run reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import live_stand
from scripts import live_stand_playwright_evidence as evidence

_PREFIX = "UE_LIVE_FOOTER_CONSOLE_V1"
_PHASES = ("burst", "repeat", "drawer-open", "drawer-route", "back", "forward")
_KINDS = ("http-4xx", "http-5xx", "network", "csp", "react-418", "other", "unavailable")


def _row(
    project: str = "desktop",
    phase: str = "burst",
    kind: str = "http-4xx",
    count: str = "1",
) -> str:
    return f"{_PREFIX} project={project} phase={phase} kind={kind} count={count}\n"


@pytest.mark.parametrize("project", ("desktop", "mobile"))
@pytest.mark.parametrize("phase", _PHASES)
@pytest.mark.parametrize("kind", _KINDS)
def test_footer_console_accepts_only_closed_labels(
    project: str, phase: str, kind: str
) -> None:
    parser = getattr(
        evidence, "_live_playwright_footer_console_diagnostics", lambda _: []
    )
    assert parser(_row(project, phase, kind)) == [(project, phase, kind, 1)]


@pytest.mark.parametrize(
    "row",
    [
        _row(project="other"),
        _row(phase="unknown"),
        _row(kind="other-value"),
        _row(count="0"),
        _row(count="1000"),
        _row(count="01"),
        _row(count="-1"),
        _row(count="1.0"),
        _row().replace("_V1", "_V2"),
        _row().replace(" phase=burst", ""),
        _row().replace(" phase=burst", " phase=burst phase=repeat"),
        _row().replace("\n", " message=private-details\n"),
        _row().replace("\n", " " + "x" * 500 + "\n"),
        _row().replace("\n", "\x00\n"),
        _row().replace("project=desktop", "project=desktop\rprivate"),
        "private " + _row(),
        _row().removesuffix("\n"),
    ],
)
def test_footer_console_rejects_invalid_or_private_frames(row: str) -> None:
    parser = getattr(
        evidence, "_live_playwright_footer_console_diagnostics", lambda _: []
    )
    assert parser(row) == []


def test_footer_console_deduplicates_and_caps_completed_records() -> None:
    parser = getattr(
        evidence, "_live_playwright_footer_console_diagnostics", lambda _: []
    )
    rows = (
        _row(count="999").replace("\n", "\r\n")
        + _row(count="999")
        + _row("mobile", "repeat", "network", "2")
        + _row("desktop", "drawer-open", "csp", "3")
        + _row("mobile", "back", "other", "4")
        + _row("desktop", "forward", "react-418", "5")
    )
    assert parser(rows) == [
        ("desktop", "burst", "http-4xx", 999),
        ("mobile", "repeat", "network", 2),
        ("desktop", "drawer-open", "csp", 3),
        ("mobile", "back", "other", 4),
    ]


@pytest.mark.parametrize("exit_code", [0, 1])
def test_runner_reports_only_closed_stdout_records_and_preserves_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    exit_code: int,
) -> None:
    valid = _row("mobile", "drawer-route", "network", "2")
    private = "private-footer-console-message"
    stdout = valid + valid + _row(kind=private) + f"{private}\n"
    stderr = _row("desktop", "back", "csp", "1") + f"{private}\n"

    def run_check(check, **_kwargs):
        return live_stand.fast_preflight.CheckResult(
            name=check.name,
            command=tuple(check.command),
            status="passed" if exit_code == 0 else "failed",
            exit_code=exit_code,
            duration_seconds=0.0,
            stdout=stdout,
            stderr=stderr,
        )

    monkeypatch.setattr(live_stand.fast_preflight, "run_check", run_check)
    if exit_code:
        with pytest.raises(live_stand.StandError, match="exit code 1"):
            live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")
    else:
        live_stand._run_live_playwright(cwd=tmp_path, environment={}, mode="smoke")

    printed = capsys.readouterr()
    assert (
        printed.out.splitlines().count(
            "live E2E footer console project=mobile phase=drawer-route kind=network count=2"
        )
        == 1
    )
    assert "project=desktop phase=back" not in printed.out
    assert private not in printed.out + printed.err
    assert printed.err == ""
    assert (
        f"live E2E outcome={'failed' if exit_code else 'passed'} exit_code={exit_code}"
        in printed.out
    )
