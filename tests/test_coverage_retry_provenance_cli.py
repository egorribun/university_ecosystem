"""End-to-end contracts for the trusted retry-provenance producer CLI."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.quality.coverage_retry_provenance_cli as retry_cli
from scripts.quality.coverage_retry_context import RETRY_PROVENANCE_FIELDS
from scripts.quality.coverage_retry_provenance_cli import main

GIT_EXECUTABLE = shutil.which("git")
REPOSITORY = "example/university-ecosystem"
RUN_ID = "123456789"
RUN_ATTEMPT = "2"
WORKFLOW_REF = "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
WORKFLOW_SHA = "b" * 40
EVENT = "pull_request"
ARTIFACT = "lighthouse-reports"


def _write(repository_root: Path, relative_path: str, content: bytes) -> None:
    path = repository_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=tmp_path, check=True
    )
    _write(tmp_path, "config/lighthouse.toml", b"routes = ['core']\n")
    _write(tmp_path, "quality/policy.json", b'{"lighthouse":100}\n')
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "add", "."], cwd=tmp_path, check=True
    )
    subprocess.run(  # noqa: S603
        [
            GIT_EXECUTABLE,
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def _arguments(repository_root: Path) -> list[str]:
    return [
        "--repository-root",
        str(repository_root),
        "--config-input",
        "config/lighthouse.toml",
        "--policy-input",
        "quality/policy.json",
        "--repository",
        REPOSITORY,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        RUN_ATTEMPT,
        "--workflow-ref",
        WORKFLOW_REF,
        "--workflow-sha",
        WORKFLOW_SHA,
        "--event",
        EVENT,
        "--artifact",
        ARTIFACT,
    ]


def test_requires_explicit_trusted_inputs_and_rejects_untrusted_context_blobs() -> None:
    with pytest.raises(SystemExit, match="2"):
        main([])

    with pytest.raises(SystemExit, match="2"):
        main(["--retry-context", "untrusted.json"])


def test_emits_complete_deterministic_retry_provenance_values(
    repository_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_arguments(repository_root)) == 0

    values = dict(line.split("=", 1) for line in capsys.readouterr().out.splitlines())
    assert tuple(values) == tuple(sorted(RETRY_PROVENANCE_FIELDS))
    assert set(values) == RETRY_PROVENANCE_FIELDS
    assert values == {
        "repository": REPOSITORY,
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "source_sha": subprocess.check_output(  # noqa: S603
            [GIT_EXECUTABLE, "rev-parse", "HEAD"],
            cwd=repository_root,
            text=True,
        ).strip(),
        "source_revision": values["source_sha"],
        "workflow_ref": WORKFLOW_REF,
        "workflow_sha": WORKFLOW_SHA,
        "event": EVENT,
        "config_digest": values["config_digest"],
        "policy_digest": values["policy_digest"],
        "artifact": ARTIFACT,
    }


def test_fails_closed_before_output_for_invalid_identity(
    repository_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = _arguments(repository_root)
    workflow_sha_index = arguments.index("--workflow-sha") + 1
    arguments[workflow_sha_index] = "not-a-sha"

    assert main(arguments) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "workflow_sha must be an exact lowercase 40-character SHA" in captured.err


def test_module_entrypoint_propagates_parser_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["coverage_retry_provenance_cli.py"])
    specification = importlib.util.spec_from_file_location(
        "__main__", retry_cli.__file__
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)

    with pytest.raises(SystemExit, match="2"):
        specification.loader.exec_module(module)
