from __future__ import annotations

import runpy
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality import check_no_pickle as gate

MODULE_PATH = Path(gate.__file__)


@pytest.mark.parametrize(
    "source",
    [
        "import pickle  # nosec",
        "import pickle as serializer",
        "import pickle.core as pickle_core",
        "from pickle import loads  # nosec",
        "import _pickle  # nosec",
        "import _pickle as low_level_pickle",
        "from _pickle import Unpickler",
    ],
)
def test_direct_pickle_imports_are_rejected_despite_nosec(source: str) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert findings[0].path == Path("unsafe.py")
    assert "pickle" in findings[0].message


@pytest.mark.parametrize(
    "source",
    [
        "pickle.loads(payload)",
        "pickle.dumps(value)",
        "_pickle.Unpickler(stream)",
        "_pickle.loads(payload)",
        "factory = pickle.loads",
    ],
)
def test_direct_pickle_api_use_is_rejected(source: str) -> None:
    assert gate.scan_source(source, filename="unsafe.py")


def test_comments_docstrings_relative_imports_and_other_names_are_ignored() -> None:
    source = '''
# import pickle # nosec
"""from _pickle import loads"""
import pickletools
from .pickle import loads
from . import local_name
object.loads(payload)
factory().loads(payload)
value = "pickle.loads is forbidden"
'''
    assert gate.scan_source(source, filename="safe.py") == ()


def test_parse_errors_fail_closed_with_source_location() -> None:
    with pytest.raises(gate.ScanError, match=r"cannot parse Python source.*broken.py"):
        gate.scan_source("def broken(:\n", filename="broken.py")


def test_scan_paths_counts_nested_python_files_and_deduplicates(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "app"
    nested = source_dir / "nested"
    nested.mkdir(parents=True)
    safe = source_dir / "safe.py"
    unsafe = nested / "unsafe.PY"
    safe.write_text("value = 1\n", encoding="utf-8")
    unsafe.write_text("import _pickle  # nosec\n", encoding="utf-8")
    (source_dir / "notes.txt").write_text("import pickle\n", encoding="utf-8")

    count, findings = gate.scan_paths([source_dir, safe])

    assert count == 2
    assert len(findings) == 1
    assert findings[0].path == unsafe


def test_empty_or_non_python_directories_fail_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "readme.txt").write_text("import pickle\n", encoding="utf-8")

    with pytest.raises(gate.ScanError, match="no Python source files"):
        gate.scan_paths([empty])
    with pytest.raises(gate.ScanError, match="no Python source files"):
        gate.scan_paths([notes])


def test_empty_nested_directory_is_allowed_when_scan_root_has_python(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "app"
    (source_dir / "empty").mkdir(parents=True)
    (source_dir / "safe.py").write_text("value = 1\n", encoding="utf-8")

    count, findings = gate.scan_paths([source_dir])

    assert count == 1
    assert findings == ()


def test_scan_paths_fails_closed_for_missing_non_python_and_empty_inputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.ScanError, match="source path"):
        gate.scan_paths([tmp_path / "missing"])
    non_python = tmp_path / "notes.txt"
    non_python.write_text("import pickle\n", encoding="utf-8")
    with pytest.raises(gate.ScanError, match="not Python source"):
        gate.scan_paths([non_python])
    with pytest.raises(gate.ScanError, match="at least one"):
        gate.scan_paths([])


def test_walk_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()

    def fail_walk(*args: object, **kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(gate.os, "walk", fail_walk)
    with pytest.raises(gate.ScanError, match="cannot traverse"):
        gate.scan_paths([source_dir])


def test_walk_callback_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()

    def call_onerror(
        directory: Path, *, followlinks: bool, onerror: object
    ) -> list[object]:
        del followlinks
        onerror(PermissionError(13, "denied", str(directory)))
        return []

    monkeypatch.setattr(gate.os, "walk", call_onerror)
    with pytest.raises(gate.ScanError, match="cannot traverse"):
        gate.scan_paths([source_dir])


def test_walk_rejects_symlinked_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    linked = source_dir / "linked"
    linked.mkdir(parents=True)
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked or is_symlink(path),
    )

    with pytest.raises(gate.ScanError, match="source directory symlink"):
        gate.scan_paths([source_dir])


def test_walk_rejects_symlinked_python_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()
    linked = source_dir / "linked.py"
    linked.write_text("value = 1\n", encoding="utf-8")
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked or is_symlink(path),
    )

    with pytest.raises(gate.ScanError, match="source file symlink"):
        gate.scan_paths([source_dir])


