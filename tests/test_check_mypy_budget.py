"""Fail closed when the mypy process fails without normal error diagnostics."""

import shutil
import subprocess

import pytest

from scripts import check_mypy_budget


@pytest.mark.parametrize(
    ("budget", "returncode", "stdout", "stderr", "expected"),
    [
        (0, 0, "", "", 0),
        (0, 0, "Success: no issues found in 1 source file\n", "", 0),
        (0, 1, "app/example.py:1: error: incompatible type\n", "", 1),
        (0, 0, "app/example.py:1: error: incompatible type\n", "", 1),
        (0, 1, "", "mypy could not start\n", 1),
        (0, 2, "", "mypy: invalid option\n", 1),
        (0, -9, "", "", 1),
        (1, 1, "app/example.py:1: error: incompatible type\n", "", 0),
        (1, 2, "app/example.py:1: error: incompatible type\n", "fatal error\n", 1),
    ],
    ids=[
        "clean-empty",
        "clean-summary",
        "type-errors",
        "diagnostics-with-zero-exit",
        "failure-without-diagnostics",
        "usage-failure",
        "terminated-process",
        "diagnostic-within-test-budget",
        "fatal-despite-test-budget",
    ],
)
def test_mypy_budget_rejects_process_failures_and_enforces_error_budget(
    monkeypatch, capsys, budget, returncode, stdout, stderr, expected
):
    assert check_mypy_budget.ERROR_BUDGET == 0
    monkeypatch.setattr(check_mypy_budget, "ERROR_BUDGET", budget)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    monkeypatch.setattr(check_mypy_budget.subprocess, "run", run)
    with pytest.raises(SystemExit) as exc_info:
        check_mypy_budget.main()

    assert exc_info.value.code == expected
    assert calls == [
        (
            [
                "/usr/bin/uv",
                "run",
                "mypy",
                "app",
                "--no-error-summary",
                "--hide-error-context",
            ],
            {"capture_output": True, "text": True, "encoding": "utf-8"},
        )
    ]
    output = capsys.readouterr().out
    assert ("[PASS]" in output) is (expected == 0)
    if expected:
        assert "[FAIL]" in output
