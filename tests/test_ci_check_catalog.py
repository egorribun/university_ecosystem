"""Fail-closed contract tests for the machine-readable CI check catalog."""

from __future__ import annotations

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
