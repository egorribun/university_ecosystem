"""Exercise the Scorecard post-scan source check with real Git repositories."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests import test_contract_validation_workflow_contract as baseline_support

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_repositories(tmp_path: Path) -> tuple[Path, Path, str]:
    origin = tmp_path / "origin"
    origin.mkdir()
    git = baseline_support._git
    git(origin, "init", "--quiet", "--initial-branch=main")
    git(origin, "config", "user.name", "Scorecard test")
    git(origin, "config", "user.email", "scorecard@example.invalid")
    git(origin, "config", "commit.gpgsign", "false")
    for relative in (
        Path("quality/scorecard-floors.json"),
        Path("scripts/quality/scorecard_floors_gate.py"),
    ):
        (origin / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, origin / relative)
    git(origin, "add", "--all")
    git(origin, "commit", "--quiet", "-m", "source")
    event_sha = git(origin, "rev-parse", "HEAD")
    checkout = tmp_path / "checkout"
    git(tmp_path, "clone", "--quiet", "--depth=1", origin.as_uri(), str(checkout))
    return origin, checkout, event_sha


def _run_source_step(
    checkout: Path, tmp_path: Path, event_sha: str, outcome: str = "success"
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/scorecard.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["analysis"]["steps"]
    step = next(
        step for step in steps if step.get("name") == "Verify Scorecard report source"
    )
    assert "steps.trusted_source.outcome == 'success'" in step["if"]
    assert "steps.scorecard-sarif.outcome == 'success'" in step["if"]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "python3"
    shim.write_text(
        f'#!/bin/sh\nexec {shlex.quote(Path(sys.executable).as_posix())} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    if os.name == "nt":
        git_executable = Path(shutil.which("git") or "")
        bash = git_executable.parent.parent / "bin/bash.exe"
    else:
        bash = Path(shutil.which("bash") or "")
    assert bash.is_file()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(baseline_support, "_baseline_step", lambda: step)
        patch.setattr(
            baseline_support,
            "which",
            lambda name: str(bash) if name == "bash" else shutil.which(name),
        )
        patch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
        patch.setenv("EVENT_SHA", event_sha)
        patch.setenv("SCORECARD_RESULT_OUTCOME", outcome)
        result, _ = baseline_support._extract(checkout, tmp_path, "push", "", "")
    return result


def _write_result(checkout: Path, commit: str) -> None:
    (checkout / "scorecard-results.json").write_text(
        json.dumps({"repo": {"commit": commit}, "checks": []}), encoding="utf-8"
    )


def test_source_check_accepts_matching_main_and_native_json(
    source_repositories: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, checkout, sha = source_repositories
    _write_result(checkout, sha)

    result = _run_source_step(checkout, tmp_path, sha)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("json_outcome", ["success", "failure"])
def test_source_check_rejects_a_new_main_tip(
    source_repositories: tuple[Path, Path, str], tmp_path: Path, json_outcome: str
) -> None:
    origin, checkout, sha = source_repositories
    _write_result(checkout, sha)
    (origin / "new-file").write_text("new commit", encoding="utf-8")
    baseline_support._git(origin, "add", "new-file")
    baseline_support._git(origin, "commit", "--quiet", "-m", "advance main")

    result = _run_source_step(checkout, tmp_path, sha, outcome=json_outcome)

    assert result.returncode != 0
    assert "main changed" in result.stdout


def test_source_check_rejects_native_result_from_another_commit(
    source_repositories: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, checkout, sha = source_repositories
    _write_result(checkout, "b" * 40)

    result = _run_source_step(checkout, tmp_path, sha)

    assert result.returncode != 0
    assert "does not match the event commit" in result.stderr


def test_source_check_rejects_missing_successful_json_scan(
    source_repositories: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, checkout, sha = source_repositories

    result = _run_source_step(checkout, tmp_path, sha)

    assert result.returncode != 0
    assert "scan result is unknown" in result.stderr


def test_failed_json_scan_still_allows_a_source_bound_sarif_upload(
    source_repositories: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, checkout, sha = source_repositories

    result = _run_source_step(checkout, tmp_path, sha, outcome="failure")

    assert result.returncode == 0, result.stderr


def test_source_check_rejects_unavailable_remote(
    source_repositories: tuple[Path, Path, str], tmp_path: Path
) -> None:
    _, checkout, sha = source_repositories
    baseline_support._git(
        checkout, "remote", "set-url", "origin", (tmp_path / "absent").as_uri()
    )

    result = _run_source_step(checkout, tmp_path, sha)

    assert result.returncode != 0
