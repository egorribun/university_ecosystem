"""Semgrep exceptions live only in the exact, reviewed dispositions ledger."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# These files name the marker because they enforce this rule or document it.
ALLOWED = frozenset(
    {
        "AGENTS.md",
        "scripts/quality/validate_semgrep_sarif.py",
    }
)
ALLOWED_PREFIXES = ("docs/", "quality/", "tests/")


def test_no_tracked_source_carries_an_inline_semgrep_suppression() -> None:
    marker = "nosem" + "grep"
    tracked = subprocess.run(  # noqa: S603  # Fixed git command over this repository.
        ["git", "grep", "-l", "-I", marker],  # noqa: S607  # git comes from PATH in CI.
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    assert tracked.returncode in (0, 1), tracked.stderr
    offenders = sorted(
        path
        for path in tracked.stdout.splitlines()
        if path not in ALLOWED and not path.startswith(ALLOWED_PREFIXES)
    )
    assert offenders == []
