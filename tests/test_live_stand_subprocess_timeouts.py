"""The owned live stand bounds every subprocess and lifecycle lock wait (AUD-309)."""

from __future__ import annotations

import ast
import ctypes
import errno
import importlib
import json
import multiprocessing
import os
import subprocess
import sys
import time
from multiprocessing.connection import Connection
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import fast_preflight, live_stand

ROOT = Path(__file__).resolve().parents[1]
LIVE_STAND = ROOT / "scripts" / "live_stand.py"
_TIMEOUT_CAPABLE_CALLS = frozenset({"run", "check_call", "check_output", "call"})


def _unbounded_subprocess_lines() -> list[int]:
    tree = ast.parse(LIVE_STAND.read_text(encoding="utf-8"), filename=str(LIVE_STAND))
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        function = node.func
        if not (
            isinstance(function.value, ast.Name)
            and function.value.id == "subprocess"
            and function.attr in _TIMEOUT_CAPABLE_CALLS | {"Popen"}
        ):
            continue
        if not any(keyword.arg == "timeout" for keyword in node.keywords):
            lines.append(node.lineno)
    return sorted(lines)


def test_every_live_stand_subprocess_call_declares_a_timeout() -> None:
    assert _unbounded_subprocess_lines() == []


def test_generic_live_stand_command_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expire(*_args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == live_stand.LIVE_COMMAND_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

    monkeypatch.setattr(live_stand.subprocess, "run", expire)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._run(["docker", "compose", "up"], cwd=ROOT)


def test_git_probe_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expire(*_args: object, **kwargs: object) -> None:
        assert kwargs["timeout"] == live_stand.LIVE_PROBE_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(live_stand.subprocess, "run", expire)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._git("rev-parse", "HEAD")


def test_playwright_timeout_becomes_a_stand_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def timeout_result(
        check: fast_preflight.CheckSpec, **kwargs: object
    ) -> fast_preflight.CheckResult:
        assert check.name == "live-playwright"
        assert check.command == ("playwright",)
        assert kwargs == {
            "repo_root": tmp_path,
            "timeout_seconds": live_stand.LIVE_E2E_TIMEOUT_SECONDS,
            "include_output": True,
            "env": {},
        }
        return fast_preflight.CheckResult(
            name=check.name,
            command=check.command,
            status="timed_out",
            exit_code=None,
            duration_seconds=1.0,
            stdout="",
            stderr="",
            error="timed out after 1 seconds",
        )

    monkeypatch.setattr(
        live_stand, "_live_e2e_command", lambda **_kwargs: ("playwright",)
    )
    monkeypatch.setattr(live_stand.fast_preflight, "run_check", timeout_result)

    with pytest.raises(live_stand.StandError, match="timed out"):
        live_stand._run_live_playwright(
            cwd=tmp_path,
            environment={},
            mode="full",
            specs=(),
        )


_AUD309_DESCENDANT_CHILD = r"""import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.GetFileType.argtypes = [wintypes.HANDLE]
kernel32.GetFileType.restype = wintypes.DWORD

def creation_time(handle):
    creation, exit_time, kernel_time, user_time = (
        FILETIME(), FILETIME(), FILETIME(), FILETIME()
    )
    if not kernel32.GetProcessTimes(
        wintypes.HANDLE(int(handle)), ctypes.byref(creation), ctypes.byref(exit_time),
        ctypes.byref(kernel_time), ctypes.byref(user_time)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return (creation.dwHighDateTime << 32) | creation.dwLowDateTime

def stream_types():
    stdout = kernel32.GetStdHandle(0xFFFFFFF5)
    stderr = kernel32.GetStdHandle(0xFFFFFFF4)
    return kernel32.GetFileType(stdout), kernel32.GetFileType(stderr)

def write_record(path, record):
    Path(path).write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

role, directory = sys.argv[1], Path(sys.argv[2])
nonce = os.environ["AUD309_NONCE"]
pid = os.getpid()
created = creation_time(kernel32.GetCurrentProcess())
stdout_type, stderr_type = stream_types()

if role == "parent":
    write_record(directory / "parent.json", {
        "pid": pid, "creation": created,
        "nonce": nonce, "stdout_type": stdout_type, "stderr_type": stderr_type,
        "executable": str(Path(sys.executable).resolve()),
    })
    child = subprocess.Popen([
        sys._base_executable, __file__, "grandchild", str(directory),
        str(pid), str(created), "4.5",
    ])
    child_created = creation_time(child._handle)
    write_record(directory / "grandchild-link.json", {
        "pid": child.pid, "creation": child_created,
        "launched_by_pid": pid, "launched_by_creation": created,
    })
    print("owned parent stdout", flush=True)
    print("owned parent stderr", file=sys.stderr, flush=True)
    time.sleep(7.5)
elif role == "grandchild":
    launcher_pid, launcher_created = int(sys.argv[3]), int(sys.argv[4])
    release_after = float(sys.argv[5])
    write_record(directory / "grandchild.json", {
        "pid": pid, "creation": created,
        "nonce": nonce, "stdout_type": stdout_type, "stderr_type": stderr_type,
        "executable": str(Path(sys.executable).resolve()),
        "launched_by_pid": launcher_pid,
        "launched_by_creation": launcher_created,
    })
    print("owned grandchild stdout", flush=True)
    print("owned grandchild stderr", file=sys.stderr, flush=True)
    time.sleep(release_after)
    write_record(directory / "grandchild-done.json", {"pid": pid, "creation": created})
else:
    raise SystemExit("unexpected role")
"""


class _WindowsFileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


def _windows_process_creation_time(handle: int) -> int:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_WindowsFileTime),
        ctypes.POINTER(_WindowsFileTime),
        ctypes.POINTER(_WindowsFileTime),
        ctypes.POINTER(_WindowsFileTime),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    creation, exit_time, kernel_time, user_time = (
        _WindowsFileTime(),
        _WindowsFileTime(),
        _WindowsFileTime(),
        _WindowsFileTime(),
    )
    if not kernel32.GetProcessTimes(
        wintypes.HANDLE(int(handle)),
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return (creation.high << 32) | creation.low


def _windows_open_owned_process(pid: int, creation_time: int) -> int:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x00100000 | 0x00001000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        actual_creation = _windows_process_creation_time(int(handle))
        if actual_creation != creation_time:
            raise AssertionError("owned descendant PID was reused")
    except Exception:
        kernel32.CloseHandle(handle)
        raise
    return int(handle)


@pytest.mark.skipif(os.name != "nt", reason="Windows inherited anonymous-pipe behavior")
def test_playwright_timeout_returns_before_descendant_releases_captured_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A finite grandchild cannot extend the timeout through inherited pipes."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    timeout = 2.0
    monkeypatch.setattr(live_stand, "LIVE_E2E_TIMEOUT_SECONDS", timeout)
    child_script = tmp_path / "aud309_descendant_child.py"
    child_script.write_text(_AUD309_DESCENDANT_CHILD, encoding="utf-8")
    base_executable = str(Path(sys._base_executable).resolve())
    assert Path(base_executable).is_file()
    command = (base_executable, str(child_script), "parent", str(tmp_path))
    monkeypatch.setattr(live_stand, "_live_e2e_command", lambda **_kwargs: command)
    environment = os.environ.copy()
    nonce = uuid4().hex
    environment["AUD309_NONCE"] = nonce

    started_processes: list[subprocess.Popen[bytes]] = []
    real_start_process = fast_preflight._start_process

    def recording_start_process(
        check: fast_preflight.CheckSpec,
        *,
        repo_root: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        assert check.name == "live-playwright"
        assert check.command == command
        assert repo_root == tmp_path
        assert env == environment
        child = real_start_process(check, repo_root=repo_root, env=env)
        started_processes.append(child)
        return child

    monkeypatch.setattr(fast_preflight, "_start_process", recording_start_process)
    grandchild_handle: int | None = None
    try:
        started = time.perf_counter()
        with pytest.raises(
            live_stand.StandError, match="live Playwright command timed out"
        ):
            live_stand._run_live_playwright(
                cwd=tmp_path,
                environment=environment,
                mode="full",
                specs=(),
            )
        elapsed = time.perf_counter() - started

        assert timeout - 0.5 < elapsed
        assert elapsed < timeout + fast_preflight._TIMEOUT_CLEANUP_GRACE_SECONDS + 1.0
        assert len(started_processes) == 1
        direct_child = started_processes[0]
        parent = json.loads((tmp_path / "parent.json").read_text(encoding="utf-8"))
        link = json.loads(
            (tmp_path / "grandchild-link.json").read_text(encoding="utf-8")
        )
        grandchild = json.loads(
            (tmp_path / "grandchild.json").read_text(encoding="utf-8")
        )

        assert direct_child.pid == parent["pid"]
        assert (
            _windows_process_creation_time(int(direct_child._handle))
            == parent["creation"]
        )
        assert parent["nonce"] == nonce
        assert Path(parent["executable"]).resolve() == Path(base_executable)
        assert parent["stdout_type"] == parent["stderr_type"] == 3
        assert link["launched_by_pid"] == parent["pid"]
        assert link["launched_by_creation"] == parent["creation"]
        assert link["pid"] == grandchild["pid"]
        assert link["creation"] == grandchild["creation"]
        assert grandchild["launched_by_pid"] == parent["pid"]
        assert grandchild["launched_by_creation"] == parent["creation"]
        assert grandchild["nonce"] == nonce
        assert Path(grandchild["executable"]).resolve() == Path(base_executable)
        assert grandchild["stdout_type"] == grandchild["stderr_type"] == 3

        grandchild_handle = _windows_open_owned_process(
            grandchild["pid"], grandchild["creation"]
        )
        assert not (tmp_path / "grandchild-done.json").exists()
        assert kernel32.WaitForSingleObject(grandchild_handle, 0) == 0x00000102
        assert kernel32.WaitForSingleObject(int(direct_child._handle), 0) == 0
    finally:
        if started_processes:
            direct_child = started_processes[0]
            if kernel32.WaitForSingleObject(int(direct_child._handle), 0) == 0x00000102:
                try:
                    direct_child.kill()
                except OSError:
                    if kernel32.WaitForSingleObject(int(direct_child._handle), 0) != 0:
                        raise
                direct_child.wait(timeout=1)
        if grandchild_handle is not None:
            try:
                assert kernel32.WaitForSingleObject(grandchild_handle, 6000) == 0
                done = json.loads(
                    (tmp_path / "grandchild-done.json").read_text(encoding="utf-8")
                )
                assert done["pid"] == grandchild["pid"]
                assert done["creation"] == grandchild["creation"]
            finally:
                kernel32.CloseHandle(grandchild_handle)


def _lock_test_worktree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    worktree = tmp_path / "ue-live"
    worktree.mkdir()
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)


def _native_lock_contender(worktree: Path, in_place: bool, result: Connection) -> None:
    live_stand.WORKTREE = worktree
    live_stand.IN_PLACE_MODE = in_place
    live_stand.LIVE_LIFECYCLE_LOCK_TIMEOUT_SECONDS = 0.15
    try:
        with live_stand.stand_lifecycle_lock():
            result.send("acquired")
    except live_stand.StandError as error:
        result.send(str(error))
    finally:
        result.close()


@pytest.mark.parametrize("in_place", [False, True], ids=["worktree", "in-place"])
def test_native_lifecycle_lock_contends_and_recovers_after_release(
    tmp_path: Path, in_place: bool
) -> None:
    """The real OS lock serializes separate processes in either owned mode."""
    worktree = tmp_path / "temporary-owned-worktree"
    worktree.mkdir()
    assert worktree.name != live_stand.WORKTREE_NAME
    lock_name = worktree.name if in_place else live_stand.WORKTREE_NAME
    lock_path = tmp_path / f".{lock_name}.lifecycle.lock"
    lock_path.write_bytes(bytes(1))

    def contend() -> str:
        context = multiprocessing.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        child = context.Process(
            target=_native_lock_contender, args=(worktree, in_place, writer)
        )
        child.start()
        writer.close()
        try:
            assert reader.poll(20), "native lock contender did not report within 20 s"
            outcome = reader.recv()
            child.join(timeout=5)
            assert child.exitcode == 0
            assert isinstance(outcome, str)
            return outcome
        finally:
            reader.close()
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
                if child.is_alive():
                    child.kill()
                    child.join(timeout=5)

    with lock_path.open("r+b") as owner:
        if os.name == "nt":
            native_lock = importlib.import_module("msvcrt")
            native_lock.locking(owner.fileno(), native_lock.LK_NBLCK, 1)
        else:
            native_lock = importlib.import_module("fcntl")
            native_lock.flock(owner.fileno(), native_lock.LOCK_EX | native_lock.LOCK_NB)
        try:
            blocked = contend()
        finally:
            if os.name == "nt":
                owner.seek(0)
                native_lock.locking(owner.fileno(), native_lock.LK_UNLCK, 1)
            else:
                native_lock.flock(owner.fileno(), native_lock.LOCK_UN)

    assert blocked == "timed out waiting for the live stand lifecycle lock"
    assert contend() == "acquired"
    assert lock_path.read_bytes() == bytes(1)
    assert list(tmp_path.glob(".*.lifecycle.lock")) == [lock_path]


@pytest.mark.skipif(os.name != "nt", reason="native Windows msvcrt lock path")
def test_windows_lifecycle_lock_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    msvcrt = importlib.import_module("msvcrt")
    _lock_test_worktree(monkeypatch, tmp_path)
    clock = [1_000.0]
    attempts = [0]

    def locked(_fileno: int, _mode: int, _nbytes: int) -> None:
        attempts[0] += 1
        if attempts[0] > 50:
            raise AssertionError("the lifecycle lock wait was not bounded")
        raise OSError(errno.EACCES, "locked by another operation")

    def sleep_past_any_deadline(seconds: float) -> None:
        assert seconds > 0
        clock[0] += 10_000_000.0

    monkeypatch.setattr(msvcrt, "locking", locked)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep_past_any_deadline)

    with (
        pytest.raises(live_stand.StandError, match="lifecycle lock"),
        live_stand.stand_lifecycle_lock(),
    ):
        pass
    assert attempts[0] <= 3


@pytest.mark.skipif(os.name == "nt", reason="POSIX fcntl lock path")
def test_posix_lifecycle_lock_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fcntl = importlib.import_module("fcntl")
    _lock_test_worktree(monkeypatch, tmp_path)
    clock = [1_000.0]
    attempts = [0]

    def locked(_fileno: int, flags: int) -> None:
        attempts[0] += 1
        assert flags & fcntl.LOCK_NB
        if attempts[0] > 50:
            raise AssertionError("the lifecycle lock wait was not bounded")
        raise BlockingIOError(errno.EAGAIN, "locked by another operation")

    def sleep_past_any_deadline(seconds: float) -> None:
        assert seconds > 0
        clock[0] += 10_000_000.0

    monkeypatch.setattr(fcntl, "flock", locked)
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep_past_any_deadline)

    with (
        pytest.raises(live_stand.StandError, match="lifecycle lock"),
        live_stand.stand_lifecycle_lock(),
    ):
        pass
    assert attempts[0] <= 3
