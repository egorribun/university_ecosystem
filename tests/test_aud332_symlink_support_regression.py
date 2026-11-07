from __future__ import annotations

import errno
import hashlib
import importlib.util
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "symlink_support.py"
SOURCE_PATH = Path(
    os.environ.get("AUD332_SOURCE_PATH", str(MAIN_SOURCE_PATH))
).resolve()
_PROBE_NAMES = (
    "_directory_symlinks_supported",
    "_file_symlinks_supported",
)


class _SyntheticWindowsError(OSError):
    def __init__(self, error_number: int, winerror: int) -> None:
        super().__init__(error_number, "synthetic Windows symlink error")
        self._native_winerror = winerror

    @property
    def winerror(self) -> int:
        return self._native_winerror


def _load_current_source() -> tuple[ModuleType, str]:
    source_bytes = SOURCE_PATH.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    name = "_aud332_symlink_support_source_bound"
    spec = importlib.util.spec_from_file_location(name, SOURCE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot create source-bound module spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() != source_hash:
        raise AssertionError("source changed during module execution")
    return module, source_hash


@pytest.fixture
def source_probe_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> Iterator[ModuleType]:
    scratch_root = Path(os.environ.get("AUD332_TEST_SCRATCH_ROOT", str(tmp_path)))
    scratch = (
        scratch_root / hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:10]
    )
    scratch.mkdir()
    original_tempdir = tempfile.tempdir
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    main_hash = hashlib.sha256(MAIN_SOURCE_PATH.read_bytes()).hexdigest()
    source_hash = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    try:
        privilege_error = _SyntheticWindowsError(errno.EACCES, 1314)

        def refuse_symlink(
            self: Path, target: object, target_is_directory: bool = False
        ) -> None:
            raise privilege_error

        # Patch before loading because module import performs both probes.
        monkeypatch.setattr(Path, "symlink_to", refuse_symlink)
        monkeypatch.setattr(sys, "dont_write_bytecode", True)
        module, loaded_hash = _load_current_source()
        if loaded_hash != source_hash:
            raise AssertionError("source changed before module execution")
        assert module.DIRECTORY_SYMLINKS_SUPPORTED is False
        assert module.FILE_SYMLINKS_SUPPORTED is False
        yield module
    finally:
        source_hash_after = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
        main_hash_after = hashlib.sha256(MAIN_SOURCE_PATH.read_bytes()).hexdigest()
        monkeypatch.setattr(tempfile, "tempdir", original_tempdir)
        cleanup_error: OSError | None = None
        try:
            scratch.rmdir()
        except OSError as error:
            cleanup_error = error
        if source_hash_after != source_hash:
            raise AssertionError("tested source changed during the private regression")
        if main_hash_after != main_hash:
            raise AssertionError("main source changed during the private regression")
        if cleanup_error is not None:
            raise AssertionError(
                "private regression scratch was not empty"
            ) from cleanup_error


@pytest.mark.parametrize("probe_name", _PROBE_NAMES)
def test_native_windows_privilege_denial_is_reported_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    source_probe_module: ModuleType,
    probe_name: str,
) -> None:
    error = _SyntheticWindowsError(errno.EACCES, 1314)

    def refuse_symlink(
        self: Path, target: object, target_is_directory: bool = False
    ) -> None:
        raise error

    monkeypatch.setattr(Path, "symlink_to", refuse_symlink)
    assert getattr(source_probe_module, probe_name)() is False
    monkeypatch.setattr(source_probe_module, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(source_probe_module, "sys", SimpleNamespace(platform="linux"))
    for error_name in ("ENOSYS", "ENOTSUP", "EOPNOTSUPP"):
        error_number = getattr(errno, error_name, None)
        if error_number is None:
            continue
        assert source_probe_module._symlink_capability_unavailable(
            OSError(error_number, "synthetic POSIX capability refusal")
        )
    assert source_probe_module._symlink_capability_unavailable(
        OSError(errno.EPERM, "Linux symlink filesystem capability refusal")
    )
    for error_number in (errno.EACCES, errno.EIO):
        assert not source_probe_module._symlink_capability_unavailable(
            OSError(error_number, "synthetic ambiguous POSIX error")
        )
    monkeypatch.setattr(source_probe_module, "sys", SimpleNamespace(platform="darwin"))
    assert not source_probe_module._symlink_capability_unavailable(
        OSError(errno.EPERM, "synthetic non-Linux permission error")
    )
    assert not source_probe_module._symlink_capability_unavailable(
        _SyntheticWindowsError(errno.ENOTSUP, 5)
    )
    monkeypatch.setattr(source_probe_module, "os", SimpleNamespace(name="unknown"))
    assert not source_probe_module._symlink_capability_unavailable(
        OSError(errno.ENOTSUP, "synthetic unknown-platform error")
    )


@pytest.mark.parametrize(
    ("probe_name", "error_number", "winerror"),
    [
        ("_directory_symlinks_supported", errno.EIO, None),
        ("_file_symlinks_supported", errno.EIO, None),
        ("_directory_symlinks_supported", errno.EACCES, 5),
        ("_file_symlinks_supported", errno.ENOTSUP, 5),
    ],
)
def test_unrelated_probe_errors_are_not_downgraded_to_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    source_probe_module: ModuleType,
    probe_name: str,
    error_number: int,
    winerror: int | None,
) -> None:
    error: OSError
    if winerror is None:
        error = OSError(error_number, "synthetic probe I/O failure")
    else:
        error = _SyntheticWindowsError(error_number, winerror)

    def refuse_symlink(
        self: Path, target: object, target_is_directory: bool = False
    ) -> None:
        raise error

    monkeypatch.setattr(Path, "symlink_to", refuse_symlink)

    with pytest.raises(OSError) as raised:
        getattr(source_probe_module, probe_name)()

    assert raised.value is error
