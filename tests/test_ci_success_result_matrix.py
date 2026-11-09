"""Execute the final CI gate against job, event, and coverage outcomes."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
RESULT_EXPRESSION = re.compile(r"\$\{\{\s*needs\.([a-z0-9-]+)\.result\s*\}\}")
EVENT_JOBS = {"codecov-upload", "live-realtime-visual"}
PRODUCERS = ("backend-tests", "frontend-tests", "go-tests", "rust-tests")


@pytest.fixture(scope="module")
def aggregate() -> tuple[list[str], dict[str, Any]]:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    job = workflow["jobs"]["ci-success"]
    step = next(
        step for step in job["steps"] if step.get("name") == "Check all jobs passed"
    )
    return job["needs"], step


def _run(
    step: dict[str, Any],
    results: dict[str, str],
    event: str = "push",
    ref: str = "refs/heads/main",
    base: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("BASH_ENV", None)
    for name, value in step["env"].items():
        match = RESULT_EXPRESSION.fullmatch(value)
        if match:
            env[name] = results[match.group(1)]
    env.update(EVENT_NAME=event, EVENT_REF=ref, BASE_REF=base)
    script = RESULT_EXPRESSION.sub(lambda match: results[match.group(1)], step["run"])
    assert "${{" not in script
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    shell = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert shell is not None, "Bash is required to execute the CI Success finalizer"
    return subprocess.run(  # noqa: S603 - fixed Bash and the workflow script
        [shell, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _success_results(needs: list[str]) -> dict[str, str]:
    results = dict.fromkeys(needs, "success")
    results["live-realtime-visual"] = "skipped"
    return results


def test_all_required_jobs_accept_success(
    aggregate: tuple[list[str], dict[str, Any]],
) -> None:
    needs, step = aggregate
    result = _run(step, _success_results(needs))
    assert result.returncode == 0
    assert result.stdout == "All required CI checks passed.\n"
    assert result.stderr == ""


@pytest.mark.parametrize("status", ["failure", "cancelled", "skipped", ""])
def test_every_required_job_rejects_other_results(
    aggregate: tuple[list[str], dict[str, Any]], status: str
) -> None:
    needs, step = aggregate
    assert EVENT_JOBS <= set(needs)
    for job in set(needs) - EVENT_JOBS:
        results = _success_results(needs)
        results[job] = status
        if job in PRODUCERS and status in {"failure", "skipped"}:
            results["coverage-policy-gate"] = "skipped"
        result = _run(step, results)
        assert result.returncode != 0, (job, status, result.stdout)
        assert f"Required CI job '{job}' concluded '{status}'" in result.stdout
        assert result.stdout.count("::error::Required CI job '") == 1
        assert result.stderr == ""


@pytest.mark.parametrize(
    ("event", "ref", "base", "codecov", "live"),
    [
        ("push", "refs/heads/main", "", "success", "skipped"),
        ("push", "refs/heads/feature", "", "skipped", "skipped"),
        ("pull_request", "refs/pull/1/merge", "main", "skipped", "success"),
        ("pull_request", "refs/pull/1/merge", "feature", "skipped", "skipped"),
        ("workflow_dispatch", "refs/heads/main", "", "skipped", "skipped"),
    ],
)
def test_event_gates_require_the_expected_result(
    aggregate: tuple[list[str], dict[str, Any]],
    event: str,
    ref: str,
    base: str,
    codecov: str,
    live: str,
) -> None:
    needs, step = aggregate
    for job, expected in (("codecov-upload", codecov), ("live-realtime-visual", live)):
        for status in ("success", "failure", "cancelled", "skipped", ""):
            results = _success_results(needs)
            results.update({"codecov-upload": codecov, "live-realtime-visual": live})
            results[job] = status
            result = _run(step, results, event, ref, base)
            assert (result.returncode == 0) is (status == expected), (job, status)
            if status != expected:
                assert (
                    f"Event-gated CI job '{job}' concluded '{status}'; expected '{expected}'"
                    in result.stdout
                )
            assert result.stderr == ""


@pytest.mark.parametrize("producer", PRODUCERS)
@pytest.mark.parametrize("producer_result", ["failure", "skipped", "cancelled"])
@pytest.mark.parametrize("coverage", ["success", "skipped"])
def test_coverage_skip_depends_on_producer_result(
    aggregate: tuple[list[str], dict[str, Any]],
    producer: str,
    producer_result: str,
    coverage: str,
) -> None:
    needs, step = aggregate
    results = _success_results(needs)
    results[producer] = producer_result
    results["coverage-policy-gate"] = coverage
    result = _run(step, results)
    expected = "skipped" if producer_result in {"failure", "skipped"} else "success"
    assert result.returncode != 0
    assert ("Required CI job 'coverage-policy-gate'" in result.stdout) is (
        coverage != expected
    )
    assert result.stderr == ""
