"""Verify CI result reporting treats GitHub job results as data."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
RESULT_ENV = {
    "WS_RESULT": "go-integration-ws-hub",
    "FILE_PROCESSOR_RESULT": "go-integration-file-processor",
    "GATEWAY_RESULT": "go-integration-gateway",
    "DB_MIGRATION_RESULT": "db-migration-integrity",
}
EXPRESSION = re.compile(r"\$\{\{\s*needs\.([a-z0-9-]+)\.result\s*\}\}")


def _report() -> dict:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["ci-success"]["steps"]
    return next(
        step
        for step in steps
        if step.get("name") == "Report integration and migration quality results"
    )


def _run_report(tmp_path: Path, results: dict[str, str]) -> tuple[str, str]:
    step = _report()
    script = EXPRESSION.sub(lambda match: results[match.group(1)], step["run"])
    assert "${{" not in script
    environment = os.environ.copy()
    environment.pop("BASH_ENV", None)
    environment["GITHUB_STEP_SUMMARY"] = "summary.md"
    for name, expression in step.get("env", {}).items():
        match = EXPRESSION.fullmatch(expression)
        assert match is not None
        environment[name] = results[match.group(1)]
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    shell = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert shell is not None, "Real Bash is required for the CI report"
    result = subprocess.run(  # noqa: S603 - fixed Bash and the workflow script
        [shell, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return (tmp_path / "summary.md").read_text(encoding="utf-8"), result.stdout


def _assert_report(tmp_path: Path, results: dict[str, str]) -> None:
    summary, stdout = _run_report(tmp_path, results)
    ws = results["go-integration-ws-hub"]
    fp = results["go-integration-file-processor"]
    gateway = results["go-integration-gateway"]
    migration = results["db-migration-integrity"]
    assert summary == (
        "## Go integration tests (required)\n\n"
        "| Service | Result |\n|---------|--------|\n"
        f"| ws-hub | {ws} |\n| file-processor | {fp} |\n"
        f"| gateway | {gateway} |\n\n"
        "## Migration rollback integrity (required)\n\n"
        "| Job | Result |\n|-----|--------|\n"
        f"| db-migration-integrity | {migration} |\n"
    )
    assert stdout == (
        f"Required Go integration results - ws-hub: {ws}, "
        f"file-processor: {fp}, gateway: {gateway}\n"
        f"Required migration rollback integrity result - {migration}\n"
    )


def test_report_receives_each_needs_result_via_environment() -> None:
    step = _report()
    assert step["shell"] == "bash"
    assert step.get("env") == {
        name: f"${{{{ needs.{job}.result }}}}" for name, job in RESULT_ENV.items()
    }
    assert "${{" not in step["run"]


@pytest.mark.parametrize("job", RESULT_ENV.values())
@pytest.mark.parametrize("status", ["success", "failure", "cancelled", "skipped"])
def test_report_preserves_each_job_result(
    tmp_path: Path, job: str, status: str
) -> None:
    results = dict.fromkeys(RESULT_ENV.values(), "success")
    results[job] = status
    _assert_report(tmp_path, results)


def test_report_preserves_distinct_job_results(tmp_path: Path) -> None:
    results = dict(
        zip(
            RESULT_ENV.values(),
            ("success", "failure", "cancelled", "skipped"),
            strict=True,
        )
    )
    _assert_report(tmp_path, results)


@pytest.mark.parametrize("job", RESULT_ENV.values())
def test_report_does_not_evaluate_result_as_shell_code(
    tmp_path: Path, job: str
) -> None:
    results = dict.fromkeys(RESULT_ENV.values(), "success")
    results[job] = "$(printf AUD380_INJECTED)"
    _assert_report(tmp_path, results)
