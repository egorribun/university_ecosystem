"""Regression controls for skipped compatibility and SBOM gates."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
COMPATIBILITY_NAMES = {
    "backend-tests-unit-dummy": (
        "Backend Tests (Python 3.14) / Unit Tests (All-Python 3.14)"
    ),
    "backend-tests-integration-dummy": (
        "Backend Tests (Python 3.14) / Integration Tests (All-Python 3.14)"
    ),
}
SBOM_RESULTS = {
    "PYTHON_SBOM_RESULT": "${{ needs.sbom-python.result }}",
    "GO_SBOM_RESULT": "${{ needs.sbom-go.result }}",
    "RUST_SBOM_RESULT": "${{ needs.sbom-rust.result }}",
}
SCANNERS = {
    "Python — known-vulnerability allowlist gate": "osv_batch_audit.py",
    "Go — govulncheck reachable vulnerability gate": "govulncheck",
    "Rust — high/critical/unknown vulnerability gate": "cargo audit",
}
RESULTS = ("success", "failure", "cancelled", "skipped", "", None, "unexpected")


def _workflow(name: str) -> dict[str, Any]:
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    return workflow


def _first_step(job: dict[str, Any]) -> dict[str, Any]:
    steps = job["steps"]
    assert isinstance(steps, list) and steps
    assert isinstance(steps[0], dict)
    return steps[0]


def _assert_guard_metadata(
    step: dict[str, Any], name: str, expected_env: dict[str, str]
) -> None:
    assert step.get("name") == name
    assert step.get("shell") == "bash"
    assert "if" not in step
    assert step.get("continue-on-error", False) is False
    assert step.get("env") == expected_env
    assert isinstance(step.get("run"), str)


def _bash() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_bash = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if git_bash.is_file():
                return str(git_bash)
    bash = shutil.which("bash")
    assert bash is not None, "Bash is required to execute the workflow guards"
    return bash


def _run_guard(
    script: str, values: dict[str, str | None]
) -> subprocess.CompletedProcess[str]:
    # Only ordinary process settings and the intended result values are passed.
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR")
        if key in os.environ
    }
    env.update({key: value for key, value in values.items() if value is not None})

    async def run() -> subprocess.CompletedProcess[str]:
        command = [
            _bash(),
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            script,
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=ROOT,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except BaseException:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
            raise
        assert process.returncode is not None
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    return asyncio.run(run())


@pytest.mark.parametrize("job_id", COMPATIBILITY_NAMES)
def test_compatibility_job_runs_after_any_backend_outcome(job_id: str) -> None:
    job = _workflow("ci.yml")["jobs"][job_id]
    assert job["name"] == COMPATIBILITY_NAMES[job_id]
    assert job["needs"] == "backend-tests"
    assert job.get("if") == "${{ always() }}"
    _assert_guard_metadata(
        _first_step(job),
        "Require successful backend tests",
        {"BACKEND_TEST_RESULT": "${{ needs.backend-tests.result }}"},
    )


@pytest.mark.parametrize("job_id", COMPATIBILITY_NAMES)
@pytest.mark.parametrize("result", RESULTS)
def test_compatibility_script_accepts_only_success(
    job_id: str, result: str | None
) -> None:
    step = _first_step(_workflow("ci.yml")["jobs"][job_id])
    # The pre-fix job has a single echo script; executing it shows the false
    # success directly. After repair the first step must be the named guard.
    assert step.get("name") in (None, "Require successful backend tests")
    script = step.get("run")
    assert isinstance(script, str), "the first compatibility step must run a guard"
    run = _run_guard(script, {"BACKEND_TEST_RESULT": result})
    assert (run.returncode == 0) == (result == "success"), (run.stdout, run.stderr)


def test_main_sbom_gate_runs_after_any_report_outcome_with_original_scope() -> None:
    workflow = _workflow("sbom.yml")
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers and "workflow_dispatch" in triggers
    gate = workflow["jobs"]["vuln-gate"]
    assert gate["name"] == "Vulnerability gate (CRITICAL/HIGH, main)"
    assert gate["needs"] == ["sbom-python", "sbom-go", "sbom-rust"]
    assert gate["if"] == (
        "${{ always() && github.ref == 'refs/heads/main' "
        "&& github.event_name != 'pull_request' }}"
    )
    _assert_guard_metadata(
        _first_step(gate), "Require successful SBOM producers", SBOM_RESULTS
    )


@pytest.mark.parametrize("result", RESULTS)
@pytest.mark.parametrize("dependency", tuple(SBOM_RESULTS))
def test_main_sbom_guard_rejects_each_non_successful_report(
    dependency: str, result: str | None
) -> None:
    step = _first_step(_workflow("sbom.yml")["jobs"]["vuln-gate"])
    assert step.get("name") == "Require successful SBOM producers", (
        "the first step must guard producer results before scanners"
    )
    script = step.get("run")
    assert isinstance(script, str)
    values: dict[str, str | None] = dict.fromkeys(SBOM_RESULTS, "success")
    values[dependency] = result
    run = _run_guard(script, values)
    assert (run.returncode == 0) == (result == "success"), (run.stdout, run.stderr)


def test_sbom_scanners_and_separate_read_only_pr_gate_remain_present() -> None:
    jobs = _workflow("sbom.yml")["jobs"]
    pr_gate = jobs["vuln-gate-pr"]
    assert pr_gate["name"] == "Vulnerability gate (CRITICAL/HIGH)"
    assert pr_gate["if"] == "${{ github.event_name == 'pull_request' }}"
    assert pr_gate["permissions"] == {"contents": "read"}
    assert "needs" not in pr_gate
    assert pr_gate["steps"][0]["with"]["persist-credentials"] is False
    for job_id in ("vuln-gate", "vuln-gate-pr"):
        by_name = {step.get("name"): step for step in jobs[job_id]["steps"]}
        for name, command in SCANNERS.items():
            step = by_name[name]
            assert command in step["run"]
            assert "if" not in step
            assert step.get("continue-on-error", False) is False
