"""Contracts for the advisory Go mutation diagnostic boundary."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "reusable-go-tests.yml"
DIAGNOSTIC_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "go-mutation-diagnostic.yml"


def _load_workflow() -> dict[str, object]:
    loaded = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    matches = [
        step for step in steps if isinstance(step, dict) and step.get("name") == name
    ]
    assert len(matches) == 1, f"expected one step named {name!r}"
    return matches[0]


def test_go_coverage_producer_is_independent_of_advisory_mutation() -> None:
    workflow = _load_workflow()
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)

    producer = jobs["test"]
    diagnostic = jobs["mutation-diagnostic"]
    assert isinstance(producer, dict)
    assert isinstance(diagnostic, dict)

    producer_step_names = {
        str(step.get("name")) for step in producer["steps"] if isinstance(step, dict)
    }
    assert "Install go-mutesting" not in producer_step_names
    assert "Run incremental mutation tests" not in producer_step_names
    coverage_upload = _step(producer, "Upload coverage artifacts")
    assert coverage_upload["if"] == "${{ success() }}"

    assert (
        diagnostic["if"]
        == "${{ inputs.run-mutation-diagnostic && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch') }}"
    )
    assert diagnostic["continue-on-error"] is True
    assert 1 <= diagnostic["timeout-minutes"] <= 70

    initialize = _step(diagnostic, "Initialize mutation diagnostic evidence")
    assert "diagnostic-failure.txt" in initialize["run"]
    assert "none" in initialize["run"]
    step_names = [step.get("name") for step in diagnostic["steps"]]
    assert (
        step_names.index("Initialize mutation diagnostic evidence")
        < step_names.index("Install dependencies")
        < step_names.index("Install go-mutesting")
    )

    diagnostic_run = _step(diagnostic, "Run bounded Go mutation diagnostic")["run"]
    assert "timeout 1800s" in diagnostic_run
    assert "go-mutesting" in diagnostic_run
    assert "MUTATION_FAILURE_REASON" in diagnostic_run
    assert "diagnostic-only" in diagnostic_run
    # The diagnostic must leave provenance that is independently auditable from
    # the job result: source/base/workflow identities, tool/config hashes, and
    # UTC timestamps are recorded in the summary.
    initialize_run = initialize["run"]
    for provenance_field in (
        "source_head_sha",
        "base_sha",
        "base_ref",
        "workflow_ref",
        "workflow_sha",
        "tool_version",
        "config_sha256",
        "generated_at",
    ):
        assert provenance_field in initialize_run or provenance_field in diagnostic_run
    assert "CONFIG_PATHS" in initialize_run
    assert "git ls-files --error-unmatch" in initialize_run
    assert '[ -L "$config_path" ]' in initialize_run
    assert "regular checked-out file" in initialize_run
    assert "sha256sum" in diagnostic_run
    assert "target_hash" in diagnostic_run
    # Every shard outcome (including failures) must be materialized into the
    # summary with source/report hashes instead of an always-empty list.
    assert "update_summary_outcomes" in diagnostic_run
    assert "source_sha256" in diagnostic_run
    assert "report_sha256" in diagnostic_run
    assert "outcome_count" in diagnostic_run
    # Unexpected failures before an explicit fail_diagnostic call must still
    # mark the evidence failed; cleanup alone is not a fail-closed handler.
    assert "trap on_exit EXIT" in diagnostic_run
    assert "DIAGNOSTIC_FINALIZED" in diagnostic_run
    assert "diagnostic command failed before evidence finalization" in diagnostic_run

    finalize = _step(diagnostic, "Finalize diagnostic failure evidence")
    assert finalize["if"] == "always()"
    assert finalize["id"] == "finalize-diagnostic-evidence"
    assert "diagnostic-failure.txt" in finalize["run"]
    assert "mutation-diagnostic-summary.json" in finalize["run"]
    assert "status" in finalize["run"]

    diagnostic_upload = _step(diagnostic, "Upload mutation diagnostic evidence")
    assert diagnostic_upload["if"] == "always()"
    assert diagnostic_upload["with"]["if-no-files-found"] == "error"
    assert "github.sha" in diagnostic_upload["with"]["name"]
    assert "github.run_attempt" in diagnostic_upload["with"]["name"]
    assert "report.json" in diagnostic_upload["with"]["path"]
    assert "mutation-diagnostic-summary.json" in diagnostic_upload["with"]["path"]
    assert "target.txt" in diagnostic_upload["with"]["path"]
    assert "source.sha256" in diagnostic_upload["with"]["path"]


def test_go_mutation_diagnostic_is_explicitly_scheduled_or_manual() -> None:
    workflow = yaml.safe_load(DIAGNOSTIC_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    triggers = workflow.get("on")
    if triggers is None:
        # PyYAML 1.1 parses the YAML 1.2 key ``on`` as boolean ``True``.
        triggers = workflow.get(True)
    assert isinstance(triggers, dict)
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"] == [{"cron": "30 4 * * *"}]
    assert triggers["workflow_dispatch"] == {}

    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    diagnostic = jobs["diagnostic"]
    assert isinstance(diagnostic, dict)
    assert diagnostic["uses"] == "./.github/workflows/reusable-go-tests.yml"
    assert diagnostic["strategy"]["fail-fast"] is False
    matrix = diagnostic["strategy"]["matrix"]
    assert isinstance(matrix, dict)
    entries = matrix["include"]
    assert isinstance(entries, list)
    assert {entry["service-directory"] for entry in entries} == {
        "services/gateway",
        "services/file-processor",
        "services/ws-hub",
        "services/cmd/uni-cli",
        "services/pkg/spiffe",
        "services/pkg/spicedb",
    }
    assert diagnostic["with"]["run-mutation-diagnostic"] is True


def test_reusable_go_mutation_diagnostic_defaults_to_off() -> None:
    workflow = _load_workflow()
    triggers = workflow.get("on")
    if triggers is None:
        # PyYAML 1.1 parses the YAML 1.2 key ``on`` as boolean ``True``.
        triggers = workflow.get(True)
    assert isinstance(triggers, dict)
    inputs = triggers["workflow_call"]["inputs"]
    assert inputs["run-mutation-diagnostic"] == {
        "description": "Run the bounded advisory mutation diagnostic (scheduled/manual only)",
        "required": False,
        "type": "boolean",
        "default": False,
    }

    ci = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert isinstance(ci, dict)
    ci_jobs = ci.get("jobs")
    assert isinstance(ci_jobs, dict)
    go_tests = ci_jobs["go-tests"]
    assert isinstance(go_tests, dict)
    # The required PR matrix must not opt back into the expensive advisory
    # lane; only the schedule/manual workflow above may set this input true.
    assert "run-mutation-diagnostic" not in go_tests.get("with", {})


def test_quality_gate_uses_only_contract_owned_go_coverage_job() -> None:
    workflow = _load_workflow()
    ci = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert isinstance(ci, dict)
    jobs = ci["jobs"]
    assert isinstance(jobs, dict)
    assert jobs["coverage-policy-gate"]["needs"] == [
        "backend-tests",
        "frontend-tests",
        "go-tests",
        "rust-tests",
    ]
    assert "mutation-diagnostic" not in jobs["coverage-policy-gate"]["needs"]

    reusable_jobs = workflow["jobs"]
    assert isinstance(reusable_jobs, dict)
    assert reusable_jobs["test"]["name"].startswith("Test Go Service")
