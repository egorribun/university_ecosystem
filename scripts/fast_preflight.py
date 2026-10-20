"""Run high-signal local checks concurrently and write an aggregate report.

This command is intentionally a developer convenience, not a replacement for
the release CI matrix.  Every check runs independently, failures are collected
instead of cancelling sibling checks, and a non-zero exit code is returned if
anything is missing, fails, or times out.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, cast

CheckStatus = Literal["passed", "failed", "timed_out", "error"]

DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_REPORT_PATH = Path("artifacts/fast-preflight/fast-preflight.json")
_WINDOWS_POLL_INTERVAL_SECONDS = 0.01
_WINDOWS_READ_CHUNK_BYTES = 64 * 1024
_TIMEOUT_CLEANUP_GRACE_SECONDS = 0.25
_ERROR_BROKEN_PIPE = 109
_WINDOWS_PEEK_NAMED_PIPE: object | None = None
_WINDOWS_KERNEL32: object | None = None
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FOCUSED_TESTS = (
    "tests/contracts/test_ci_release_capacity_contract.py",
    "tests/test_duration_sharding_contract.py",
    "tests/test_frontend_ci_performance_contracts.py",
    "tests/test_workflow_fail_closed_contracts.py",
    "tests/test_fast_preflight.py",
    "tests/test_nightly_helm_reuse_contract.py",
    "tests/test_scheduled_workflow_regressions.py",
    # Fast repository ledgers that a hosted run otherwise catches first.
    "tests/test_route_dependency_inventory.py",
    "tests/test_quality_configuration.py",
    "tests/test_quality_workflow_contract.py",
    "tests/test_domain_event_registry_contract.py",
    "tests/test_mfa_openapi_artifacts_contract.py",
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
        # Mirror the remaining Frontend "Lint & Format" static gates that are
        # fast enough for a local preflight.
        CheckSpec(
            "frontend-format", (npm, "run", "format:check", "--prefix", "frontend")
        ),
        CheckSpec("frontend-i18n", (npm, "run", "i18n:check", "--prefix", "frontend")),
        CheckSpec(
            "message-contract",
            _python_command("scripts/generate_message_contract.py", "--check"),
        ),
        CheckSpec(
            "backend-typecheck",
            _python_command("-m", "mypy", "--config-file", "pyproject.toml", "app"),
        ),
        CheckSpec("backend-lint", _python_command("-m", "ruff", "check", "app")),
        CheckSpec(
            "verify-harness", _python_command("verify_harness.py", "--repo-only")
        ),
        CheckSpec(
            "ci-check-catalog",
            _python_command("scripts/quality/validate_ci_check_catalog.py"),
        ),
        CheckSpec(
            "focused-contract-tests",
            _python_command(
                "-m", "pytest", "-q", "-p", "no:cacheprovider", *focused_tests
            ),
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


def _start_process(
    check: CheckSpec,
    *,
    repo_root: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    """Start one trusted command without shell interpolation."""
    environment = None if env is None else dict(env)

    if os.name == "nt":
        return subprocess.Popen(  # noqa: S603
            check.command,
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            env=environment,
        )
    return subprocess.Popen(  # noqa: S603
        check.command,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
        env=environment,
    )


def _decode_output(value: bytes | None) -> str:
    """Decode command output deterministically without locale dependence."""

    return value.decode("utf-8", errors="replace") if value else ""


def _windows_peek_named_pipe_api() -> Callable[..., int]:
    """Load PeekNamedPipe once for direct, nonblocking-by-availability reads."""

    global _WINDOWS_KERNEL32, _WINDOWS_PEEK_NAMED_PIPE
    if _WINDOWS_PEEK_NAMED_PIPE is None:
        import ctypes
        from ctypes import wintypes

        loader_name = "WinDLL"
        loader = cast(Callable[..., object], getattr(ctypes, loader_name))
        kernel32 = loader("kernel32", use_last_error=True)
        api_name = "PeekNamedPipe"
        peek = getattr(kernel32, api_name)
        peek.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        )
        peek.restype = wintypes.BOOL
        _WINDOWS_KERNEL32 = kernel32
        _WINDOWS_PEEK_NAMED_PIPE = peek
    return cast(Callable[..., int], _WINDOWS_PEEK_NAMED_PIPE)


def _peek_windows_pipe_available(stream: BinaryIO) -> int | None:
    """Return available bytes, or None only when the pipe writer is gone."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    available = wintypes.DWORD()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
    peek_named_pipe = _windows_peek_named_pipe_api()
    succeeded = peek_named_pipe(
        handle,
        None,
        0,
        None,
        ctypes.byref(available),
        None,
    )
    if succeeded:
        return int(available.value)

    get_last_error_name = "get_last_error"
    get_last_error = cast(Callable[[], int], getattr(ctypes, get_last_error_name))
    error_code = get_last_error()
    if error_code == _ERROR_BROKEN_PIPE:
        return None
    win_error_name = "WinError"
    win_error = cast(Callable[[int], OSError], getattr(ctypes, win_error_name))
    raise win_error(error_code)


