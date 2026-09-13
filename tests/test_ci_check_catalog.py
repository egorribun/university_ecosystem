"""Fail-closed contract tests for the machine-readable CI check catalog."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.quality.validate_ci_check_catalog import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    _read_json,
    main,
    validate_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


def _catalog() -> dict[str, object]:
    return json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))


def _schema() -> dict[str, object]:
    return json.loads(DEFAULT_SCHEMA.read_text(encoding="utf-8"))


def _errors(value: dict[str, object]) -> list[str]:
    return validate_catalog(value, repository_root=ROOT, schema=_schema())


def test_catalog_is_a_complete_current_workflow_inventory() -> None:
    assert _errors(_catalog()) == []


def test_catalog_cli_reports_current_inventory() -> None:
    assert (
        main(["--catalog", str(DEFAULT_CATALOG), "--schema", str(DEFAULT_SCHEMA)]) == 0
    )


def test_workflow_and_job_additions_or_removals_fail_closed() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    first = workflows[0]
    assert isinstance(first, dict)
    jobs = first["jobs"]
    assert isinstance(jobs, dict)
    jobs.pop(next(iter(jobs)))
    workflows.pop()

    errors = _errors(value)
    assert any("job inventory mismatch" in error for error in errors)
    assert any("workflow inventory mismatch" in error for error in errors)


def test_changed_event_guard_and_check_name_are_detected() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    workflow = next(item for item in workflows if item["path"].endswith("ci.yml"))
    event = workflow["events"][0]
    event["guard"] = "tampered"
    job = workflow["jobs"]["ci-success"]
    job["check_name_template"] = "tampered"

    errors = _errors(value)
    assert any("events[0].guard is stale" in error for error in errors)
    assert any("check_name_template is stale" in error for error in errors)


def test_timeout_duration_and_required_policy_are_source_bound() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    workflow = next(item for item in workflows if item["path"].endswith("ci.yml"))
    job = workflow["jobs"]["ci-diagnostic"]
    job["expected_timeout_minutes"] = 4
    job["expected_duration_seconds"] = 1
    job["required_events"] = []

    errors = _errors(value)
    assert any("timeout differs from workflow" in error for error in errors)
    assert any("duration must cover timeout budget" in error for error in errors)
    assert any("required job has no required_events" in error for error in errors)


def test_retry_like_source_cannot_be_hidden_as_no_retry() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    target = next(
        (
            job
            for workflow in workflows
            for job in workflow["jobs"].values()
            if job["retry_policy"]["mode"] == "review-required"
        ),
        None,
    )
    assert target is not None
    target["retry_policy"] = {
        "mode": "none",
        "first_failure_preserved": True,
        "classifier": "not_applicable",
        "review_required": False,
    }

    errors = _errors(value)
    assert any(
        "retry behavior is present but policy is declared none" in error
        for error in errors
    )


def test_artifact_and_runbook_metadata_are_mandatory() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    target = next(
        job
        for workflow in workflows
        for job in workflow["jobs"].values()
        if job["artifacts"]
    )
    target["artifacts"] = []
    target["runbook"] = "docs/testing/does-not-exist.md"

    errors = _errors(value)
    assert any("artifact metadata does not match" in error for error in errors)
    assert any("runbook does not exist" in error for error in errors)


def test_schema_rejects_unknown_profile_fields() -> None:
    value = _catalog()
    profiles = value["profiles"]
    assert isinstance(profiles, dict)
    profile = profiles[next(iter(profiles))]
    assert isinstance(profile, dict)
    profile["unexpected"] = True

    errors = _errors(value)
    assert any("schema:" in error and "unexpected" in error for error in errors)


def test_strict_json_loader_rejects_duplicate_and_non_finite_values(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    try:
        _read_json(duplicate)
    except ValueError as exc:
        assert "duplicate JSON key" in str(exc)
    else:
        raise AssertionError("duplicate JSON key was accepted")

    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"a": NaN}', encoding="utf-8")
    try:
        _read_json(non_finite)
    except ValueError as exc:
        assert "non-finite JSON number" in str(exc)
    else:
        raise AssertionError("non-finite JSON number was accepted")


def test_cli_fails_closed_for_invalid_catalog(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert main(["--catalog", str(invalid), "--schema", str(DEFAULT_SCHEMA)]) == 1


def test_catalog_declares_external_provider_contexts() -> None:
    value = _catalog()
    checks = value["external_checks"]
    assert isinstance(checks, list)
    by_context = {entry["context"]: entry for entry in checks}
    assert set(by_context) == {"CodeQL", "Checkov", "spectral", "zizmor"}
    expected_sources = {
        "CodeQL": ".github/workflows/codeql.yml",
        "Checkov": ".github/workflows/checkov.yml",
        "spectral": ".github/workflows/contract-validation.yml",
        "zizmor": ".github/workflows/zizmor.yml",
    }
    for context, entry in by_context.items():
        assert entry["provider"] == "github-advanced-security", context
        assert entry["integration_id"] == 57789, context
        assert entry["profile"] == "external-required-pr", context
        assert entry["classification"] == "required", context
        assert entry["externally_owned"] is True, context
        assert entry["owner"] == "@github-advanced-security", context
        assert entry["runbook"] == "docs/testing/ci-check-catalog-runbook.md", context
        assert expected_sources[context] in entry["source_reference"], context


def test_catalog_declares_protected_reusable_and_matrix_expansions() -> None:
    value = _catalog()
    expansions = value["expansions"]
    assert isinstance(expansions, list)
    by_id = {entry["id"]: entry for entry in expansions}
    expected = {
        "backend-tests-units",
        "frontend-tests-protected",
        "e2e-tests-chromium",
        "go-tests-protected",
        "security-audit-protected",
        "codeql-languages",
        "rust-fuzz-command",
        "rust-fuzz-additional",
    }
    assert set(by_id) == expected
    for entry in expansions:
        assert entry["profile"] == "required-pr-main", entry["id"]
        assert entry["classification"] == "required", entry["id"]
        assert entry["owner"] == "@egorribun", entry["id"]
        assert entry["runbook"] == "docs/testing/ci-check-catalog-runbook.md", entry[
            "id"
        ]
        assert entry["declared_contexts"], entry["id"]
        assert len(entry["declared_contexts"]) == len(
            set(entry["declared_contexts"])
        ), entry["id"]
        assert entry["source_reference"], entry["id"]
    assert by_id["backend-tests-units"]["reusable_workflow_path"].endswith(
        "reusable-backend-tests.yml"
    )
    assert by_id["frontend-tests-protected"]["reusable_workflow_path"].endswith(
        "reusable-frontend-tests.yml"
    )
    assert by_id["e2e-tests-chromium"]["reusable_workflow_path"].endswith(
        "reusable-e2e-tests.yml"
    )
    assert by_id["go-tests-protected"]["reusable_workflow_path"].endswith(
        "reusable-go-tests.yml"
    )
    assert by_id["security-audit-protected"]["reusable_workflow_path"].endswith(
        "reusable-security-audit.yml"
    )
    assert len(by_id["codeql-languages"]["declared_contexts"]) == 5
    assert len(by_id["rust-fuzz-command"]["declared_contexts"]) == 1
    assert len(by_id["rust-fuzz-additional"]["declared_contexts"]) == 2


def test_duplicate_external_context_is_rejected() -> None:
    value = _catalog()
    checks = value["external_checks"]
    assert isinstance(checks, list)
    checks.append(copy.deepcopy(checks[0]))

    errors = _errors(value)
    assert any("duplicate provider context" in error for error in errors)


def test_duplicate_expanded_context_is_rejected() -> None:
    value = _catalog()
    expansions = value["expansions"]
    assert isinstance(expansions, list)
    duplicate = copy.deepcopy(expansions[0])
    duplicate["id"] = "duplicate-expansion"
    expansions.append(duplicate)

    errors = _errors(value)
    assert any("duplicate expanded context" in error for error in errors)


def test_expansion_reference_profile_owner_and_runbook_are_fail_closed() -> None:
    value = _catalog()
    expansions = value["expansions"]
    assert isinstance(expansions, list)
    entry = expansions[0]
    entry["caller_job_id"] = "does-not-exist"
    entry["profile"] = "does-not-exist"
    entry["owner"] = ""
    entry["runbook"] = "docs/testing/does-not-exist.md"

    errors = _errors(value)
    assert any("caller job does not exist" in error for error in errors)
    assert any("unknown profile" in error for error in errors)
    assert any("owner must be non-empty" in error for error in errors)
    assert any("runbook does not exist" in error for error in errors)


def test_expansion_rejects_malformed_reference_path() -> None:
    value = _catalog()
    expansions = value["expansions"]
    assert isinstance(expansions, list)
    entry = expansions[0]
    entry["caller_workflow_path"] = "../.github/workflows/ci.yml"

    errors = _errors(value)
    assert any(
        "workflow path must be a relative POSIX path" in error or "schema:" in error
        for error in errors
    )


def test_expansion_rejects_unknown_reusable_job() -> None:
    value = _catalog()
    expansions = value["expansions"]
    assert isinstance(expansions, list)
    entry = expansions[0]
    entry["reusable_job_ids"] = ["does-not-exist"]

    errors = _errors(value)
    assert any("reusable job does not exist" in error for error in errors)
