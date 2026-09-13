"""Unit contracts for the local parallel fast-preflight runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import fast_preflight


def test_makefile_exposes_the_local_fast_preflight_command() -> None:
    makefile = Path(__file__).resolve().parents[1] / "Makefile"
    content = makefile.read_text(encoding="utf-8")

    assert any(
        line.startswith(".PHONY:") and "fast-preflight" in line
        for line in content.splitlines()
    )
    assert "fast-preflight:" in content
    assert "uv run python scripts/fast_preflight.py" in content


def test_default_checks_cover_frontend_backend_harness_and_focused_contracts() -> None:
    checks = fast_preflight.default_checks(Path("/repo"))

    assert [check.name for check in checks] == [
        "frontend-typecheck",
        "frontend-lint",
        "backend-typecheck",
        "backend-lint",
        "verify-harness",
        "focused-contract-tests",
    ]
    assert Path(checks[0].command[0]).name.lower() in {"npm", "npm.cmd"}
    assert checks[0].command[1:3] == ("run", "typecheck")
    assert checks[1].command[1:3] == ("run", "lint")
    assert checks[2].command[:3] == (sys.executable, "-m", "mypy")
    assert checks[3].command[:3] == (sys.executable, "-m", "ruff")
    assert checks[4].command[:2] == (sys.executable, "verify_harness.py")
    assert checks[5].command[:3] == (sys.executable, "-m", "pytest")
    normalized_command = [item.replace("\\", "/") for item in checks[5].command]
    assert any(
        item.endswith("/tests/contracts/test_ci_release_capacity_contract.py")
        for item in normalized_command
    )


def test_run_checks_executes_all_checks_and_preserves_spec_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checks = (
        fast_preflight.CheckSpec("first", ("first",)),
        fast_preflight.CheckSpec("second", ("second",)),
        fast_preflight.CheckSpec("third", ("third",)),
    )
    started: list[str] = []

    def fake_run(
        check: fast_preflight.CheckSpec,
        *,
        repo_root: Path,
        timeout_seconds: float,
        include_output: bool,
    ) -> fast_preflight.CheckResult:
        del repo_root, timeout_seconds, include_output
        started.append(check.name)
        return fast_preflight.CheckResult(
            name=check.name,
            command=check.command,
            status="passed",
            exit_code=0,
            duration_seconds=0.01,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(fast_preflight, "run_check", fake_run)
    results = fast_preflight.run_checks(
        checks, repo_root=tmp_path, max_workers=2, timeout_seconds=1
    )

    assert [result.name for result in results] == ["first", "second", "third"]
    assert sorted(started) == ["first", "second", "third"]


def test_aggregate_report_is_failed_closed_and_writes_json(tmp_path: Path) -> None:
    results = [
        fast_preflight.CheckResult(
            name="pass",
            command=("pass",),
            status="passed",
            exit_code=0,
            duration_seconds=0.1,
            stdout="secret-looking output",
            stderr="",
        ),
        fast_preflight.CheckResult(
            name="fail",
            command=("fail",),
            status="failed",
            exit_code=1,
            duration_seconds=0.2,
            stdout="",
            stderr="failure",
        ),
    ]
    report_path = tmp_path / "nested" / "report.json"

    report = fast_preflight.build_report(
        repo_root=tmp_path,
        results=results,
        max_workers=2,
        started_at="2026-09-13T00:00:00Z",
        finished_at="2026-09-13T00:00:01Z",
    )
    fast_preflight.write_report(report_path, report)

    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert loaded["passed"] is False
    assert loaded["exit_code"] == 1
    assert loaded["checks"][0]["status"] == "passed"
    assert loaded["checks"][1]["status"] == "failed"
    assert "secret-looking output" not in report_path.read_text(encoding="utf-8")


def test_run_check_marks_timeout_and_does_not_raise(tmp_path: Path) -> None:
    check = fast_preflight.CheckSpec(
        "slow",
        (sys.executable, "-c", "import time; time.sleep(2)"),
    )

    result = fast_preflight.run_check(
        check,
        repo_root=tmp_path,
        timeout_seconds=0.05,
        include_output=False,
    )

    assert result.status == "timed_out"
    assert result.exit_code is None


def test_run_check_reports_missing_executable_without_raising(tmp_path: Path) -> None:
    check = fast_preflight.CheckSpec("missing", ("definitely-not-a-real-program",))

    result = fast_preflight.run_check(
        check,
        repo_root=tmp_path,
        timeout_seconds=1,
        include_output=False,
    )

    assert result.status == "error"
    assert result.exit_code is None
    assert result.error


def test_main_returns_nonzero_for_failed_check_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = fast_preflight.CheckSpec("only", ("only",))
    monkeypatch.setattr(fast_preflight, "default_checks", lambda _: (check,))
    monkeypatch.setattr(
        fast_preflight,
        "run_checks",
        lambda *args, **kwargs: [
            fast_preflight.CheckResult(
                name="only",
                command=("only",),
                status="failed",
                exit_code=1,
                duration_seconds=0.1,
                stdout="",
                stderr="bad",
            )
        ],
    )

    report_path = tmp_path / "report.json"
    exit_code = fast_preflight.main(
        ["--repo-root", str(tmp_path), "--report", str(report_path)]
    )

    assert exit_code == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["exit_code"] == 1