def _is_windows_broken_pipe(exc: OSError) -> bool:
    """Recognize only Win32's explicit broken-pipe condition as EOF."""

    platform_error_attribute = "winerror"
    return getattr(exc, platform_error_attribute, None) == _ERROR_BROKEN_PIPE


def _drain_windows_pipes(
    process: subprocess.Popen[bytes],
    *,
    stdout: bytearray,
    stderr: bytearray,
    deadline: float,
) -> bool:
    """Drain each available pipe chunk fairly until EOF, exit, or deadline.

    This avoids ``Popen.communicate``'s Windows background reader threads. The
    parent thread uses PeekNamedPipe before every bounded ``os.read`` and is the
    sole reader for these handles, so closing them after the loop cannot wait
    on a BufferedReader lock held by another thread.
    """

    streams: tuple[BinaryIO | None, BinaryIO | None] = (
        process.stdout,
        process.stderr,
    )
    buffers = (stdout, stderr)
    open_pipes = [stream is not None for stream in streams]

    while True:
        if time.monotonic() >= deadline:
            return False
        made_progress = False
        for index, stream in enumerate(streams):
            if not open_pipes[index] or stream is None:
                continue
            available = _peek_windows_pipe_available(stream)
            if available is None:
                open_pipes[index] = False
                continue
            if available < 0:
                raise OSError("PeekNamedPipe returned a negative byte count")
            if available == 0:
                continue

            read_size = min(available, _WINDOWS_READ_CHUNK_BYTES)
            try:
                chunk = os.read(stream.fileno(), read_size)
            except OSError as exc:
                if _is_windows_broken_pipe(exc):
                    open_pipes[index] = False
                    continue
                raise
            if not chunk:
                raise OSError(
                    "PeekNamedPipe reported available bytes but the pipe read was empty"
                )
            buffers[index].extend(chunk)
            made_progress = True

        if all(not is_open for is_open in open_pipes) and process.poll() is not None:
            return True

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if not made_progress:
            time.sleep(min(_WINDOWS_POLL_INTERVAL_SECONDS, remaining))


