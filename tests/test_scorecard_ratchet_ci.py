"""Exercise the PR ratchet step against actual Git commit objects."""

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
POLICY = Path("quality/scorecard-floors.json")
GATE = Path("scripts/quality/scorecard_floors_gate.py")


def _git(repo: Path, *arguments: str) -> str:
    return baseline_support._git(repo, *arguments)


def _policy(sast: int = 9) -> dict[str, object]:
    policy = json.loads((ROOT / POLICY).read_text(encoding="utf-8"))
    policy["gated_checks"]["SAST"] = sast
    return policy


def _add_policy(repo: Path, sast: int = 9, gate: str | None = None) -> None:
    (repo / POLICY).parent.mkdir(parents=True, exist_ok=True)
    (repo / POLICY).write_text(json.dumps(_policy(sast)), encoding="utf-8")
    (repo / GATE).parent.mkdir(parents=True, exist_ok=True)
    (repo / GATE).write_text(
        gate if gate is not None else (ROOT / GATE).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _commit(repo: Path) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", "fixture")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repository"
    path.mkdir()
    _git(path, "init", "--quiet")
    _git(path, "config", "user.name", "Scorecard test")
    _git(path, "config", "user.email", "scorecard@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "remote", "add", "origin", path.as_uri())
    return path


def _run_step(
    repo: Path, tmp_path: Path, base: str, tested: str
) -> subprocess.CompletedProcess[str]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["pre-commit-check"]["steps"]
    matches = [
        step for step in steps if step.get("name") == "Enforce Scorecard floor ratchet"
    ]
    assert len(matches) == 1
    step = matches[0]
    assert step["if"] == "${{ github.event_name == 'pull_request' }}"
    assert step["env"] == {
        "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "TESTED_SHA": "${{ github.sha }}",
    }

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
        patch.setenv("TESTED_SHA", tested)
        result, _ = baseline_support._extract(repo, tmp_path, "pull_request", base, "")
    return result


def test_ratchet_accepts_a_floor_raise_against_the_base_commit(
    repo: Path, tmp_path: Path
) -> None:
    _add_policy(repo)
    base = _commit(repo)
    _add_policy(repo, sast=10)
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode == 0, result.stderr


def test_ratchet_uses_base_checker_and_tested_commit_policy(
    repo: Path, tmp_path: Path
) -> None:
    _add_policy(repo, sast=10)
    base = _commit(repo)
    _add_policy(repo, sast=9, gate="raise SystemExit(0)\n")
    tested = _commit(repo)
    # A modified worktree must not replace the policy from the tested commit.
    (repo / POLICY).write_text(json.dumps(_policy(10)), encoding="utf-8")

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode != 0
    assert "SAST floor decreased from 10 to 9" in result.stderr


def test_ratchet_bootstraps_when_both_base_files_are_absent(
    repo: Path, tmp_path: Path
) -> None:
    base = _commit(repo)
    _add_policy(repo)
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode == 0, result.stderr


def test_ratchet_skips_branches_where_neither_side_has_the_policy(
    repo: Path, tmp_path: Path
) -> None:
    base = _commit(repo)
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode == 0, result.stderr


def test_ratchet_rejects_incomplete_trusted_base(repo: Path, tmp_path: Path) -> None:
    _add_policy(repo)
    (repo / GATE).unlink()
    base = _commit(repo)
    _add_policy(repo)
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode != 0
    assert "incomplete Scorecard floor policy" in result.stdout


@pytest.mark.parametrize("removed", [POLICY, GATE])
def test_ratchet_rejects_removing_either_policy_file(
    repo: Path, tmp_path: Path, removed: Path
) -> None:
    _add_policy(repo)
    base = _commit(repo)
    (repo / removed).unlink()
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, base, tested)

    assert result.returncode != 0
    assert "must both be present" in result.stdout


def test_ratchet_rejects_unavailable_base_commit(repo: Path, tmp_path: Path) -> None:
    _add_policy(repo)
    tested = _commit(repo)

    result = _run_step(repo, tmp_path, "0" * 40, tested)

    assert result.returncode != 0
