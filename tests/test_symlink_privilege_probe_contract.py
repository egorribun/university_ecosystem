"""AUD-332: symlink tests are gated by a native privilege probe, not by os.name."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from defusedxml import ElementTree as SafeElementTree

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


@pytest.mark.parametrize(
    ("denied_kind", "targets", "skip_reasons"),
    [
        (
            "directory",
            (
                (
                    "test_start_docker_live_owner_key_paths.py",
                    "test_common_git_metadata_rejects_reparse_directory_when_supported",
                ),
                (
                    "test_secret_file_config_contract.py",
                    "test_file_loader_follows_projected_secret_symlink_when_supported",
                ),
            ),
            {
                "test_common_git_metadata_rejects_reparse_directory_when_supported": (
                    "native directory symlink privilege is unavailable (AUD-332 probe)"
                ),
                "test_file_loader_follows_projected_secret_symlink_when_supported": (
                    "native directory and file symlink privileges are unavailable "
                    "(AUD-332 probe)"
                ),
            },
        ),
        (
            "file",
            (
                (
                    "test_start_docker_live_owner_key_paths.py",
                    "test_worktree_owner_rejects_reparse_common_key_when_supported",
                ),
                (
                    "test_secret_file_config_contract.py",
                    "test_file_loader_follows_projected_secret_symlink_when_supported",
                ),
            ),
            {
                "test_worktree_owner_rejects_reparse_common_key_when_supported": (
                    "native file symlink privilege is unavailable (AUD-332 probe)"
                ),
                "test_file_loader_follows_projected_secret_symlink_when_supported": (
                    "native directory and file symlink privileges are unavailable "
                    "(AUD-332 probe)"
                ),
            },
        ),
    ],
)
def test_when_supported_cases_skip_after_native_probe_denial(
    tmp_path: Path,
    denied_kind: str,
    targets: tuple[tuple[str, str], ...],
    skip_reasons: dict[str, str],
) -> None:
    """Exercise collection and real test markers after a simulated OS refusal."""
    plugin = tmp_path / "aud332_refuse_symlink.py"
    plugin.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "original = Path.symlink_to\n"
        "def refuse_selected_kind(self, target, target_is_directory=False):\n"
        "    kind = 'directory' if target_is_directory else 'file'\n"
        "    if kind == os.environ['AUD332_DENIED_KIND']:\n"
        "        with open(os.environ['AUD332_PROBE_CALLS'], 'a', encoding='utf-8') as log:\n"
        "            log.write(kind + '\\n')\n"
        "        raise OSError(1314, 'A required privilege is not held by the client')\n"
        "    return original(self, target, target_is_directory=target_is_directory)\n"
        "Path.symlink_to = refuse_selected_kind\n",
        encoding="utf-8",
    )
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    report = tmp_path / "report.xml"
    calls = tmp_path / "probe-calls.txt"
    # Collection imports app settings in the projected-secret case. Keep that
    # import independent of any configured real services or secret files.
    inherited = {
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in inherited}
    env.update(
        {
            "AUD332_DENIED_KIND": denied_kind,
            "AUD332_PROBE_CALLS": str(calls),
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "ENVIRONMENT": "testing",
            "ENV_FILE_PATH": "",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONPATH": os.pathsep.join(
                (
                    str(tmp_path),
                    str(TESTS_ROOT.parent),
                    os.environ.get("PYTHONPATH", ""),
                )
            ),
            "SECRET_KEY": "s" * 64,
        }
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and pytest arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(config),
            "-p",
            plugin.stem,
            "--noconftest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp_path / 'child-temp'}",
            f"--junitxml={report}",
            *(
                f"{TESTS_ROOT / filename}::{test_name}"
                for filename, test_name in targets
            ),
        ],
        cwd=TESTS_ROOT.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == [denied_kind]
    cases = {
        case.get("name"): case
        for case in SafeElementTree.parse(report).getroot().findall(".//testcase")
    }
    assert set(cases) == set(skip_reasons)
    for test_name, skip_reason in skip_reasons.items():
        skipped = cases[test_name].find("skipped")
        assert skipped is not None and skipped.get("message") == skip_reason
