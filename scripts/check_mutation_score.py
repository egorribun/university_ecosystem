#!/usr/bin/env python3
"""Mutation score checker for the University Ecosystem project.

Runs ``uv run mutmut results --all`` and parses the output to compute the
viable mutation score:
    mutation_score = accepted_kills / (accepted_kills + survived)

Only a killed mutant or a mutant caught by a configured type checker is an
accepted kill. Any incomplete or unclassified mutmut status fails the gate.

Usage:
    python scripts/check_mutation_score.py [--min-score FLOAT]

Exit codes:
    0  Score meets or exceeds --min-score (default 100.0)
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
    skipped: int = 0
    interrupted: int = 0
    segfault: int = 0
    caught_by_type_check: int = 0

    @property
    def accepted_kills(self) -> int:
        """Mutants conclusively rejected by tests or a configured type checker."""
        return self.killed + self.caught_by_type_check

    @property
    def total_meaningful(self) -> int:
        """Accepted kills + survivors — the viable-score denominator."""
        return self.accepted_kills + self.survived

    @property
    def incomplete_statuses(self) -> dict[str, int]:
        """Statuses that cannot serve as complete mutation-test evidence."""
        return {
            name: count
            for name, count in (
                ("timeout", self.timeout),
                ("suspicious", self.suspicious),
                ("no_tests", self.no_tests),
                ("not_checked", self.not_checked),
                ("skipped", self.skipped),
                ("interrupted", self.interrupted),
                ("segfault", self.segfault),
            )
            if count
        }

    @property
    def score(self) -> float:
        """Mutation score as a value between 0.0 and 100.0.

        An empty viable-mutant universe is not a passing score.
        """
        if self.total_meaningful == 0:
            return 0.0
        return (self.accepted_kills / self.total_meaningful) * 100.0


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
_SKIPPED_PATTERN = re.compile(r"Skipped[:\s]+(\d+)", re.IGNORECASE)
_INTERRUPTED_PATTERN = re.compile(
    r"(?:Check\s+was\s+)?interrupted(?:\s+by\s+user)?[:\s]+(\d+)",
    re.IGNORECASE,
)
_SEGFAULT_PATTERN = re.compile(r"Segfault[:\s]+(\d+)", re.IGNORECASE)
_CAUGHT_BY_TYPE_CHECK_PATTERN = re.compile(
    r"Caught\s+by\s+type\s+check[:\s]+(\d+)", re.IGNORECASE
)

_STATUS_PATTERNS = {
    "killed": re.compile(r":\s*killed\b", re.IGNORECASE),
    "survived": re.compile(r":\s*survived\b", re.IGNORECASE),
    "timeout": re.compile(r":\s*(?:timed\s+out|timeout)\b", re.IGNORECASE),
    "suspicious": re.compile(r":\s*suspicious\b", re.IGNORECASE),
    "no_tests": re.compile(r":\s*no\s+tests\b", re.IGNORECASE),
    "not_checked": re.compile(r":\s*not\s+checked\b", re.IGNORECASE),
    "skipped": re.compile(r":\s*skipped\b", re.IGNORECASE),
    "interrupted": re.compile(
        r":\s*(?:check\s+was\s+)?interrupted(?:\s+by\s+user)?\b",
        re.IGNORECASE,
    ),
    "segfault": re.compile(r":\s*segfault\b", re.IGNORECASE),
    "caught_by_type_check": re.compile(
        r":\s*caught\s+by\s+type\s+check\b", re.IGNORECASE
    ),
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
            skipped=status_counts["skipped"],
            interrupted=status_counts["interrupted"],
            segfault=status_counts["segfault"],
            caught_by_type_check=status_counts["caught_by_type_check"],
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
        skipped=_extract(_SKIPPED_PATTERN, output),
        interrupted=_extract(_INTERRUPTED_PATTERN, output),
        segfault=_extract(_SEGFAULT_PATTERN, output),
        caught_by_type_check=_extract(_CAUGHT_BY_TYPE_CHECK_PATTERN, output),
    )


def _parse_cicd_stats(payload: str | bytes | dict[str, Any]) -> MutationSummary:
    """Parse the machine-readable mutmut CI/CD statistics JSON.

    mutmut can produce an empty stdout stream for ``results --all``
    after a positional mutation shard. CI supplies the exact-shard or complete
    universe JSON produced by ``export_mutmut_shard_stats.py``; the text parser
    remains a backwards-compatible fallback for local invocations that do not
    have an exported stats file.
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
        skipped=skipped,
        interrupted=interrupted,
        segfault=segfault,
        caught_by_type_check=caught_by_type_check,
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
    print(f"  Type check : {summary.caught_by_type_check:>6}")
    print(f"  Survived   : {summary.survived:>6}")
    print(f"  Timed out  : {summary.timeout:>6}")
    print(f"  Suspicious : {summary.suspicious:>6}")
    print(f"  No tests   : {summary.no_tests:>6}")
    print(f"  Not checked: {summary.not_checked:>6}")
    print(f"  Skipped    : {summary.skipped:>6}")
    print(f"  Interrupted: {summary.interrupted:>6}")
    print(f"  Segfault   : {summary.segfault:>6}")
    print(f"  Total (A+S): {summary.total_meaningful:>6}")
    print()
    print(f"  Score  [{bar}]  {summary.score:.2f}%")
    print(f"  Target : {min_score:.2f}%")
    print()
    if summary.incomplete_statuses:
        statuses = ", ".join(
            f"{name}={count}" for name, count in summary.incomplete_statuses.items()
        )
        print(f"  ❌  FAIL — incomplete mutation evidence: {statuses}")
    elif summary.score >= min_score:
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
        default=100.0,
        metavar="FLOAT",
        help=(
            "Minimum acceptable mutation score (0–100). "
            "Defaults to 100.0. Exits with code 1 if below this threshold."
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

    if summary.incomplete_statuses or summary.score < args.min_score:
        sys.exit(1)


if __name__ == "__main__":
    main()
