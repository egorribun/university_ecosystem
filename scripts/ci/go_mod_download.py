#!/usr/bin/env python3
"""Download Go modules with a narrow, bounded transport retry policy.

The Go module proxy and checksum database occasionally return transient HTTP/2
or transport failures.  Retrying every non-zero exit would hide deterministic
checksum, authentication, version, and ``go.mod`` errors, so this helper only
retries output that explicitly identifies a transport failure.  The first
failure is always retained and printed if all attempts fail.
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
DEFAULT_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60
MAX_TIMEOUT_SECONDS = 900

# Keep this allowlist deliberately narrow.  In particular, checksum mismatch,
# authentication, missing versions and malformed module metadata must fail on
# the first attempt rather than being hidden behind repeated downloads.
_TRANSIENT_FAILURE_RE = re.compile(
    r"(?:"
    r"\bstream error\b|"
    r"\binternal_error\b|"
    r"\breceived from peer\b|"
    r"\bunexpected eof\b|"
    r"\b(?:connection|network) (?:reset|refused|aborted|closed)\b|"
    r"\bi/o timeout\b|"
    r"\bcontext deadline exceeded\b|"
    r"\btemporary failure in name resolution\b|"
    r"\bcould not resolve host\b|"
    r"\bnetwork is unreachable\b|"
    r"\btls handshake timeout\b|"
    r"\b(?:http|status(?: code)?)\s*(?:408|429|500|502|503|504)\b|"
    r"\b(?:408|429|500|502|503|504)\s+(?:request timeout|too many requests|"
    r"internal server error|bad gateway|service unavailable|gateway timeout)\b"
    r")",
    re.IGNORECASE,
)
_PERMANENT_FAILURE_RE = re.compile(
    r"(?:"
    r"\bchecksum mismatch\b|"
    r"\b(?:authentication required|unauthorized|forbidden)\b|"
    r"\b(?:http|status(?: code)?)\s*(?:401|403|404)\b|"
    r"\b(?:unknown revision|invalid version|malformed module)\b"
    r")",
    re.IGNORECASE,
)


def is_transient_failure(output: str) -> bool:
    """Return whether Go output proves a retryable transport failure."""

    if _PERMANENT_FAILURE_RE.search(output):
        return False
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


def _run_go_download(
    working_directory: Path,
    *,
    go_bin: str,
    timeout_seconds: int | None,
) -> tuple[int, str]:
    """Run the fixed Go command and return its status plus combined output."""

    try:
        completed = subprocess.run(  # noqa: S603  # fixed argv; shell disabled
            [go_bin, "mod", "download"],
            cwd=working_directory,
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
            f"go mod download timed out after {timeout_seconds}s\n{stdout}{stderr}",
        )
    except OSError as error:
        return 127, f"unable to execute Go: {error}\n"

    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    return completed.returncode, output


def run(
    working_directory: Path,
    *,
    go_bin: str = "go",
    timeout_seconds: int | None = None,
    backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    """Download modules and return a process-style exit code."""

    if not working_directory.is_dir():
        print(
            f"::error::Go module directory does not exist: {working_directory}",
            file=sys.stderr,
        )
        return 2
    if timeout_seconds is not None and not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        print(
            f"::error::Go download timeout must be between 1 and {MAX_TIMEOUT_SECONDS}s",
            file=sys.stderr,
        )
        return 2
    if not 0 <= backoff_seconds <= MAX_BACKOFF_SECONDS:
        print(
            f"::error::Go download backoff must be between 0 and {MAX_BACKOFF_SECONDS}s",
            file=sys.stderr,
        )
        return 2

    first_failure: str | None = None
    last_status = 1
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, output = _run_go_download(
            working_directory,
            go_bin=go_bin,
            timeout_seconds=timeout_seconds,
        )
        last_status = status if status > 0 else 1
        print(f"--- go mod download attempt {attempt}/{MAX_ATTEMPTS} ---")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        if status == 0:
            print(f"Go modules ready on attempt {attempt}.")
            return 0

        if first_failure is None:
            first_failure = output
        if not is_transient_failure(output):
            print(
                "::error::go mod download failed with a non-transient error; "
                "retry suppressed.",
                file=sys.stderr,
            )
            return last_status
        if attempt == MAX_ATTEMPTS:
            break

        delay = backoff_seconds * attempt
        print(
            f"::warning::Transient go mod download failure on attempt {attempt}; "
            f"retrying after {delay}s.",
            file=sys.stderr,
        )
        sleep_fn(delay)

    print(
        "::error::go mod download failed after three transient attempts. "
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
    parser.add_argument("--working-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        timeout_value = os.environ.get("GO_MOD_DOWNLOAD_TIMEOUT_SECONDS")
        timeout_seconds = (
            None
            if timeout_value is None
            else _positive_seconds(
                timeout_value,
                field="GO_MOD_DOWNLOAD_TIMEOUT_SECONDS",
            )
        )
        backoff_seconds = _positive_seconds(
            os.environ.get(
                "GO_MOD_RETRY_SLEEP_BASE_SECONDS", str(DEFAULT_BACKOFF_SECONDS)
            ),
            field="GO_MOD_RETRY_SLEEP_BASE_SECONDS",
            allow_zero=True,
        )
    except ValueError as error:
        parser.error(str(error))

    return run(
        args.working_directory,
        go_bin=os.environ.get("GO_BIN", "go"),
        timeout_seconds=timeout_seconds,
        backoff_seconds=backoff_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
