"""End-to-end contracts for the fail-closed Lighthouse selector CLI."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.quality.select_lighthouse_artifacts_cli as lighthouse_cli
from scripts.quality.coverage_retry_context import build_consumer_retry_context
from scripts.quality.select_lighthouse_artifacts import (
    LIGHTHOUSE_LOGICAL_ARTIFACT,
    LIGHTHOUSE_METADATA_PATH,
    expected_lighthouse_report_specs,
)
from scripts.quality.select_lighthouse_artifacts_cli import main

GIT_EXECUTABLE = shutil.which("git")
REPOSITORY = "example/university-ecosystem"
RUN_ID = "123456789"
WORKFLOW_REF = "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
WORKFLOW_SHA = "b" * 40
EVENT = "pull_request"
CONSUMER_JOB = "performance-gate"


def _git_head(repository_root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()


@pytest.fixture
def repository_root(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=root, check=True
    )
    _write(root, "config/lighthouse.toml", b"routes = ['core']\n")
    _write(root, "quality/policy.json", b'{"lighthouse":100}\n')
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "add", "."], cwd=root, check=True
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
        cwd=root,
        check=True,
    )
    return root


def _write(repository_root: Path, relative_path: str, content: bytes) -> Path:
    path = repository_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _context(repository_root: Path) -> dict[str, str]:
    return build_consumer_retry_context(
        repository_root=repository_root,
        config_inputs=("config/lighthouse.toml",),
        policy_inputs=("quality/policy.json",),
        repository=REPOSITORY,
        run_id=RUN_ID,
        workflow_ref=WORKFLOW_REF,
        workflow_sha=WORKFLOW_SHA,
        event=EVENT,
    )


def _write_candidate(
    *, parent: Path, repository_root: Path, attempt: str = "1"
) -> Path:
    candidate = parent / f"{LIGHTHOUSE_LOGICAL_ARTIFACT}-attempt-{attempt}"
    candidate.mkdir(parents=True)
    reports: list[dict[str, object]] = []
    for report_index, specification in enumerate(expected_lighthouse_report_specs()):
        report = candidate / specification.path
        report.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(
                {
                    "finalUrl": f"https://example.test/{report_index}",
                    "requestedUrl": f"https://example.test/{report_index}",
                },
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        report.write_bytes(content)
        reports.append(
            {
                "component": specification.component,
                "format": specification.report_format,
                "path": specification.path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "byte_size": len(content),
            }
        )
    context = _context(repository_root)
    metadata = {
        "schema_version": 2,
        "commit_sha": context["source_sha"],
        "collected_at": "2026-08-29T12:34:56Z",
        "producer": {
            "identity_provider": "github-actions",
            "repository": REPOSITORY,
            "workflow_ref": WORKFLOW_REF,
            "workflow_sha": WORKFLOW_SHA,
            "run_id": RUN_ID,
            "run_attempt": attempt,
            "event": EVENT,
            "job": "lighthouse",
            "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        },
        "tool_versions": {"@lhci/cli": "0.15.1", "node": "24.0.0"},
        "reports": reports,
        "retry_provenance": {
            **context,
            "run_attempt": attempt,
            "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        },
    }
    metadata_path = candidate / LIGHTHOUSE_METADATA_PATH
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def _arguments(repository_root: Path, candidate: Path) -> list[str]:
    return [
        "--repository-root",
        str(repository_root),
        "--candidate-root",
        str(candidate),
        "--destination-root",
        "artifacts/lighthouse-selection",
        "--repository",
        REPOSITORY,
        "--run-id",
        RUN_ID,
        "--run-attempt",
        "2",
        "--workflow-ref",
        WORKFLOW_REF,
        "--workflow-sha",
        WORKFLOW_SHA,
        "--event",
        EVENT,
        "--consumer-job",
        CONSUMER_JOB,
        "--config-input",
        "config/lighthouse.toml",
        "--policy-input",
        "quality/policy.json",
    ]


def test_requires_identity_paths_and_rejects_retry_context_blobs() -> None:
    with pytest.raises(SystemExit, match="2"):
        main([])

    with pytest.raises(SystemExit, match="2"):
        main(["--retry-context", "untrusted.json"])


def test_module_entrypoint_propagates_parser_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["select_lighthouse_artifacts_cli.py"])
    specification = importlib.util.spec_from_file_location(
        "__main__", lighthouse_cli.__file__
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)

    with pytest.raises(SystemExit, match="2"):
        specification.loader.exec_module(module)


def test_rejects_invalid_trusted_identity_before_materialization(
    repository_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _write_candidate(
        parent=tmp_path / "downloads", repository_root=repository_root
    )
    arguments = _arguments(repository_root, candidate)
    workflow_sha_index = arguments.index("--workflow-sha") + 1
    arguments[workflow_sha_index] = "not-a-sha"

    assert main(arguments) == 1

    captured = capsys.readouterr()
    assert "workflow_sha must be an exact lowercase 40-character SHA" in captured.err
    assert not (repository_root / "artifacts/lighthouse-selection").exists()


def test_selects_verified_lighthouse_evidence_and_binds_consumer_job(
    repository_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _write_candidate(
        parent=tmp_path / "downloads", repository_root=repository_root
    )

    assert main(_arguments(repository_root, candidate)) == 0

    result = json.loads(capsys.readouterr().out)
    destination = repository_root / "artifacts/lighthouse-selection"
    receipt = json.loads(
        (destination / "selection-receipt.json").read_text(encoding="utf-8")
    )
    assert result == {
        "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        "consumer_job": CONSUMER_JOB,
        "physical_artifact": "lighthouse-reports-attempt-1",
        "producer_attempt": 1,
        "receipt_path": str(destination / "selection-receipt.json"),
    }
    assert receipt["consumer"]["job"] == CONSUMER_JOB
    assert receipt["consumer"]["commit_sha"] == _git_head(repository_root)
    assert receipt["consumer"]["retry_context"] == _context(repository_root)
