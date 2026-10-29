"""Regression coverage for private VAPID key-file creation."""

import json
import os
import stat
from pathlib import Path

import pytest

from scripts import live_stand


def test_vapid_key_file_is_private_from_its_first_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / live_stand.VAPID_FILE
    original_open = os.open
    opened: list[tuple[int, int, int, int]] = []

    def observe_open(file, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is None:
            descriptor = original_open(file, flags, mode)
        else:
            descriptor = original_open(file, flags, mode, dir_fd=dir_fd)
        if os.fspath(file) == os.fspath(path):
            info = os.fstat(descriptor)
            opened.append((flags, mode, stat.S_IMODE(info.st_mode), info.st_size))
        return descriptor

    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(os, "open", observe_open)
    previous_umask = os.umask(0) if os.name == "posix" else None
    try:
        keys = live_stand.load_or_create_vapid(tmp_path)
    finally:
        if previous_umask is not None:
            os.umask(previous_umask)

    assert len(opened) == 1
    flags, requested_mode, observed_mode, size_before_write = opened[0]
    required_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    assert flags & required_flags == required_flags
    assert requested_mode == 0o600
    assert size_before_write == 0
    if os.name == "posix":
        assert observed_mode == 0o600
    if json.loads(path.read_text(encoding="utf-8")) != keys:
        pytest.fail("the created key file does not hold the generated key pair")


def test_vapid_creation_collision_keeps_the_winner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / live_stand.VAPID_FILE
    winner = live_stand.generate_vapid_keys()
    losing_keys = live_stand.generate_vapid_keys()

    def create_competing_file() -> dict[str, str]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(winner), encoding="utf-8")
        return losing_keys

    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "generate_vapid_keys", create_competing_file)

    returned = live_stand.load_or_create_vapid(tmp_path)

    if returned != winner or json.loads(path.read_text(encoding="utf-8")) != winner:
        pytest.fail("a concurrent creator's key pair was not preserved")


def test_vapid_creation_closes_file_when_serialization_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / live_stand.VAPID_FILE
    original_open = os.open
    original_path_open = Path.open
    descriptors: list[int] = []
    streams = []

    def observe_open(file, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is None:
            descriptor = original_open(file, flags, mode)
        else:
            descriptor = original_open(file, flags, mode, dir_fd=dir_fd)
        if os.fspath(file) == os.fspath(path):
            descriptors.append(descriptor)
        return descriptor

    def observe_path_open(file: Path, *args, **kwargs):
        stream = original_path_open(file, *args, **kwargs)
        if file == path:
            streams.append(stream)
        return stream

    def fail_serialization(*_args, **_kwargs):
        raise RuntimeError("synthetic serialization failure")

    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(os, "open", observe_open)
    monkeypatch.setattr(Path, "open", observe_path_open)
    monkeypatch.setattr(live_stand.json, "dumps", fail_serialization)

    with pytest.raises(RuntimeError, match="synthetic serialization failure"):
        live_stand.load_or_create_vapid(tmp_path)

    if streams:
        assert len(streams) == 1 and streams[0].closed
    else:
        assert len(descriptors) == 1
        with pytest.raises(OSError):
            os.fstat(descriptors[0])


def test_in_place_vapid_preserves_platform_file_protection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / live_stand.VAPID_FILE
    protected: list[Path] = []

    def prepare_directory(directory: Path, *, protect_new_windows: bool) -> None:
        assert protect_new_windows
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    monkeypatch.setattr(
        live_stand, "_ensure_private_state_directory", prepare_directory
    )
    monkeypatch.setattr(
        live_stand, "_restrict_in_place_windows_state_file", protected.append
    )

    live_stand.load_or_create_vapid(tmp_path)

    assert protected == ([path] if os.name == "nt" else [])
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