def _remaining_seconds(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _bounded_process_wait(
    process: subprocess.Popen[bytes], *, timeout_seconds: float
) -> bool:
    """Wait only for the supplied finite interval; never drain inherited pipes."""

    if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
        return False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _close_process_pipes(process: subprocess.Popen[bytes]) -> tuple[str, ...]:
    """Close only this process object's parent-side pipe handles."""

    errors: list[str] = []
    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        if stream is None or stream.closed:
            continue
        try:
            stream.close()
        except (OSError, ValueError) as exc:
            errors.append(f"{name} close failed: {type(exc).__name__}")
    return tuple(errors)


def _cleanup_after_runner_error(process: subprocess.Popen[bytes]) -> tuple[str, ...]:
    """Bound cleanup after a read/runner error without touching unrelated PIDs."""

    errors: list[str] = []
    try:
        if process.poll() is None:
            _terminate_process(process)
    except OSError as exc:
        errors.append(f"termination failed: {type(exc).__name__}")

    deadline = time.monotonic() + _TIMEOUT_CLEANUP_GRACE_SECONDS
    if not _bounded_process_wait(process, timeout_seconds=_remaining_seconds(deadline)):
        errors.append("direct process did not exit within cleanup grace")
    errors.extend(_close_process_pipes(process))
    return tuple(errors)


def _timeout_cleanup_details(
    process: subprocess.Popen[bytes],
    *,
    stdout: bytearray,
    stderr: bytearray,
    deadline: float,
) -> tuple[str, ...]:
    """Drain/close owned handles and report any bounded cleanup limitation."""

    errors: list[str] = []
    try:
        drained = _drain_windows_pipes(
            process, stdout=stdout, stderr=stderr, deadline=deadline
        )
    except (OSError, ValueError) as exc:
        errors.append(f"pipe drain failed: {type(exc).__name__}")
    else:
        if not drained:
            errors.append("process output did not drain within cleanup grace")

    if not _bounded_process_wait(process, timeout_seconds=_remaining_seconds(deadline)):
        errors.append("direct process did not exit within cleanup grace")
    errors.extend(_close_process_pipes(process))
    return tuple(errors)


def _terminate_for_timeout(process: subprocess.Popen[bytes]) -> tuple[str, ...]:
    """Attempt owned-process termination without losing a timeout to an exit race."""

    try:
        _terminate_process(process)
    except OSError as exc:
        if process.poll() is None:
            return (f"termination failed: {type(exc).__name__}",)
    return ()


def run_check(
    check: CheckSpec,
    *,
    repo_root: Path,
    timeout_seconds: float,
    include_output: bool,
) -> CheckResult:
    """Run one check, converting launch/failure/timeout into a result."""

    del include_output  # Output retention is selected when the report is built.
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    stdout: bytes = b""
    stderr: bytes = b""
    stdout_buffer: bytearray | None = None
    stderr_buffer: bytearray | None = None
    try:
        process = _start_process(check, repo_root=repo_root)
        if os.name == "nt":
            stdout_buffer = bytearray()
            stderr_buffer = bytearray()
            deadline = time.monotonic() + timeout_seconds
            completed = _drain_windows_pipes(
                process,
                stdout=stdout_buffer,
                stderr=stderr_buffer,
                deadline=deadline,
            )
            stdout = bytes(stdout_buffer)
            stderr = bytes(stderr_buffer)
            if not completed:
                cleanup_errors = list(_terminate_for_timeout(process))
                cleanup_deadline = time.monotonic() + _TIMEOUT_CLEANUP_GRACE_SECONDS
                cleanup_errors.extend(
                    _timeout_cleanup_details(
                        process,
                        stdout=stdout_buffer,
                        stderr=stderr_buffer,
                        deadline=cleanup_deadline,
                    )
                )
                stdout = bytes(stdout_buffer)
                stderr = bytes(stderr_buffer)
                duration = round(time.monotonic() - started, 3)
                error = f"timed out after {timeout_seconds:g} seconds"
                if cleanup_errors:
                    error += "; cleanup: " + "; ".join(cleanup_errors)
                return CheckResult(
                    name=check.name,
                    command=check.command,
                    status="timed_out",
                    exit_code=None,
                    duration_seconds=duration,
                    stdout=_decode_output(stdout),
                    stderr=_decode_output(stderr),
                    error=error,
                )
            close_errors = _close_process_pipes(process)
            if close_errors:
                duration = round(time.monotonic() - started, 3)
                return CheckResult(
                    name=check.name,
                    command=check.command,
                    status="error",
                    exit_code=process.returncode,
                    duration_seconds=duration,
                    stdout=_decode_output(stdout),
                    stderr=_decode_output(stderr),
                    error="; ".join(close_errors),
                )
        else:
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as first_timeout:
                stdout = first_timeout.output or b""
                stderr = first_timeout.stderr or b""
                cleanup_errors = list(_terminate_for_timeout(process))
                cleanup_deadline = time.monotonic() + _TIMEOUT_CLEANUP_GRACE_SECONDS
                try:
                    stdout, stderr = process.communicate(
                        timeout=_remaining_seconds(cleanup_deadline)
                    )
                except subprocess.TimeoutExpired as drain_timeout:
                    stdout = (
                        drain_timeout.output
                        if drain_timeout.output is not None
                        else first_timeout.output
                    )
                    stderr = (
                        drain_timeout.stderr
                        if drain_timeout.stderr is not None
                        else first_timeout.stderr
                    )
                    cleanup_errors.extend(_close_process_pipes(process))
                    if not _bounded_process_wait(
                        process,
                        timeout_seconds=_remaining_seconds(cleanup_deadline),
                    ):
                        cleanup_errors.append(
                            "direct process did not exit within cleanup grace"
                        )
                duration = round(time.monotonic() - started, 3)
                error = f"timed out after {timeout_seconds:g} seconds"
                if cleanup_errors:
                    error += "; cleanup: " + "; ".join(cleanup_errors)
                return CheckResult(
                    name=check.name,
                    command=check.command,
                    status="timed_out",
                    exit_code=None,
                    duration_seconds=duration,
                    stdout=_decode_output(stdout),
                    stderr=_decode_output(stderr),
                    error=error,
                )
    except (OSError, ValueError) as exc:
        cleanup_errors = (
            _cleanup_after_runner_error(process) if process is not None else ()
        )
        duration = round(time.monotonic() - started, 3)
        error = f"could not launch check: {type(exc).__name__}: {exc}"
        if cleanup_errors:
            error += "; cleanup: " + "; ".join(cleanup_errors)
        return CheckResult(
            name=check.name,
            command=check.command,
            status="error",
            exit_code=None,
            duration_seconds=duration,
            stdout=_decode_output(
                bytes(stdout_buffer) if stdout_buffer is not None else stdout
            ),
            stderr=_decode_output(
                bytes(stderr_buffer) if stderr_buffer is not None else stderr
            ),
            error=error,
        )
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        cleanup_errors = (
            _cleanup_after_runner_error(process) if process is not None else ()
        )
        duration = round(time.monotonic() - started, 3)
        error = f"unexpected runner error: {type(exc).__name__}: {exc}"
        if cleanup_errors:
            error += "; cleanup: " + "; ".join(cleanup_errors)
        return CheckResult(
            name=check.name,
            command=check.command,
            status="error",
            exit_code=None,
            duration_seconds=duration,
            stdout=_decode_output(
                bytes(stdout_buffer) if stdout_buffer is not None else stdout
            ),
            stderr=_decode_output(
                bytes(stderr_buffer) if stderr_buffer is not None else stderr
            ),
            error=error,
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
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
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


def current_commit_sha(repo_root: Path) -> str | None:
    """Read and validate the exact checkout SHA without shell interpolation."""

    try:
        completed = subprocess.run(
            ("git", "rev-parse", "--verify", "HEAD"),
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if _COMMIT_SHA.fullmatch(value) else None


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
    commit_sha: str | None = None,
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
        "commit_sha": commit_sha,
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
    if not math.isfinite(parsed) or parsed <= 0:
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
            "frontend-format",
            "frontend-i18n",
            "message-contract",
            "backend-typecheck",
            "backend-lint",
            "verify-harness",
            "ci-check-catalog",
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
        commit_sha=current_commit_sha(repo_root),
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
