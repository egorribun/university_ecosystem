"""Contract for the native Windows proof job (AUD-332 and AUD-436).

The job must run the Windows-only proofs on a Windows runner, pin every action,
never mark itself as continue-on-error, and feed the CI Success aggregate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CI = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _ci() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(CI.read_text(encoding="utf-8"))
    return document


def _job() -> dict[str, Any]:
    job: dict[str, Any] = _ci()["jobs"]["windows-live-proofs"]
    return job


def _run_text(steps: list[dict[str, Any]]) -> str:
    return "\n".join(str(step.get("run", "")) for step in steps)


def test_windows_job_runs_on_a_windows_hosted_runner() -> None:
    job = _job()

    assert job["runs-on"] == "windows-latest"
    assert "continue-on-error" not in job


def test_windows_job_pins_every_action_to_a_full_commit_sha() -> None:
    uses = [str(step["uses"]) for step in _job()["steps"] if "uses" in step]

    assert uses, "the job must check out and set up its toolchain"
    for reference in uses:
        pin = reference.split("@", 1)[1].split(" ", 1)[0]
        assert FULL_SHA.match(pin), reference


def test_windows_job_executes_both_proofs_and_rejects_skips() -> None:
    run = _run_text(_job()["steps"])

    for path in (
        "tests/test_start_docker_live_owner_key_paths.py",
        "tests/test_start_docker_live_stand_state_root.py",
        "tests/test_symlink_privilege_probe_contract.py",
        "tests/test_live_stand_subprocess_timeouts.py",
        "tests/test_seed_owned_stand_record.py",
    ):
        assert path in run, path
    for posix_only in (
        "test_launcher_rejects_permissive_owned_state_root_before_secret_reads",
        "test_posix_lifecycle_lock_wait_is_bounded",
    ):
        assert "--deselect" in run and posix_only in run
    assert "-rs" in run
    assert "skipped" in run and "unexecuted" in run


def test_windows_job_feeds_the_ci_success_aggregate() -> None:
    ci = _ci()

    assert "windows-live-proofs" in ci["jobs"]["ci-success"]["needs"]
    aggregate = _run_text(ci["jobs"]["ci-success"]["steps"])
    assert "windows-live-proofs|${{ needs.windows-live-proofs.result }}" in aggregate
