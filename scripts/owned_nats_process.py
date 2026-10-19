"""Private local-child collection; not a remote-exec lifecycle API.

Selector and wait budgets use the caller deadline. Local path validation and
OS process creation are synchronous trusted-local operations, not preemptible
hard-real-time calls. Cleanup confirmation means direct-child reaping only;
process-group signaling does not prove descendant or remote-exec termination.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import BinaryIO

from scripts.owned_nats_outage import Deadline, DeadlineVerdict


class ProcessOutcome(StrEnum):
    NOT_READY = "not_ready"
    EXITED = "exited"
    INVALID = "invalid"
    TIMED_OUT = "timed_out"
    OUTPUT_LIMIT = "output_limit"
    START_FAILED = "start_failed"
    CONTAINMENT_UNAVAILABLE = "containment_unavailable"
    CLEANUP_UNCERTAIN = "cleanup_uncertain"


class LocalCleanup(StrEnum):
    NOT_STARTED = "not_started"
    CONFIRMED = "confirmed"
    UNPROVEN = "unproven"


@dataclass(frozen=True, slots=True)
class PrivateProcessRequest:
    argv: tuple[str, ...] = field(repr=False)
    cwd: str = field(repr=False)
    env: Mapping[str, str] = field(repr=False)
    stdin: bytes = field(default=b"", repr=False)
    stdout_limit: int = 65_536
    stderr_limit: int = 16_384
    input_limit: int = 65_536


@dataclass(frozen=True, slots=True)
class PrivateProcessResult:
    outcome: ProcessOutcome
    returncode: int | None
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)
    local_cleanup: LocalCleanup


_IO_CHUNK = 16_384
_MAX_BYTES = 1_048_576
_OPERATION_CAP = 120.0
_CLEANUP_RESERVE = 0.25
_POLL_CAP = 0.05


def _process_tree_containment_available() -> bool:
    """Admit POSIX session signaling, not proven process-tree containment."""
    return (
        os.name == "posix"
        and callable(getattr(os, "killpg", None))
        and callable(getattr(os, "set_blocking", None))
    )


def _result(
    outcome: ProcessOutcome,
    returncode: int | None = None,
    stdout: bytes = b"",
    stderr: bytes = b"",
    cleanup: LocalCleanup = LocalCleanup.NOT_STARTED,
) -> PrivateProcessResult:
    return PrivateProcessResult(outcome, returncode, stdout, stderr, cleanup)


def _validate_request(request: PrivateProcessRequest) -> dict[str, str] | None:
    if not isinstance(request, PrivateProcessRequest):
        return None
    if (
        type(request.argv) is not tuple
        or not request.argv
        or len(request.argv) > 128
        or any(type(arg) is not str or "\x00" in arg for arg in request.argv)
        or not request.argv[0]
        or sum(map(len, request.argv)) > 65_536
    ):
        return None
    if (
        type(request.cwd) is not str
        or not request.cwd
        or "\x00" in request.cwd
        or len(request.cwd) > 4_096
        or not os.path.isdir(request.cwd)
    ):
        return None
    if not isinstance(request.env, Mapping) or len(request.env) > 128:
        return None
    environment = dict(request.env)
    if len(environment) > 128:
        return None
    size = 0
    for key, value in environment.items():
        if (
            type(key) is not str
            or not key
            or "=" in key
            or "\x00" in key
            or type(value) is not str
            or "\x00" in value
        ):
            return None
        size += len(key) + len(value)
        if size > 65_536:
            return None
    if type(request.stdin) is not bytes:
        return None
    for limit in (request.input_limit, request.stdout_limit, request.stderr_limit):
        if type(limit) is not int or not 0 <= limit <= _MAX_BYTES:
            return None
    return environment if len(request.stdin) <= request.input_limit else None


def _close_stream(stream: BinaryIO | None) -> None:
    if stream is not None:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _cleanup_child(
    child: subprocess.Popen[bytes],
    deadline: Deadline,
    outcome: ProcessOutcome,
    stdout: bytearray,
    stderr: bytearray,
) -> PrivateProcessResult:
    # Never signal a numeric PID/group after this Popen child was reaped.
    if child.returncode is None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                os.kill(child.pid, signal.SIGKILL)
            except OSError:
                pass
        budget = deadline.timeout_for(_OPERATION_CAP)
        if budget.verdict is DeadlineVerdict.VALID and budget.seconds is not None:
            try:
                child.wait(timeout=budget.seconds)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass
    if child.returncode is not None:
        return _result(
            outcome,
            child.returncode,
            bytes(stdout),
            bytes(stderr),
            LocalCleanup.CONFIRMED,
        )
    return _result(
        ProcessOutcome.CLEANUP_UNCERTAIN,
        None,
        bytes(stdout),
        bytes(stderr),
        LocalCleanup.UNPROVEN,
    )


def run_private_process(
    request: PrivateProcessRequest, *, deadline: Deadline
) -> PrivateProcessResult:
    """Collect bounded private bytes and reap only the explicit direct child."""
    if not isinstance(deadline, Deadline):
        return _result(ProcessOutcome.INVALID)
    budget = deadline.timeout_for(_OPERATION_CAP)
    if budget.verdict is DeadlineVerdict.INVALID:
        return _result(ProcessOutcome.INVALID)
    if budget.verdict is DeadlineVerdict.EXPIRED:
        return _result(ProcessOutcome.TIMED_OUT)
    try:
        environment = _validate_request(request)
    except (OSError, TypeError, ValueError, RuntimeError):
        return _result(ProcessOutcome.INVALID)
    if environment is None:
        return _result(ProcessOutcome.INVALID)
    if not _process_tree_containment_available():
        return _result(ProcessOutcome.CONTAINMENT_UNAVAILABLE)

    operation = deadline.child(_OPERATION_CAP)
    budget = operation.timeout_for(_OPERATION_CAP)
    if budget.verdict is DeadlineVerdict.INVALID:
        return _result(ProcessOutcome.INVALID)
    if (
        budget.verdict is not DeadlineVerdict.VALID
        or budget.seconds is None
        or budget.seconds <= _CLEANUP_RESERVE
        or operation.expires_at is None
    ):
        return _result(ProcessOutcome.TIMED_OUT)
    # Subtract from the absolute expiry, not a later clock sample.
    work = replace(operation, expires_at=operation.expires_at - _CLEANUP_RESERVE)
    if work.timeout_for(_POLL_CAP).verdict is not DeadlineVerdict.VALID:
        return _result(ProcessOutcome.TIMED_OUT)
    stdout = bytearray()
    stderr = bytearray()
    selector: selectors.BaseSelector | None = None
    reason = ProcessOutcome.CLEANUP_UNCERTAIN
    input_offset = 0
    input_view = memoryview(request.stdin)
    result: PrivateProcessResult
    try:
        # Caller-owned argv is trusted internal input, never a public command API.
        child = subprocess.Popen(  # noqa: S603 -- reviewed internal argv, no shell
            request.argv,
            shell=False,
            cwd=request.cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            bufsize=0,
            start_new_session=True,
        )
    except OSError:
        return _result(ProcessOutcome.START_FAILED)

    try:
        if child.stdin is None or child.stdout is None or child.stderr is None:
            raise OSError("Subprocess pipes unavailable")
        selector = selectors.DefaultSelector()
        for stream in (child.stdin, child.stdout, child.stderr):
            os.set_blocking(stream.fileno(), False)
        if request.stdin:
            selector.register(child.stdin, selectors.EVENT_WRITE, "stdin")
        else:
            _close_stream(child.stdin)
        selector.register(child.stdout, selectors.EVENT_READ, "stdout")
        selector.register(child.stderr, selectors.EVENT_READ, "stderr")

        while selector.get_map():
            budget = work.timeout_for(_POLL_CAP)
            if budget.verdict is not DeadlineVerdict.VALID or budget.seconds is None:
                reason = (
                    ProcessOutcome.TIMED_OUT
                    if budget.verdict is DeadlineVerdict.EXPIRED
                    else ProcessOutcome.CLEANUP_UNCERTAIN
                )
                break
            for key, _ in selector.select(budget.seconds):
                if key.data == "stdin":
                    try:
                        written = os.write(
                            key.fd,
                            input_view[input_offset : input_offset + _IO_CHUNK],
                        )
                    except (BlockingIOError, InterruptedError):
                        continue
                    except BrokenPipeError:
                        selector.unregister(child.stdin)
                        _close_stream(child.stdin)
                        continue
                    input_offset += written
                    if input_offset >= len(input_view):
                        selector.unregister(child.stdin)
                        _close_stream(child.stdin)
                    continue

                is_stdout = key.data == "stdout"
                target = stdout if is_stdout else stderr
                limit = request.stdout_limit if is_stdout else request.stderr_limit
                remaining = limit - len(target)
                try:
                    chunk = os.read(key.fd, min(_IO_CHUNK, remaining + 1))
                except (BlockingIOError, InterruptedError):
                    continue
                if not chunk:
                    stream = child.stdout if is_stdout else child.stderr
                    selector.unregister(stream)
                    _close_stream(stream)
                    continue
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    reason = ProcessOutcome.OUTPUT_LIMIT
                    break
            if reason is ProcessOutcome.OUTPUT_LIMIT:
                break
        else:
            budget = work.timeout_for(_OPERATION_CAP)
            if budget.verdict is DeadlineVerdict.VALID and budget.seconds is not None:
                try:
                    child.wait(timeout=budget.seconds)
                except subprocess.TimeoutExpired:
                    reason = ProcessOutcome.TIMED_OUT
                else:
                    reason = ProcessOutcome.EXITED
            elif budget.verdict is DeadlineVerdict.EXPIRED:
                reason = ProcessOutcome.TIMED_OUT
    except Exception:
        # Raw exceptions and child output remain private.
        reason = ProcessOutcome.CLEANUP_UNCERTAIN
    finally:
        try:
            if selector is not None:
                try:
                    selector.close()
                except (OSError, ValueError):
                    pass
            _close_stream(child.stdin)
            _close_stream(child.stdout)
            _close_stream(child.stderr)
        finally:
            # Also runs before KeyboardInterrupt/SystemExit propagate.
            result = _cleanup_child(child, operation, reason, stdout, stderr)

    return result
