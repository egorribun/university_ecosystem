"""Exercise Dockerfile discovery and failure propagation in the real Make recipe."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.owned_nats_outage import Deadline
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessRequest,
    ProcessOutcome,
    run_private_process,
)

_ROOT = Path(__file__).resolve().parents[2]
_DOCKERFILES = (
    "backend.Dockerfile",
    "frontend.Dockerfile",
    "Dockerfile.test",
    "Dockerfile.protogen",
    "nested service/Dockerfile",
    "containers/quality/Dockerfile.performance-rust",
)
_IGNORED_FILES = (
    "Dockerfile.test.dockerignore",
    "nested service/.dockerignore",
    "node_modules/example/Dockerfile",
    ".git/example/Dockerfile",
)


@pytest.fixture
def docker_lint_fixture(tmp_path: Path):
    assert os.name == "posix", "Hosted contract requires POSIX process support"
    make = shutil.which("make")
    assert make is not None, "Hosted runner must provide GNU make"
    root = tmp_path / "lint workspace"
    root.mkdir()
    bin_path = root / "bin"
    bin_path.mkdir()
    for tool in ("find", "which"):
        executable = shutil.which(tool)
        assert executable is not None, f"Hosted runner must provide {tool}"
        (bin_path / tool).symlink_to(Path(executable).resolve())
    (root / "Makefile").write_text(
        (_ROOT / "Makefile").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for relative in (*_DOCKERFILES, *_IGNORED_FILES):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM scratch\n", encoding="utf-8")
    # A matching directory must not be passed to the linter as an input file.
    (root / "Dockerfile.directory").mkdir()
    source = dedent(
        """\
        import json
        import sys
        from pathlib import Path

        root = Path.cwd()
        arguments = sys.argv[1:]
        if arguments[:4] != ["--ignore", "DL3008", "--ignore", "DL3009"]:
            raise SystemExit(91)
        with (root / "lint-calls.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(arguments[4:]) + "\\n")
        if (root / "lint-failure").exists():
            raise SystemExit(23)
        """
    )
    hadolint = bin_path / "hadolint"
    hadolint.write_text(f"#!{Path(sys.executable).resolve()}\n{source}", encoding="utf-8")
    hadolint.chmod(0o700)
    return root, str(Path(make).resolve()), {"PATH": str(bin_path), "LC_ALL": "C.UTF-8"}


def _run_docker_lint(fixture):
    root, make, environment = fixture
    request = PrivateProcessRequest(
        argv=(make, "docker-lint"),
        cwd=str(root),
        env=environment,
        stdout_limit=32_768,
        stderr_limit=32_768,
    )
    result = run_private_process(
        request, deadline=Deadline.after(10.0, clock=time.monotonic)
    )
    assert result.outcome is ProcessOutcome.EXITED
    assert result.local_cleanup is LocalCleanup.CONFIRMED
    return result


def test_docker_lint_discovers_all_recipe_names_without_ignore_files(
    docker_lint_fixture,
) -> None:
    root, _make, _environment = docker_lint_fixture
    result = _run_docker_lint(docker_lint_fixture)
    assert result.returncode == 0
    calls = [
        json.loads(line)
        for line in (root / "lint-calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    actual = [Path(path).as_posix() for call in calls for path in call]
    assert sorted(actual) == sorted(_DOCKERFILES)


def test_docker_lint_propagates_linter_failure(docker_lint_fixture) -> None:
    root, _make, _environment = docker_lint_fixture
    (root / "lint-failure").touch()
    result = _run_docker_lint(docker_lint_fixture)
    assert result.returncode != 0
    assert b"Dockerfile lint passed." not in result.stdout
