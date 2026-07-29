#!/usr/bin/env python3
"""Mutation score checker for the University Ecosystem project.

Runs ``uv run mutmut results`` and parses the output to compute:
    mutation_score = killed / (killed + survived)

Usage:
    python scripts/check_mutation_score.py [--min-score FLOAT]

Exit codes:
    0  Score meets or exceeds --min-score (default 80.0)
    1  Score is below --min-score, or mutmut could not be run / parsed
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass

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


def _parse_mutmut_output(output: str) -> MutationSummary:
    """Extract mutation counts from ``mutmut results`` output.

    WHY: mutmut writes a human-readable summary; we parse it with named
    patterns rather than relying on positional output so the parser is
    robust to minor formatting changes between mutmut versions.

    Raises:
        ValueError: when the required ``Killed`` or ``Survived`` lines are
            missing — a malformed output should surface as an explicit error
            rather than being silently treated as a zero-score run.
    """

    def _extract(pattern: re.Pattern[str], text: str, default: int = 0) -> int:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
        return default

    killed_match = _KILLED_PATTERN.search(output)
    survived_match = _SURVIVED_PATTERN.search(output)

    if killed_match is not None and survived_match is not None:
        killed = int(killed_match.group(1))
        survived = int(survived_match.group(1))
        timeout = _extract(_TIMEOUT_PATTERN, output)
        suspicious = _extract(_SUSPICIOUS_PATTERN, output)
    else:
        # Fallback for mutmut 3.x per-mutant output lines (e.g., "...: killed", "...: survived")
        killed = len(re.findall(r":\s*killed\b", output, re.IGNORECASE))
        survived = len(re.findall(r":\s*survived\b", output, re.IGNORECASE))
        timeout = len(re.findall(r":\s*timed out\b", output, re.IGNORECASE))
        suspicious = len(re.findall(r":\s*suspicious\b", output, re.IGNORECASE))
        if killed == 0 and survived == 0:
            raise ValueError(
                "Could not parse 'Killed' or 'Survived' counts from mutmut output.\n"
                f"Raw output:\n{output}"
            )

    return MutationSummary(
        killed=killed,
        survived=survived,
        timeout=timeout,
        suspicious=suspicious,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_mutmut() -> str:
    """Invoke ``uv run mutmut results`` and return stdout as a string.

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
            [uv_path, "run", "mutmut", "results"],
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
            "Compute the mutation score from mutmut results and fail "
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

    print("Running: uv run mutmut results …")
    raw_output = _run_mutmut()

    try:
        summary = _parse_mutmut_output(raw_output)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_report(summary, args.min_score)

    if summary.score < args.min_score:
        sys.exit(1)


if __name__ == "__main__":
    main()
