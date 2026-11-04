"""Real subprocess timeout and cleanup controls for the live stand (AUD-309)."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path
from threading import Timer

import pytest

from scripts import live_stand

_CHILD_WAIT_FOR_RELEASE = """
import os
import sys
import time
from pathlib import Path
from threading import Event

Path(sys.argv[1]).write_text(str(os.getpid()), encoding="ascii")
release = Path(sys.argv[2])
deadline = time.monotonic() + 8.0
waiter = Event()
while not release.is_file():
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SystemExit("child release deadline elapsed")
    waiter.wait(timeout=min(0.05, remaining))
"""


def _schedule_release(release: Path, delay: float) -> Timer:
    signal = Timer(delay, release.touch)
    signal.daemon = True
    signal.start()
    return signal


def _cancel_release(signal: Timer) -> None:
    signal.cancel()
    signal.join(timeout=1)
    assert not signal.is_alive()


def _assert_process_exited(pid: int) -> None:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        )
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            assert ctypes.get_last_error() == 87
            return
        try:
            code = ctypes.c_uint32()
            assert kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            assert code.value != 259, "timed-out child is still running"
        finally:
            assert kernel32.CloseHandle(handle)
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_subprocess_timeout_terminates_native_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "child.pid"
    release = tmp_path / "release"
    monkeypatch.setattr(live_stand, "LIVE_COMMAND_TIMEOUT_SECONDS", 1.5)
    fallback = _schedule_release(release, 5.0)
    try:
        started = time.monotonic()
        with pytest.raises(
            live_stand.StandError, match=r"^live stand command timed out$"
        ):
            live_stand._run(
                [
                    sys.executable,
                    "-c",
                    _CHILD_WAIT_FOR_RELEASE,
                    str(marker),
                    str(release),
                ],
                cwd=tmp_path,
            )
        elapsed = time.monotonic() - started
    finally:
        _cancel_release(fallback)
    assert marker.is_file(), "the real child must start before timeout"
    assert not release.exists(), "the timeout must precede the fallback release"
    assert 0.5 <= elapsed < 7
    _assert_process_exited(int(marker.read_text(encoding="ascii")))


def test_subprocess_success_completes_native_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "child.pid"
    release = tmp_path / "release"
    monkeypatch.setattr(live_stand, "LIVE_COMMAND_TIMEOUT_SECONDS", 5)
    signal = _schedule_release(release, 0.5)
    try:
        live_stand._run(
            [sys.executable, "-c", _CHILD_WAIT_FOR_RELEASE, str(marker), str(release)],
            cwd=tmp_path,
        )
    finally:
        _cancel_release(signal)
    assert marker.is_file() and release.is_file()
    _assert_process_exited(int(marker.read_text(encoding="ascii")))