def test_root_junction_is_rejected_before_directory_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "root-junction"
    source_dir.mkdir()
    is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == source_dir or is_junction(path),
    )

    def fail_walk(*args: object, **kwargs: object) -> None:
        raise AssertionError("junction root must be rejected before traversal")

    monkeypatch.setattr(gate.os, "walk", fail_walk)
    with pytest.raises(gate.ScanError, match="source path junction"):
        gate.scan_paths([source_dir])


def test_nested_junction_is_rejected_before_walking_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    linked = source_dir / "linked"
    linked.mkdir(parents=True)
    (source_dir / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (linked / "outside.py").write_text("import pickle\n", encoding="utf-8")

    is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == linked or is_junction(path),
    )
    real_walk = gate.os.walk
    visited: list[Path] = []

    def track_walk(*args: object, **kwargs: object) -> object:
        for entry in real_walk(*args, **kwargs):
            visited.append(Path(entry[0]))
            yield entry

    monkeypatch.setattr(gate.os, "walk", track_walk)
    with pytest.raises(gate.ScanError, match="source directory junction"):
        gate.scan_paths([source_dir])

    assert visited == [source_dir]


def test_junction_check_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    is_junction = Path.is_junction

    def fail_junction_check(path: Path) -> bool:
        if path == source:
            raise PermissionError("denied")
        return is_junction(path)

    monkeypatch.setattr(Path, "is_junction", fail_junction_check)
    with pytest.raises(gate.ScanError, match="cannot inspect source path"):
        gate.scan_paths([source])


def test_input_symlinks_and_non_regular_paths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "linked.py"
    special = tmp_path / "special"
    real_lstat = Path.lstat

    def fake_lstat(path: Path) -> object:
        if path == linked:
            return SimpleNamespace(st_mode=stat.S_IFLNK)
        if path == special:
            return SimpleNamespace(st_mode=stat.S_IFCHR)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(gate.ScanError, match="source path symlink"):
        gate.scan_paths([linked])
    with pytest.raises(gate.ScanError, match="not a regular file or directory"):
        gate.scan_paths([special])


def test_resolution_and_read_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    real_resolve = Path.resolve

    def fail_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path == source:
            raise RuntimeError("resolution failed")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(gate.ScanError, match="cannot inspect source path"):
        gate.scan_paths([source])


def test_tokenize_open_reads_valid_pep263_source(tmp_path: Path) -> None:
    source = tmp_path / "latin1.py"
    source.write_bytes(b"# coding: latin-1\nname = 'caf\xe9'\n")

    count, findings = gate.scan_paths([source])

    assert count == 1
    assert findings == ()


def test_tokenize_open_reads_utf8_bom_and_finds_pickle_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bom.py"
    source.write_bytes(b"\xef\xbb\xbfimport pickle  # nosec\n")

    count, findings = gate.scan_paths([source])

    assert count == 1
    assert len(findings) == 1
    assert "pickle" in findings[0].message


@pytest.mark.parametrize(
    "content",
    [
        b"\xff",
        b"# coding: unknown-codec\nvalue = 1\n",
    ],
)
def test_invalid_source_encodings_fail_closed(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "invalid.py"
    source.write_bytes(content)

    with pytest.raises(gate.ScanError, match="cannot read Python source"):
        gate.scan_paths([source])


def test_main_returns_distinct_status_for_clean_findings_and_scan_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = tmp_path / "clean.py"
    unsafe = tmp_path / "unsafe.py"
    invalid = tmp_path / "invalid.py"
    empty = tmp_path / "empty"
    empty.mkdir()
    clean.write_text("value = 1\n", encoding="utf-8")
    unsafe.write_text("from _pickle import loads # nosec\n", encoding="utf-8")
    invalid.write_text("def invalid(:\n", encoding="utf-8")

    assert gate.ALLOWED_PICKLE_FINDING_COUNT == 0
    assert gate.main([str(clean)]) == 0
    assert "allowed=0" in capsys.readouterr().out
    assert gate.main([str(unsafe)]) == 1
    assert "pickle" in capsys.readouterr().out.lower()
    assert gate.main([str(invalid)]) == 2
    assert "no_pickle_scan_error" in capsys.readouterr().err
    assert gate.main([str(empty)]) == 2
    assert "no_pickle_scan_error" in capsys.readouterr().err


def test_script_entrypoint_exits_with_scanner_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(MODULE_PATH), str(clean)])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(MODULE_PATH), run_name="__main__")

    assert exc_info.value.code == 0
