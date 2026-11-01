"""AUD-332: symlink tests are gated by a native privilege probe, not by os.name."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import tests.symlink_support as symlink_support

TESTS_ROOT = Path(__file__).resolve().parent
_PROBE_NAMES = ("DIRECTORY_SYMLINKS_SUPPORTED", "FILE_SYMLINKS_SUPPORTED")


def _creates_symlink(function: ast.AST) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"symlink_to", "symlink"}:
                return True
    return False


def _probe_gated(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        text = ast.unparse(decorator)
        if "skipif" in text and any(name in text for name in _PROBE_NAMES):
            return True
    return False


def _ungated_when_supported_symlink_tests(
    sources: dict[str, str],
) -> list[str]:
    offenders: list[str] = []
    for name, source in sorted(sources.items()):
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.endswith("_when_supported"):
                continue
            if _creates_symlink(node) and not _probe_gated(node):
                offenders.append(f"{name}::{node.name}")
    return offenders


def test_file_symlink_probe_reports_unprivileged_creation_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_symlink(
        self: Path, target: object, target_is_directory: bool = False
    ) -> None:
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(Path, "symlink_to", refuse_symlink)

    assert symlink_support._file_symlinks_supported() is False


def test_directory_symlink_probe_reports_unprivileged_creation_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_symlink(
        self: Path, target: object, target_is_directory: bool = False
    ) -> None:
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(Path, "symlink_to", refuse_symlink)

    assert symlink_support._directory_symlinks_supported() is False


def test_probe_flags_match_the_native_symlink_capability() -> None:
    assert isinstance(symlink_support.FILE_SYMLINKS_SUPPORTED, bool)
    assert isinstance(symlink_support.DIRECTORY_SYMLINKS_SUPPORTED, bool)


def test_every_when_supported_symlink_test_is_probe_gated() -> None:
    sources = {
        str(path.relative_to(TESTS_ROOT)): path.read_text(encoding="utf-8")
        for path in TESTS_ROOT.rglob("test_*.py")
    }

    assert _ungated_when_supported_symlink_tests(sources) == []


def test_census_detects_an_ungated_when_supported_symlink_test() -> None:
    ungated = (
        "def test_link_when_supported(tmp_path):\n"
        "    (tmp_path / 'a').symlink_to(tmp_path / 'b')\n"
    )
    gated = (
        "import pytest\n"
        "from tests.symlink_support import FILE_SYMLINKS_SUPPORTED\n"
        "@pytest.mark.skipif(not FILE_SYMLINKS_SUPPORTED, reason='probe')\n"
        "def test_link_when_supported(tmp_path):\n"
        "    (tmp_path / 'a').symlink_to(tmp_path / 'b')\n"
    )
    hard_link_only = (
        "def test_output_rejects_hard_links_when_supported(tmp_path):\n    pass\n"
    )

    offenders = _ungated_when_supported_symlink_tests(
        {"ungated.py": ungated, "gated.py": gated, "hard.py": hard_link_only}
    )

    assert offenders == ["ungated.py::test_link_when_supported"]
