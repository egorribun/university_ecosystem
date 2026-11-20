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


def test_windows_playwright_uses_os_program_files_instead_of_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_stand, "_windows_program_files_root", lambda: "trusted-root"
    )
    source = {"PATH": "allowed-path", "PROGRAMFILES": "caller-controlled"}
    result = live_stand._live_playwright_platform_environment(source, platform="nt")
    assert result == {"PATH": "allowed-path", "PROGRAMFILES": "trusted-root"}
    assert source["PROGRAMFILES"] == "caller-controlled"


def test_posix_playwright_does_not_resolve_windows_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected() -> str:
        pytest.fail("POSIX must not request a Windows known folder")

    monkeypatch.setattr(live_stand, "_windows_program_files_root", unexpected)
    source = {"PATH": "allowed-path", "HOME": "allowed-home"}
    result = live_stand._live_playwright_platform_environment(source, platform="posix")
    assert result == source
    assert result is not source


def test_windows_playwright_keeps_safe_search_if_known_folder_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> str:
        raise live_stand.StandError("known Program Files directory unavailable")

    monkeypatch.setattr(live_stand, "_windows_program_files_root", unavailable)
    source = {
        "PATH": "allowed-path",
        "LOCALAPPDATA": "allowed-user-root",
        "ProgramFiles": "caller-controlled",
        "PROGRAMFILES(X86)": "caller-controlled-x86",
        "HOMEDRIVE": "caller-controlled-drive",
    }
    result = live_stand._live_playwright_platform_environment(source, platform="nt")
    assert result == {"PATH": "allowed-path", "LOCALAPPDATA": "allowed-user-root"}
    assert source["ProgramFiles"] == "caller-controlled"


@pytest.mark.skipif(os.name != "nt", reason="requires Windows known-folder API")
def test_windows_known_folder_matches_native_system_api() -> None:
    buffer = ctypes.create_unicode_buffer(32768)
    status = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0026, None, 0, buffer)
    assert status == 0 and buffer.value
    assert Path(live_stand._windows_program_files_root()) == Path(buffer.value).resolve(
        strict=True
    )


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
@pytest.mark.parametrize("root", ["", r"..\relative", r"\\server\share\Program Files"])
def test_windows_known_folder_rejects_nonlocal_or_nonabsolute(
    monkeypatch: pytest.MonkeyPatch, root: str
) -> None:
    monkeypatch.setattr(live_stand, "_read_windows_program_files", lambda: root)
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_rejects_missing_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        live_stand,
        "_read_windows_program_files",
        lambda: str(tmp_path / "missing"),
    )
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_fails_closed_for_reparse_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        live_stand, "_read_windows_program_files", lambda: str(tmp_path)
    )

    def reject(_path: Path) -> None:
        raise live_stand.StandError("reparse")

    monkeypatch.setattr(live_stand, "_assert_no_reparse_ancestors", reject)
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows known-folder API")
def test_windows_known_folder_api_failure_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedLookup:
        def __call__(self, *_args: object) -> int:
            return -1

    monkeypatch.setattr(
        live_stand.ctypes.windll.shell32, "SHGetKnownFolderPath", FailedLookup()
    )
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._read_windows_program_files()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_lookup_exception_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed() -> str:
        raise OSError("unavailable")

    monkeypatch.setattr(live_stand, "_read_windows_program_files", failed)
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_rejects_non_fixed_drive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        live_stand, "_read_windows_program_files", lambda: str(tmp_path)
    )
    monkeypatch.setattr(live_stand.ctypes.windll.kernel32, "GetDriveTypeW", lambda _: 4)
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_rejects_regular_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("test", encoding="utf-8")
    monkeypatch.setattr(live_stand, "_read_windows_program_files", lambda: str(target))
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path validation")
def test_windows_known_folder_rejects_drive_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        live_stand, "_read_windows_program_files", lambda: tmp_path.anchor
    )
    with pytest.raises(live_stand.StandError, match="Program Files"):
        live_stand._windows_program_files_root()


@pytest.mark.skipif(os.name != "nt", reason="requires Windows known-folder API")
def test_windows_known_folder_api_exception_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailedLookup:
        def __call__(self, *_args: object) -> int:
            raise OSError("private sentinel")

    monkeypatch.setattr(
        live_stand.ctypes.windll.shell32, "SHGetKnownFolderPath", FailedLookup()
    )
    with pytest.raises(
        live_stand.StandError, match="cannot resolve Windows Program Files"
    ):
        live_stand._read_windows_program_files()
