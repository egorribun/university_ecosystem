"""Bounded collector contracts; no Docker, network, or stand operations."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace

import pytest

from scripts import owned_nats_process as process
from scripts.owned_nats_outage import Deadline

_MISSING = object()


class _CapturedPopen:
    def __init__(self, child, owner):
        self._child = child
        self._owner = owner

    def communicate(self, *args, **kwargs):
        self._owner.communicate_calls += 1
        raise AssertionError("communicate is forbidden")

    def wait(self, timeout=_MISSING):
        if timeout is _MISSING or timeout is None:
            self._owner.unbounded_wait_calls += 1
            raise AssertionError("wait must have a finite timeout")
        self._owner.wait_timeouts.append(timeout)
        try:
            finite = math.isfinite(timeout) and timeout >= 0
        except (TypeError, OverflowError):
            finite = False
        if not finite:
            self._owner.bad_wait_budget = True
            raise AssertionError("wait timeout must be finite and nonnegative")
        deadline = self._owner.deadline
        if deadline is not None and deadline.expires_at is not None:
            remaining = deadline.expires_at - time.monotonic()
            # This observes Popen.wait only, not every selector/read operation.
            if timeout > max(0.0, remaining) + 0.02:
                self._owner.bad_wait_budget = True
        return self._child.wait(timeout=timeout)

    def __getattr__(self, name):
        return getattr(self._child, name)


class _OwnedChildren:
    def __init__(self):
        self.calls = []
        self.children = []
        self.deadline = None
        self.wait_timeouts = []
        self.communicate_calls = 0
        self.unbounded_wait_calls = 0
        self.bad_wait_budget = False


@pytest.fixture
def owned_children(monkeypatch):
    owner = _OwnedChildren()
    real_popen = subprocess.Popen

    def capture_popen(*args, **kwargs):
        argv = args[0] if args else kwargs.get("args")
        owner.calls.append((argv, dict(kwargs)))
        child = real_popen(*args, **kwargs)
        owner.children.append(child)
        return _CapturedPopen(child, owner)

    monkeypatch.setattr(subprocess, "Popen", capture_popen)
    yield owner

    # This slice spawns no descendants. Reap only this test's captured children.
    for child in owner.children:
        if child.poll() is None:
            try:
                if os.name == "posix":
                    os.kill(child.pid, signal.SIGKILL)
                else:
                    child.kill()
            except ProcessLookupError:
                child.poll()
            try:
                child.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                raise AssertionError("captured child was not reaped") from None
    # These checks are outside the collector's exception handling.
    assert owner.communicate_calls == 0
    assert owner.unbounded_wait_calls == 0
    assert not owner.bad_wait_budget


def _deadline(seconds=3.0):
    return Deadline.after(seconds, clock=time.monotonic)


def _guarded_source(body):
    return (
        "import os, threading, time\n"
        "def _watchdog():\n"
        "    time.sleep(1.5)\n"
        "    os._exit(97)\n"
        "threading.Thread(target=_watchdog, daemon=True).start()\n"
        f"{body}\n"
    )


def _request(tmp_path, body="pass", *, argv_tail=(), **changes):
    source = _guarded_source(body)
    values = {
        "argv": (sys.executable, "-c", source, *argv_tail),
        "cwd": str(tmp_path),
        "env": {},
    }
    values.update(changes)
    return process.PrivateProcessRequest(**values)


def _assert_supported_or_fail_closed(result, owner):
    if process._process_tree_containment_available():
        return True
    assert result.outcome is process.ProcessOutcome.CONTAINMENT_UNAVAILABLE
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert owner.calls == []
    return False


def test_fixed_argv_env_cwd_stdin_and_empty_argument(
    monkeypatch, tmp_path, owned_children
):
    monkeypatch.setenv("NOT_INHERITED", "parent-only")
    deadline = _deadline()
    owned_children.deadline = deadline
    code = (
        "import os,sys; "
        "sys.stdout.write(os.getcwd()+'|'+os.environ['ONLY']+'|'+"
        "os.environ.get('NOT_INHERITED','missing')+'|'+"
        "sys.stdin.buffer.read().decode()+'|'+sys.argv[1])"
    )
    request = _request(
        tmp_path, code, argv_tail=("",), env={"ONLY": "explicit"}, stdin=b"payload"
    )

    result = process.run_private_process(request, deadline=deadline)

    if not _assert_supported_or_fail_closed(result, owned_children):
        return
    assert result.outcome is process.ProcessOutcome.EXITED
    assert result.returncode == 0
    assert result.stdout == f"{tmp_path}|explicit|missing|payload|".encode()
    assert result.local_cleanup is process.LocalCleanup.CONFIRMED
    argv, kwargs = owned_children.calls[0]
    assert tuple(argv) == request.argv
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == request.cwd
    assert kwargs["env"] == request.env
    assert kwargs["stdin"] == subprocess.PIPE
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["stderr"] == subprocess.PIPE
    assert kwargs["start_new_session"] is True


def test_nonzero_exit_is_returned(tmp_path, owned_children):
    deadline = _deadline()
    owned_children.deadline = deadline
    request = _request(tmp_path, "import sys; sys.exit(17)")

    result = process.run_private_process(request, deadline=deadline)

    if not _assert_supported_or_fail_closed(result, owned_children):
        return
    assert result.outcome is process.ProcessOutcome.EXITED
    assert result.returncode == 17
    assert result.local_cleanup is process.LocalCleanup.CONFIRMED


@pytest.mark.parametrize(
    "changes",
    [
        {"argv": ()},
        {"argv": ("",)},
        {"argv": (sys.executable, "\x00")},
        {"argv": [sys.executable, "-c", "pass"]},
        {"argv": (sys.executable, 7)},
        {"cwd": ""},
        {"cwd": "missing-directory"},
        {"env": []},
        {"env": {"": "value"}},
        {"env": {"BAD=KEY": "value"}},
        {"env": {"BAD\x00KEY": "value"}},
        {"env": {"GOOD": object()}},
        {"stdin": "not-bytes"},
        {"stdin": b"1234", "input_limit": 3},
        {"stdout_limit": -1},
        {"stderr_limit": -1},
        {"input_limit": -1},
        {"stdout_limit": True},
    ],
)
def test_invalid_request_is_rejected_before_spawn(tmp_path, owned_children, changes):
    deadline = _deadline()
    owned_children.deadline = deadline
    if changes.get("cwd") == "missing-directory":
        changes = {**changes, "cwd": str(tmp_path / "missing-directory")}
    request = replace(_request(tmp_path), **changes)

    result = process.run_private_process(request, deadline=deadline)

    assert result.outcome is process.ProcessOutcome.INVALID
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert owned_children.calls == []


def test_expired_deadline_does_not_spawn(tmp_path, owned_children):
    class Clock:
        now = 0.0

        def __call__(self):
            return self.now

    clock = Clock()
    deadline = Deadline.after(0.1, clock=clock)
    owned_children.deadline = deadline
    clock.now = 0.11

    result = process.run_private_process(_request(tmp_path), deadline=deadline)

    assert result.outcome is process.ProcessOutcome.TIMED_OUT
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert owned_children.calls == []


def test_invalid_deadline_does_not_spawn(tmp_path, owned_children):
    deadline = Deadline.after(0, clock=time.monotonic)
    owned_children.deadline = deadline

    result = process.run_private_process(_request(tmp_path), deadline=deadline)

    assert result.outcome is process.ProcessOutcome.INVALID
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert owned_children.calls == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (
            "import sys; sys.stdout.buffer.write(b'x'*8192); sys.stdout.flush()",
            "stdout",
        ),
        (
            "import sys; sys.stderr.buffer.write(b'x'*8192); sys.stderr.flush()",
            "stderr",
        ),
    ],
)
def test_output_is_capped(tmp_path, owned_children, body, field):
    deadline = _deadline()
    owned_children.deadline = deadline
    request = _request(tmp_path, body, **{f"{field}_limit": 128})

    result = process.run_private_process(request, deadline=deadline)

    if not _assert_supported_or_fail_closed(result, owned_children):
        return
    assert result.outcome is process.ProcessOutcome.OUTPUT_LIMIT
    assert len(getattr(result, field)) <= 128
    assert result.local_cleanup is process.LocalCleanup.CONFIRMED


def test_spawn_error_text_is_not_returned_or_logged(
    monkeypatch, tmp_path, owned_children, capsys, caplog
):
    monkeypatch.setattr(process, "_process_tree_containment_available", lambda: True)
    deadline = _deadline()
    owned_children.deadline = deadline

    def fail_spawn(*args, **kwargs):
        raise OSError("PRIVATE-SPAWN-ERROR")

    monkeypatch.setattr(subprocess, "Popen", fail_spawn)
    result = process.run_private_process(_request(tmp_path), deadline=deadline)

    assert result.outcome is process.ProcessOutcome.START_FAILED
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert "PRIVATE-SPAWN-ERROR" not in repr(result)
    assert "PRIVATE-SPAWN-ERROR" not in caplog.text
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_private_request_and_result_fields_are_not_in_repr(tmp_path):
    secret = "PRIVATE-SENTINEL"
    request = _request(
        tmp_path,
        argv=(secret,),
        cwd=secret,
        env={secret: secret},
        stdin=secret.encode(),
    )
    result = process.PrivateProcessResult(
        process.ProcessOutcome.EXITED,
        0,
        secret.encode(),
        secret.encode(),
        process.LocalCleanup.CONFIRMED,
    )

    assert secret not in repr(request)
    assert secret not in repr(result)


def test_collected_output_is_private_not_console_output(
    tmp_path, owned_children, capsys, caplog
):
    deadline = _deadline()
    owned_children.deadline = deadline
    request = _request(
        tmp_path,
        "import sys; sys.stdout.write('PRIVATE-OUT'); sys.stderr.write('PRIVATE-ERR')",
    )

    result = process.run_private_process(request, deadline=deadline)

    if not _assert_supported_or_fail_closed(result, owned_children):
        return
    assert result.outcome is process.ProcessOutcome.EXITED
    assert result.stdout == b"PRIVATE-OUT"
    assert result.stderr == b"PRIVATE-ERR"
    assert "PRIVATE-" not in repr(result)
    assert "PRIVATE-OUT" not in caplog.text
    assert "PRIVATE-ERR" not in caplog.text
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_normal_child_timeout_has_finite_waits_and_bounded_cleanup(
    tmp_path, owned_children
):
    deadline = _deadline(0.75)
    owned_children.deadline = deadline
    request = _request(tmp_path, "time.sleep(10)")
    started = time.monotonic()

    result = process.run_private_process(request, deadline=deadline)

    elapsed = time.monotonic() - started
    if not _assert_supported_or_fail_closed(result, owned_children):
        return
    assert result.outcome is process.ProcessOutcome.TIMED_OUT
    assert result.local_cleanup is process.LocalCleanup.CONFIRMED
    assert elapsed < 1.3  # Scheduling tolerance, not an extra collector grace.
    assert owned_children.children[0].poll() is not None


def test_unsupported_containment_fails_closed_without_spawn(
    monkeypatch, tmp_path, owned_children
):
    monkeypatch.setattr(process, "_process_tree_containment_available", lambda: False)
    deadline = _deadline()
    owned_children.deadline = deadline

    result = process.run_private_process(_request(tmp_path), deadline=deadline)

    assert result.outcome is process.ProcessOutcome.CONTAINMENT_UNAVAILABLE
    assert result.local_cleanup is process.LocalCleanup.NOT_STARTED
    assert owned_children.calls == []
