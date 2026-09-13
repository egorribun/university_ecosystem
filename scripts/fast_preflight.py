"""Run high-signal local checks concurrently and write an aggregate report.

This command is intentionally a developer convenience, not a replacement for
the release CI matrix.  Every check runs independently, failures are collected
instead of cancelling sibling checks, and a non-zero exit code is returned if
anything is missing, fails, or times out.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

CheckStatus = Literal["passed", "failed", "timed_out", "error"]

DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_REPORT_PATH = Path("artifacts/fast-preflight/fast-preflight.json")
_FOCUSED_TESTS = (
    "tests/contracts/test_ci_release_capacity_contract.py",
    "tests/test_frontend_ci_performance_contracts.py",
    "tests/test_workflow_fail_closed_contracts.py",
    "tests/test_fast_preflight.py",
)


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """One trusted, fixed local command in the fast-preflight suite."""

    name: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Machine-readable outcome of one preflight command."""

    name: str
    command: tuple[str, ...]
    status: CheckStatus
    exit_code: int | None
    duration_seconds: float
    stdout: str
    stderr: str
    error: str | None = None


def _python_command(*arguments: str) -> tuple[str, ...]:
    return (sys.executable, *arguments)


def _npm_executable() -> str:
    """Return the platform npm launcher without invoking a shell."""

    if os.name == "nt":
        # ``npm.cmd`` is the native Windows launcher.  Keep a plain fallback
        # so the report remains useful in a partially configured environment.
        import shutil

        return "npm.cmd" if shutil.which("npm.cmd") else "npm"
    return "npm"


def default_checks(repo_root: Path) -> tuple[CheckSpec, ...]:
    """Return the fixed high-signal checks used by the local preflight.

    The commands are deliberately explicit and shell-free.  The current
    Python interpreter is reused so ``uv run python ...`` keeps the same
    locked environment for the Python lanes.
    """

    focused_tests = tuple(str(repo_root / path) for path in _FOCUSED_TESTS)
    npm = _npm_executable()
    return (
        CheckSpec(
            "frontend-typecheck", (npm, "run", "typecheck", "--prefix", "frontend")
        ),
        CheckSpec("frontend-lint", (npm, "run", "lint", "--prefix", "frontend")),
        CheckSpec(
            "backend-typecheck",
            _python_command("-m", "mypy", "--config-file", "pyproject.toml", "app"),
        ),
        CheckSpec("backend-lint", _python_command("-m", "ruff", "check", "app")),
        CheckSpec(
            "verify-harness", _python_command("verify_harness.py", "--repo-only")
        ),
        CheckSpec(
            "focused-contract-tests",
            _python_command("-m", "pytest", "-q", *focused_tests),
        ),
    )


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate a timed-out process and its POSIX process group."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        process.kill()
        return
    killpg = getattr(os, "killpg", None)
    sigkill = getattr(signal, "SIGKILL", None)
    if callable(killpg) and isinstance(sigkill, int):
        try:
            cast(Callable[[int, int], None], killpg)(process.pid, sigkill)
            return
        except ProcessLookupError:
            return
    process.kill()


def _start_process(check: CheckSpec, *, repo_root: Path) -> subprocess.Popen[bytes]:
    """Start one trusted command without shell interpolation."""

    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603
            check.command,
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    return subprocess.Popen(  # noqa: S603
        check.command,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )


def _decode_output(value: bytes | None) -> str:
    """Decode command output deterministically without locale dependence."""

    return value.decode("utf-8", errors="replace") if value else ""


def run_check(
    check: CheckSpec,
    *,
    repo_root: Path,
    timeout_seconds: float,
    include_output: bool,
) -> CheckResult:
    """Run one check, converting launch/failure/timeout into a result."""

    del include_output  # Output retention is selected when the report is built.
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = _start_process(check, repo_root=repo_root)
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            stdout, stderr = process.communicate()
            duration = round(time.monotonic() - started, 3)
            return CheckResult(
                name=check.name,
                command=check.command,
                status="timed_out",
                exit_code=None,
                duration_seconds=duration,
                stdout=_decode_output(stdout),
                stderr=_decode_output(stderr),
                error=f"timed out after {timeout_seconds:g} seconds",
            )
    except (OSError, ValueError) as exc:
        duration = round(time.monotonic() - started, 3)
        return CheckResult(
            name=check.name,
            command=check.command,
            status="error",
            exit_code=None,
            duration_seconds=duration,
            stdout="",
            stderr="",
            error=f"could not launch check: {type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        duration = round(time.monotonic() - started, 3)
        return CheckResult(
            name=check.name,
            command=check.command,
            status="error",
            exit_code=None,
            duration_seconds=duration,
            stdout="",
            stderr="",
            error=f"unexpected runner error: {type(exc).__name__}: {exc}",
        )

    duration = round(time.monotonic() - started, 3)
    return CheckResult(
        name=check.name,
        command=check.command,
        status="passed" if process.returncode == 0 else "failed",
        exit_code=process.returncode,
        duration_seconds=duration,
        stdout=_decode_output(stdout),
        stderr=_decode_output(stderr),
    )


def run_checks(
    checks: Sequence[CheckSpec],
    *,
    repo_root: Path,
    max_workers: int,
    timeout_seconds: float,
) -> list[CheckResult]:
    """Run all checks concurrently and return results in spec order."""

    if not checks:
        raise ValueError("at least one preflight check is required")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    names = [check.name for check in checks]
    if len(names) != len(set(names)):
        raise ValueError("preflight check names must be unique")

    worker_count = min(max_workers, len(checks))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                run_check,
                check,
                repo_root=repo_root,
                timeout_seconds=timeout_seconds,
                include_output=False,
            )
            for check in checks
        ]
        return [future.result() for future in futures]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return f"[truncated to last {limit} characters]\n{value[-limit:]}"


