#!/usr/bin/env python3
"""Mutation score checker for the University Ecosystem project.

Runs ``uv run mutmut results --all`` and parses the output to compute:
    mutation_score = killed / (killed + survived)

Usage:
    python scripts/check_mutation_score.py [--min-score FLOAT]

Exit codes:
    0  Score meets or exceeds --min-score (default 80.0)
    1  Score is below --min-score, or mutmut could not be run / parsed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MutationSummary:
    """Parsed mutation testing summary."""

    killed: int
    survived: int
    timeout: int
    suspicious: int
    no_tests: int
    not_checked: int

    @property
    def total_meaningful(self) -> int:
        """Killed + survived — the denominator for score calculation."""
        return self.killed + self.survived

    @property
    def score(self) -> float:
        """Mutation score as a value between 0.0 and 100.0.

        When no mutants survived (survived == 0), score is 100.0%.
        """
        if self.total_meaningful == 0:
            return 100.0 if self.survived == 0 else 0.0
        return (self.killed / self.total_meaningful) * 100.0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


# Example mutmut output:
#   Killed: 312
#   Survived: 88
#   Timed out: 3
#   Suspicious: 2
_KILLED_PATTERN = re.compile(r"Killed[:\s]+(\d+)", re.IGNORECASE)
_SURVIVED_PATTERN = re.compile(r"Survived[:\s]+(\d+)", re.IGNORECASE)
_TIMEOUT_PATTERN = re.compile(r"Timed\s+out[:\s]+(\d+)", re.IGNORECASE)
_SUSPICIOUS_PATTERN = re.compile(r"Suspicious[:\s]+(\d+)", re.IGNORECASE)
_NO_TESTS_PATTERN = re.compile(r"No\s+tests[:\s]+(\d+)", re.IGNORECASE)
_NOT_CHECKED_PATTERN = re.compile(r"Not\s+checked[:\s]+(\d+)", re.IGNORECASE)

_STATUS_PATTERNS = {
    "killed": re.compile(r":\s*killed\b", re.IGNORECASE),
    "survived": re.compile(r":\s*survived\b", re.IGNORECASE),
    "timeout": re.compile(r":\s*(?:timed\s+out|timeout)\b", re.IGNORECASE),
    "suspicious": re.compile(r":\s*suspicious\b", re.IGNORECASE),
    "no_tests": re.compile(r":\s*no\s+tests\b", re.IGNORECASE),
    "not_checked": re.compile(r":\s*not\s+checked\b", re.IGNORECASE),
}


def _parse_mutmut_output(output: str) -> MutationSummary:
    """Extract mutation counts from the complete ``mutmut results --all`` output.

    ``mutmut results`` hides killed mutants unless ``--all`` is supplied. The
    checker therefore consumes the complete per-mutant status stream directly;
    it must not infer a score from a stale or platform-specific run-log path.
    """

    def _extract(pattern: re.Pattern[str], text: str, default: int = 0) -> int:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
        return default

    status_counts = {
        name: len(pattern.findall(output)) for name, pattern in _STATUS_PATTERNS.items()
    }

    if any(status_counts.values()):
        return MutationSummary(
            killed=status_counts["killed"],
            survived=status_counts["survived"],
            timeout=status_counts["timeout"],
            suspicious=status_counts["suspicious"],
            no_tests=status_counts["no_tests"],
            not_checked=status_counts["not_checked"],
        )

    killed_match = _KILLED_PATTERN.search(output)
    survived_match = _SURVIVED_PATTERN.search(output)
    if killed_match is None or survived_match is None:
        raise ValueError(
            "Could not parse 'Killed' or 'Survived' counts from mutmut output.\n"
            f"Raw output:\n{output}"
        )

    return MutationSummary(
        killed=int(killed_match.group(1)),
        survived=int(survived_match.group(1)),
        timeout=_extract(_TIMEOUT_PATTERN, output),
        suspicious=_extract(_SUSPICIOUS_PATTERN, output),
        no_tests=_extract(_NO_TESTS_PATTERN, output),
        not_checked=_extract(_NOT_CHECKED_PATTERN, output),
    )


def _parse_cicd_stats(payload: str | bytes | dict[str, Any]) -> MutationSummary:
    """Parse mutmut's authoritative ``export-cicd-stats`` JSON.

    mutmut 3.5.0 can produce an empty stdout stream for ``results --all``
    after a positional mutation shard, while its JSON exporter still records
    the complete per-mutant state. Prefer this machine-readable contract in
    CI; the text parser remains a backwards-compatible fallback for local
    invocations that do not have an exported stats file.
    """

    data: Any
    if isinstance(payload, dict):
        data = payload
    else:
        data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("mutmut CI stats must be a JSON object")

    def _count(name: str) -> int:
        value = data.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"mutmut CI stats field {name!r} must be a non-negative integer"
            )
        return value

    killed = _count("killed")
    survived = _count("survived")
    total = _count("total")
    no_tests = _count("no_tests")
    skipped = _count("skipped")
    suspicious = _count("suspicious")
    timeout = _count("timeout")
    interrupted = _count("check_was_interrupted_by_user")
    segfault = _count("segfault")
    caught_by_type_check = _count("caught_by_type_check")

    known = (
        killed
        + survived
        + no_tests
        + skipped
        + suspicious
        + timeout
        + interrupted
        + segfault
        + caught_by_type_check
    )
    if total < known:
        raise ValueError(
            "mutmut CI stats total is smaller than the sum of its status counts"
        )

    return MutationSummary(
        killed=killed,
        survived=survived,
        timeout=timeout,
        suspicious=suspicious,
        no_tests=no_tests,
        not_checked=total - known,
    )


def _load_cicd_stats(
    path: Path = Path("mutants/mutmut-cicd-stats.json"),
) -> MutationSummary | None:
    """Load an exported mutmut stats file when the current run produced one."""

    if not path.is_file():
        return None
    try:
        return _parse_cicd_stats(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Could not parse mutmut CI stats at {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_mutmut() -> str:
    """Invoke ``uv run mutmut results --all`` and return stdout as a string.

    WHY: using subprocess keeps this script dependency-free (stdlib only).
    We capture stderr separately so that diagnostic messages from mutmut
    do not contaminate the parseable stdout.

    Raises:
        SystemExit(1): when the subprocess itself cannot be launched (e.g.,
            ``uv`` not on PATH) or returns a non-zero exit code that is not
            an expected mutmut status code.
    """
    import shutil

    uv_path = shutil.which("uv")
    if uv_path is None:
        print(
            "ERROR: 'uv' binary not found on PATH. Install it with: pip install uv",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = subprocess.run(
            [uv_path, "run", "mutmut", "results", "--all"],
            capture_output=True,
            text=True,
            check=False,  # We check the return code manually below
        )
    except FileNotFoundError:
        print(
            "ERROR: 'uv' binary not found on PATH. Install it with: pip install uv",
            file=sys.stderr,
        )
        sys.exit(1)

    if result.returncode not in (0, 1, 2):
        # mutmut exits 1 when there are survived mutants — that is expected.
        # Any other non-zero code is a real failure (e.g., syntax error, crash).
        print(
            f"ERROR: mutmut exited with unexpected code {result.returncode}.",
            file=sys.stderr,
        )
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)

    return result.stdout


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _print_report(summary: MutationSummary, min_score: float) -> None:
    """Print a human-readable mutation score report to stdout."""
    bar_width = 40
    fill = int((summary.score / 100.0) * bar_width)
    bar = "█" * fill + "░" * (bar_width - fill)

    print()
    print("═" * 52)
    print("  Mutation Score Report")
    print("═" * 52)
    print(f"  Killed     : {summary.killed:>6}")
    print(f"  Survived   : {summary.survived:>6}")
    print(f"  Timed out  : {summary.timeout:>6}")
    print(f"  Suspicious : {summary.suspicious:>6}")
    print(f"  No tests   : {summary.no_tests:>6}")
    print(f"  Not checked: {summary.not_checked:>6}")
    print(f"  Total (K+S): {summary.total_meaningful:>6}")
    print()
    print(f"  Score  [{bar}]  {summary.score:.2f}%")
    print(f"  Target : {min_score:.2f}%")
    print()
    if summary.score >= min_score:
        print(f"  ✅  PASS — score {summary.score:.2f}% ≥ min {min_score:.2f}%")
    else:
        delta = min_score - summary.score
        print(
            f"  ❌  FAIL — score {summary.score:.2f}% is {delta:.2f}pp "
            f"below the required {min_score:.2f}%"
        )
    print("═" * 52)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute the mutation score from mutmut results --all and fail "
            "if it is below the required minimum."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=80.0,
        metavar="FLOAT",
        help=(
            "Minimum acceptable mutation score (0–100). "
            "Defaults to 80.0. Exits with code 1 if below this threshold."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, run mutmut, compute score, exit accordingly."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not (0.0 <= args.min_score <= 100.0):
        print(
            f"ERROR: --min-score must be between 0 and 100 (got {args.min_score}).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        summary = _load_cicd_stats()
        if summary is None:
            print("Running: uv run mutmut results --all …")
            summary = _parse_mutmut_output(_run_mutmut())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_report(summary, args.min_score)

    if summary.score < args.min_score:
        sys.exit(1)


if __name__ == "__main__":
    main()
