#!/usr/bin/env python3
"""Build a locked Helm dependency set with narrowly-scoped retries.

Only failures whose output proves a transient registry/transport condition are
retried. Authentication, missing-chart, lock and chart-validation failures
fail immediately so CI does not spend minutes repeating deterministic errors.
The helper is intentionally dependency-free and is safe to run from a GitHub
Actions checkout on the hosted Ubuntu images.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_BACKOFF_SECONDS = 15

# Helm's registry client reports these conditions with several subtly
# different messages.  Keep this allowlist deliberately narrow: a generic
# retry on any non-zero exit would hide credentials, lock and chart errors.
_TRANSIENT_FAILURE_RE = re.compile(
    r"(?:"
    r"\bi/o timeout\b|"
    r"\bcontext deadline exceeded\b|"
    r"\b(?:connection|network) (?:reset|refused|aborted|closed)\b|"
    r"\btemporary failure in name resolution\b|"
    r"\bcould not resolve host\b|"
    r"\btls handshake timeout\b|"
    r"\bunexpected eof\b|"
    r"\bnetwork is unreachable\b|"
    r"\btransport is closing\b|"
    r"\b(?:too many requests|rate limit)\b|"
    r"\b(?:http|status(?: code)?)\s*(?:408|429|500|502|503|504)\b|"
    r"\b(?:408|429|500|502|503|504)\s+(?:request timeout|too many requests|"
    r"internal server error|bad gateway|service unavailable|gateway timeout)\b"
    r")",
    re.IGNORECASE,
)


def is_transient_failure(output: str) -> bool:
    """Return whether Helm output proves a retryable transport failure."""

    return bool(_TRANSIENT_FAILURE_RE.search(output))


def _positive_seconds(value: str, *, field: str, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an integer") from error
    minimum = 0 if allow_zero else 1
    if parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return parsed


def _run_helm(command: Sequence[str], *, timeout_seconds: int) -> tuple[int, str]:
    """Run Helm and return its exit status plus combined output."""

    try:
        completed = subprocess.run(  # noqa: S603  # fixed Helm argv; shell execution is disabled
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return (
            124,
            f"Helm dependency build timed out after {timeout_seconds}s\n{stdout}{stderr}",
        )
    except OSError as error:
        return 127, f"unable to execute Helm: {error}\n"
    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    return completed.returncode, output


def _validate_required_names(names: Sequence[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for name in names:
        path = Path(name)
        if (
            not name
            or path.is_absolute()
            or path.name != name
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
        ):
            raise ValueError(
                f"required dependency must be a plain archive name: {name!r}"
            )
        validated.append(name)
    return tuple(validated)


def _missing_required(chart: Path, required: Sequence[str]) -> tuple[str, ...]:
    missing: list[str] = []
    for name in required:
        candidate = chart / "charts" / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size == 0
        ):
            missing.append(name)
    return tuple(missing)


def run(
    chart: Path,
    *,
    skip_refresh: bool = False,
    required: Sequence[str] = (),
    helm_bin: str = "helm",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Build dependencies and return a process-style exit code."""

    if not chart.is_dir():
        print(f"::error::Helm chart directory does not exist: {chart}", file=sys.stderr)
        return 2
    try:
        validated_required = _validate_required_names(required)
    except ValueError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 2
    if timeout_seconds < 1 or backoff_seconds < 0:
        print("::error::Helm timeout/backoff values are invalid", file=sys.stderr)
        return 2

    command = [helm_bin, "dependency", "build"]
    if skip_refresh:
        command.append("--skip-refresh")
    command.append(str(chart))
    first_failure: str | None = None
    last_status = 1

    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, output = _run_helm(command, timeout_seconds=timeout_seconds)
        last_status = status if status > 0 else 1
        print(f"--- Helm dependency build attempt {attempt}/{MAX_ATTEMPTS} ---")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        if status == 0:
            missing = _missing_required(chart, validated_required)
            if missing:
                print(
                    "::error::Helm succeeded but required dependency archives are missing: "
                    + ", ".join(missing),
                    file=sys.stderr,
                )
                return 1
            print(f"Helm dependencies ready on attempt {attempt}.")
            return 0

        if first_failure is None:
            first_failure = output
        if not is_transient_failure(output):
            print(
                "::error::Helm dependency build failed with a non-transient error; "
                "retry suppressed.",
                file=sys.stderr,
            )
            return last_status
        if attempt == MAX_ATTEMPTS:
            break
        delay = backoff_seconds * attempt
        print(
            f"::warning::Transient Helm failure on attempt {attempt}; "
            f"retrying after {delay}s.",
            file=sys.stderr,
        )
        sleep_fn(delay)

    print(
        "::error::Helm dependency build failed after three transient attempts. "
        "First failure output follows:",
        file=sys.stderr,
    )
    if first_failure:
        print(
            first_failure,
            end="" if first_failure.endswith("\n") else "\n",
            file=sys.stderr,
        )
    return last_status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chart", type=Path)
    parser.add_argument(
        "required", nargs="*", help="required archive names under chart/charts"
    )
    parser.add_argument("--skip-refresh", action="store_true")
    args = parser.parse_args(argv)
    try:
        timeout_seconds = _positive_seconds(
            os.environ.get(
                "HELM_DEPENDENCY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)
            ),
            field="HELM_DEPENDENCY_TIMEOUT_SECONDS",
        )
        backoff_seconds = _positive_seconds(
            os.environ.get(
                "HELM_RETRY_SLEEP_BASE_SECONDS", str(DEFAULT_BACKOFF_SECONDS)
            ),
            field="HELM_RETRY_SLEEP_BASE_SECONDS",
            allow_zero=True,
        )
    except ValueError as error:
        parser.error(str(error))
    return run(
        args.chart,
        skip_refresh=args.skip_refresh,
        required=args.required,
        timeout_seconds=timeout_seconds,
        backoff_seconds=backoff_seconds,
        helm_bin=os.environ.get("HELM_BIN", "helm"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