def build_report(
    *,
    repo_root: Path,
    results: Sequence[CheckResult],
    max_workers: int,
    started_at: str,
    finished_at: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    include_output: bool = False,
    duration_seconds: float | None = None,
) -> dict[str, object]:
    """Build the local-only aggregate report without treating it as evidence."""

    serialized_results: list[dict[str, object]] = []
    for result in results:
        payload: dict[str, object] = {
            "name": result.name,
            "command": list(result.command),
            "status": result.status,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
        }
        if result.error:
            payload["error"] = result.error
        if include_output:
            payload["stdout_tail"] = _tail(result.stdout)
            payload["stderr_tail"] = _tail(result.stderr)
        serialized_results.append(payload)

    passed = bool(results) and all(result.status == "passed" for result in results)
    report: dict[str, object] = {
        "schema_version": 1,
        "report_kind": "local-fast-preflight",
        "repo_root": str(repo_root.resolve()),
        "started_at": started_at,
        "finished_at": finished_at,
        "max_workers": max_workers,
        "timeout_seconds": timeout_seconds,
        "check_count": len(results),
        "passed_count": sum(result.status == "passed" for result in results),
        "failed_count": sum(result.status != "passed" for result in results),
        "passed": passed,
        "exit_code": 0 if passed else 1,
        "checks": serialized_results,
    }
    if duration_seconds is not None:
        report["duration_seconds"] = round(duration_seconds, 3)
    return report


def write_report(path: Path, report: dict[str, object]) -> None:
    """Atomically write a UTF-8 JSON report, replacing only the requested path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(report, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _positive_number(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run trusted local typecheck, lint, harness and focused contract "
            "checks concurrently."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: detected from this script)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"JSON report path (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="maximum concurrent checks (default: one worker per check)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_number,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-check timeout (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=(
            "frontend-typecheck",
            "frontend-lint",
            "backend-typecheck",
            "backend-lint",
            "verify-harness",
            "focused-contract-tests",
        ),
        help="run only this named check; may be supplied more than once",
    )
    parser.add_argument(
        "--include-output",
        action="store_true",
        help="include bounded stdout/stderr tails in the local report",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    checks = default_checks(repo_root)
    if args.only:
        selected = set(args.only)
        checks = tuple(check for check in checks if check.name in selected)
    if not checks:
        print("No preflight checks selected.", file=sys.stderr)
        return 2

    max_workers = args.max_workers or len(checks)
    if max_workers < 1:
        print("--max-workers must be positive.", file=sys.stderr)
        return 2

    report_path = args.report
    if not report_path.is_absolute():
        report_path = repo_root / report_path
    started_at = _utc_now()
    started = time.monotonic()
    results = run_checks(
        checks,
        repo_root=repo_root,
        max_workers=max_workers,
        timeout_seconds=args.timeout_seconds,
    )
    finished_at = _utc_now()
    report = build_report(
        repo_root=repo_root,
        results=results,
        max_workers=max_workers,
        started_at=started_at,
        finished_at=finished_at,
        timeout_seconds=args.timeout_seconds,
        include_output=args.include_output,
        duration_seconds=time.monotonic() - started,
    )
    write_report(report_path, report)

    for result in results:
        label = result.status.upper()
        suffix = f" ({result.error})" if result.error else ""
        print(f"[{label}] {result.name} — {result.duration_seconds:.3f}s{suffix}")
    print(
        f"Fast preflight: {report['passed_count']}/{report['check_count']} passed; "
        f"report: {report_path}"
    )
    exit_code = report.get("exit_code")
    return exit_code if isinstance(exit_code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
