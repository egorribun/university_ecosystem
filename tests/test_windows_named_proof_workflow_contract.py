"""Bind the native Windows selection and fail-closed JUnit consumer together."""

from __future__ import annotations

import copy
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _workflow() -> dict[str, Any]:
    result: dict[str, Any] = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    return result


def _assert_windows_job(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["windows-live-proofs"]
    assert job["runs-on"] == "windows-latest"
    assert "if" not in job and "continue-on-error" not in job
    steps = job["steps"]
    names = [step.get("name") for step in steps]
    producer_index = names.index("Run Windows-only proofs")
    consumer_index = names.index("Require every Windows-only proof to execute")
    assert producer_index < consumer_index
    producer, consumer = steps[producer_index], steps[consumer_index]
    assert all(
        "if" not in step and "continue-on-error" not in step
        for step in (producer, consumer)
    )
    argv = shlex.split(producer["run"].replace("\\\n", " "), comments=True)
    assert argv == [
        "set",
        "-euo",
        "pipefail",
        "uv",
        "run",
        "--frozen",
        "--no-sync",
        "pytest",
        "tests/test_start_docker_live_owner_key_paths.py",
        "tests/test_start_docker_live_stand_state_root.py",
        "tests/test_symlink_privilege_probe_contract.py",
        "tests/test_live_stand_subprocess_timeouts.py",
        "tests/test_windows_live_native_subprocess.py",
        "tests/test_windows_named_proofs_gate.py",
        "tests/test_windows_named_proof_workflow_contract.py",
        "tests/test_seed_owned_stand_record.py",
        "--deselect",
        "tests/test_start_docker_live_stand_state_root.py::test_launcher_rejects_permissive_owned_state_root_before_secret_reads",
        "--deselect",
        "tests/test_live_stand_subprocess_timeouts.py::test_posix_lifecycle_lock_wait_is_bounded",
        "-v",
        "--tb=short",
        "-p",
        "no:cacheprovider",
        "-rs",
        "--junitxml=windows-proofs.xml",
    ]
    command = "uv run --frozen --no-sync python scripts/quality/windows_named_proofs_gate.py windows-proofs.xml"
    lines = [line.strip() for line in consumer["run"].splitlines() if line.strip()]
    assert lines[0] == "set -euo pipefail"
    assert lines[-1] == command
    aggregate = workflow["jobs"]["ci-success"]
    assert "windows-live-proofs" in aggregate["needs"]
    assert any(
        "windows-live-proofs|${{ needs.windows-live-proofs.result }}"
        in step.get("run", "")
        for step in aggregate["steps"]
    )


def test_windows_job_executes_the_named_proofs_and_receipt_gate() -> None:
    _assert_windows_job(_workflow())


@pytest.mark.parametrize(
    "mutation",
    [
        "runner",
        "job-condition",
        "step-condition",
        "missing-file",
        "extra-deselection",
        "filter",
        "missing-gate",
        "aggregate",
    ],
)
def test_windows_job_rejects_selector_and_gate_drift(mutation: str) -> None:
    workflow = copy.deepcopy(_workflow())
    job = workflow["jobs"]["windows-live-proofs"]
    steps = job["steps"]
    producer = next(
        step for step in steps if step.get("name") == "Run Windows-only proofs"
    )
    consumer = next(
        step
        for step in steps
        if step.get("name") == "Require every Windows-only proof to execute"
    )
    if mutation == "runner":
        job["runs-on"] = "ubuntu-latest"
    elif mutation == "job-condition":
        job["if"] = "false"
    elif mutation == "step-condition":
        consumer["continue-on-error"] = True
    elif mutation == "missing-file":
        producer["run"] = producer["run"].replace(
            "tests/test_windows_live_native_subprocess.py",
            "tests/test_seed_owned_stand_record.py",
        )
    elif mutation == "extra-deselection":
        producer["run"] += " --deselect=tests/test_windows_live_native_subprocess.py"
    elif mutation == "filter":
        producer["run"] += " -k unrelated"
    elif mutation == "missing-gate":
        consumer["run"] = consumer["run"].replace(
            "windows_named_proofs_gate.py", "other_gate.py"
        )
    else:
        workflow["jobs"]["ci-success"]["needs"].remove("windows-live-proofs")
    with pytest.raises(AssertionError):
        _assert_windows_job(workflow)
