from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
BACKEND_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
)


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML 5/6 parses the YAML 1.1 key ``on`` as boolean True."""

    value = workflow.get("on", workflow.get(True))
    assert isinstance(value, dict)
    return value


def test_quality_policy_gate_is_properly_wired_in_ci() -> None:
    assert CI_WORKFLOW_PATH.exists()

    with open(CI_WORKFLOW_PATH, encoding="utf-8") as file:
        workflow = yaml.safe_load(file)

    jobs = workflow.get("jobs", {})

    # We expect a job named 'coverage-policy-gate' or similar.
    # Let's search for a job that runs both validate_quality_contract.py and normalize_coverage_reports.py.
    policy_job_name = None
    policy_job = None

    for job_name, job_config in jobs.items():
        if job_name == "ci-success":
            continue

        steps = job_config.get("steps", [])
        has_validator = False
        has_normalizer = False

        for step in steps:
            run_cmd = step.get("run", "")
            if "validate_quality_contract.py" in run_cmd:
                has_validator = True
            if "normalize_coverage_reports.py" in run_cmd:
                has_normalizer = True

        if has_validator and has_normalizer:
            policy_job_name = job_name
            policy_job = job_config
            break

    assert policy_job_name is not None, (
        "Could not find a CI job that runs both the contract validator and coverage normalizer"
    )

    # Assert no continue-on-error at the job level
    assert policy_job.get("continue-on-error") is not True, (
        f"Job {policy_job_name} must not have continue-on-error enabled"
    )

    # Assert steps do not have continue-on-error
    for step in policy_job.get("steps", []):
        assert step.get("continue-on-error") is not True, (
            f"Steps in {policy_job_name} must not have continue-on-error enabled"
        )

    # Assert included in the needs of ci-success job
    ci_success = jobs.get("ci-success")
    assert ci_success is not None, "ci-success job is missing"

    needs = ci_success.get("needs", [])
    assert policy_job_name in needs, (
        f"{policy_job_name} must be in the needs list of ci-success"
    )

    # Assert included in the results array of ci-success step
    steps = ci_success.get("steps", [])
    assert len(steps) > 0
    run_script = steps[0].get("run", "")
    expected_result_check = f"${{{{ needs.{policy_job_name}.result }}}}"
    assert expected_result_check in run_script, (
        f"ci-success must assert the result of {policy_job_name}"
    )

    # Assert quality-manifest.json is uploaded as an artifact
    has_upload = False
    for step in policy_job.get("steps", []):
        uses = step.get("uses", "")
        if "upload-artifact" in uses:
            path = step.get("with", {}).get("path", "")
            if "quality-manifest.json" in path or "quality-manifest.json" in str(path):
                has_upload = True

    assert has_upload, (
        f"Job {policy_job_name} must upload quality-manifest.json as an artifact"
    )

    # ── Verify quality-inventory-check job ──
    inventory_job = jobs.get("quality-inventory-check")
    assert inventory_job is not None, "quality-inventory-check job is missing in ci.yml"

    # Assert no continue-on-error
    assert inventory_job.get("continue-on-error") is not True, (
        "quality-inventory-check must not have continue-on-error enabled"
    )
    for step in inventory_job.get("steps", []):
        assert step.get("continue-on-error") is not True, (
            "Steps in quality-inventory-check must not have continue-on-error enabled"
        )

    # Assert in needs of ci-success
    assert "quality-inventory-check" in needs, (
        "quality-inventory-check must be in the needs list of ci-success"
    )

    # Assert checked in results array
    expected_inventory_check = "${{ needs.quality-inventory-check.result }}"
    assert expected_inventory_check in run_script, (
        "ci-success must assert the result of quality-inventory-check"
    )


def test_backend_ci_uses_historical_duration_shards_and_aggregates_coverage() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    backend_job = ci_workflow["jobs"]["backend-tests"]
    matrix = backend_job["strategy"]["matrix"]["include"]
    assert [entry["shard"] for entry in matrix] == [0, 1, 2, 3]
    assert all(entry["python-version"] == "3.14" for entry in matrix)
    assert backend_job["with"]["shard-id"] == "${{ matrix.shard }}"
    assert backend_job["with"]["num-shards"] == 4

    policy_job = ci_workflow["jobs"]["coverage-policy-gate"]
    policy_text = "\n".join(
        step.get("run", "") for step in policy_job["steps"] if isinstance(step, dict)
    )
    download_steps = [
        step
        for step in policy_job["steps"]
        if step.get("uses", "").startswith("actions/download-artifact")
    ]
    python_download = next(
        step
        for step in download_steps
        if "backend-coverage-data" in str(step.get("with", {}))
    )
    assert python_download["with"]["merge-multiple"] is True
    assert "coverage combine" in policy_text
    assert "--python-xml coverage.xml" in policy_text
    assert "--rust-report rust-crypto=artifacts/coverage/rust/rust-crypto/llvm.json" in policy_text

    backend_workflow = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    inputs = _workflow_triggers(backend_workflow)["workflow_call"]["inputs"]
    assert inputs["shard-id"]["default"] == -1
    assert inputs["num-shards"]["default"] == 1
    run_step = next(
        step
        for step in backend_workflow["jobs"]["unit-tests"]["steps"]
        if step.get("name") == "Run pytest"
    )
    assert "--shard-id=${{ inputs.shard-id }}" in run_step["run"]
    assert "--num-shards=${{ inputs.num-shards }}" in run_step["run"]


def test_weekly_duration_refresh_is_a_reviewable_bot_pr() -> None:
    workflow_path = (
        REPOSITORY_ROOT / ".github" / "workflows" / "weekly-test-durations.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert _workflow_triggers(workflow)["schedule"][0]["cron"] == "0 4 * * 1"
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["permissions"]["pull-requests"] == "write"
    step_text = "\n".join(
        step.get("run", "")
        for step in workflow["jobs"]["refresh"]["steps"]
        if isinstance(step, dict)
    )
    assert "update_test_durations.py" in step_text
    assert "gh pr create" in step_text


def test_nightly_full_gate_contains_the_long_running_quality_suites() -> None:
    workflow_path = REPOSITORY_ROOT / ".github" / "workflows" / "nightly-full-gate.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)
    assert triggers["schedule"][0]["cron"] == "0 1 * * *"
    jobs = workflow["jobs"]
    assert {
        "mutation-tests-full",
        "frontend-mutation-tests-full",
        "backend-full",
        "go-integration",
        "browser-matrix",
        "load-and-chaos",
        "kyverno-test",
        "miri",
        "notify-failure",
    } <= set(jobs)
    mutation_steps = jobs["mutation-tests-full"]["steps"]
    export_step = next(
        step
        for step in mutation_steps
        if step.get("name") == "Export and gate mutation statistics"
    )
    assert "export-cicd-stats" in export_step["run"]
    assert jobs["go-integration"]["strategy"]["matrix"]["service-directory"] == [
        "services/gateway",
        "services/ws-hub",
        "services/file-processor",
    ]
    assert jobs["browser-matrix"]["strategy"]["matrix"]["browser"] == [
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    ]
    assert "always()" in jobs["notify-failure"]["if"]
    assert "frontend-mutation-tests-full" in jobs["notify-failure"]["needs"]
    assert "issues" in workflow["permissions"]


def test_incremental_mutation_gate_is_blocking_and_fails_on_timeout() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = ci_workflow["jobs"]
    mutation_job = jobs["mutation-tests-incremental"]
    assert mutation_job["timeout-minutes"] == 35
    assert "mutation-tests-incremental" in jobs["ci-success"]["needs"]
    mutation_text = "\n".join(
        step.get("run", "")
        for step in mutation_job["steps"]
        if isinstance(step, dict)
    )
    assert "exceeded its 25-minute budget" in mutation_text
    assert "Skipping score verification" not in mutation_text
    assert "needs.mutation-tests-incremental.result" in jobs["ci-success"]["steps"][0]["run"]


def test_frontend_mutation_gate_is_blocking_and_reproducible() -> None:
    ci_workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = ci_workflow["jobs"]
    mutation_job = jobs["stryker-incremental"]
    assert mutation_job["if"] == "${{ github.event_name == 'pull_request' }}"
    assert "stryker-incremental" in jobs["ci-success"]["needs"]
    result_check = jobs["ci-success"]["steps"][0]["run"]
    assert "needs.stryker-incremental.result" in result_check

    frontend_workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml").read_text(
            encoding="utf-8"
        )
    )
    unit_steps = frontend_workflow["jobs"]["unit-tests"]["steps"]
    diff_step = next(
        step for step in unit_steps if step.get("name") == "Check differential frontend coverage"
    )
    assert "--fail-under=80" in diff_step["run"]
    codecov_step = next(
        step for step in unit_steps if step.get("name") == "Upload frontend coverage to Codecov"
    )
    assert codecov_step["with"]["flags"] == "frontend"
