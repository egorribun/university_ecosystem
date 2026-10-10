"""Contracts for byte-safe Windows ACL subprocess handling."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_stand.py"
_SPEC = importlib.util.spec_from_file_location(
    "live_stand_acl_bytes_candidate", _SCRIPT
)
assert _SPEC is not None and _SPEC.loader is not None
live_stand = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = live_stand
_SPEC.loader.exec_module(live_stand)

_ICACLS = r"C:\Windows\System32\icacls.exe"
_USER_SID = "S-1-5-21-111111111-222222222-333333333-1001"


def _configure_icacls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        live_stand.shutil,
        "which",
        lambda name: _ICACLS if name == "icacls.exe" else None,
    )
    monkeypatch.setattr(live_stand, "_windows_user_sid", lambda: _USER_SID)


def _recording_runner(calls: list[tuple[list[str], dict[str, object]]]):
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((list(command), dict(kwargs)))
        assert kwargs.get("check") is True
        assert kwargs.get("capture_output") is True
        assert kwargs.get("timeout") == 20
        raw_output = b"icacls OEM byte: \x81"
        if kwargs.get("text") is True:
            raw_output.decode("cp1252")
        assert kwargs.get("text") is not True
        return subprocess.CompletedProcess(
            command, 0, stdout=raw_output, stderr=raw_output
        )

    return run


def test_new_state_directory_ignores_oem_acl_output_as_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_icacls(monkeypatch)
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(live_stand.subprocess, "run", _recording_runner(calls))
    state_root = tmp_path / "run-state"

    live_stand._restrict_new_windows_state_directory(state_root)

    assert [command for command, _kwargs in calls] == [
        [_ICACLS, str(state_root), "/reset"],
        [_ICACLS, str(state_root), "/setowner", f"*{_USER_SID}"],
        [
            _ICACLS,
            str(state_root),
            "/inheritance:r",
            "/grant:r",
            f"*{_USER_SID}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
        ],
    ]
    assert all("text" not in kwargs for _command, kwargs in calls)


def test_in_place_state_file_ignores_oem_acl_output_as_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_icacls(monkeypatch)
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(live_stand.subprocess, "run", _recording_runner(calls))
    state_root = tmp_path / "owned-state"
    state_root.mkdir()
    state_file = state_root / "owner.json"
    state_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(live_stand, "os", SimpleNamespace(name="nt", path=os.path))
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)

    live_stand._restrict_in_place_windows_state_file(state_file)

    assert [command for command, _kwargs in calls] == [
        [_ICACLS, str(state_file), "/reset"],
        [_ICACLS, str(state_file), "/setowner", f"*{_USER_SID}"],
    ]
    assert all("text" not in kwargs for _command, kwargs in calls)


@pytest.mark.parametrize("target", ["directory", "file"])
@pytest.mark.parametrize("failure", ["called_process_error", "timeout_expired"])
def test_acl_subprocess_errors_remain_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: str,
    failure: str,
) -> None:
    _configure_icacls(monkeypatch)
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(list(command))
        assert kwargs.get("check") is True
        assert kwargs.get("capture_output") is True
        assert kwargs.get("timeout") == 20
        if len(calls) == 2:
            if failure == "called_process_error":
                raise subprocess.CalledProcessError(
                    1, command, output=b"access denied", stderr=b""
                )
            raise subprocess.TimeoutExpired(
                command, 20, output=b"partial output", stderr=b""
            )
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(live_stand.subprocess, "run", run)
    if target == "directory":
        state_directory = tmp_path / "run-state"

        def action() -> None:
            live_stand._restrict_new_windows_state_directory(state_directory)

    else:
        state_root = tmp_path / "owned-state"
        state_root.mkdir()
        state_file = state_root / "owner.json"
        state_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(live_stand, "os", SimpleNamespace(name="nt", path=os.path))
        monkeypatch.setattr(live_stand, "WORKTREE", state_root)
        monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)

        def action() -> None:
            live_stand._restrict_in_place_windows_state_file(state_file)

    with pytest.raises(
        live_stand.StandError,
        match="cannot enforce private Windows permissions for live state",
    ) as raised:
        action()

    assert raised.value.__cause__ is None
    assert len(calls) == 2
