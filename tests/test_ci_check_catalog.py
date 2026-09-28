"""Fail-closed contract tests for the machine-readable CI check catalog."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from scripts.quality.validate_ci_check_catalog import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    _artifact_inventory,
    _job_expressions,
    _needs_references,
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


def _source_repo(tmp_path: Path, value: dict[str, object]) -> Path:
    workflow_dir = tmp_path / ".github" / "workflows"
    shutil.copytree(ROOT / ".github" / "workflows", workflow_dir)
    runbook_paths = {value["default_runbook"]}
    runbook_paths.update(profile["runbook"] for profile in value["profiles"].values())
    runbook_paths.update(entry["runbook"] for entry in value["external_checks"])
    runbook_paths.update(entry["runbook"] for entry in value["expansions"])
    for runbook in runbook_paths:
        target = tmp_path / runbook
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / runbook, target)
    return workflow_dir


def _validate_changed_ci(tmp_path: Path, value: dict[str, object]) -> list[str]:
    return validate_catalog(
        value,
        repository_root=tmp_path,
        workflow_directory=tmp_path / ".github" / "workflows",
        schema=_schema(),
    )


def test_catalog_is_a_complete_current_workflow_inventory() -> None:
    assert _errors(_catalog()) == []


def test_every_catalog_job_declares_exact_source_needs() -> None:
    value = _catalog()
    for entry in value["workflows"]:
        workflow = yaml.safe_load((ROOT / entry["path"]).read_text(encoding="utf-8"))
        for job_id, job in entry["jobs"].items():
            source_needs = workflow["jobs"][job_id].get("needs", [])
            expected = [source_needs] if isinstance(source_needs, str) else source_needs
            assert job["needs"] == expected, f"{entry['path']}::{job_id}"


def test_needs_reference_scan_ignores_literals_and_aggregate_access() -> None:
    assert (
        list(_needs_references("contains('needs.ghost', 'needs') && needs.*.result"))
        == []
    )
    assert list(_job_expressions({"steps": [{"run": "echo needs.ghost"}]})) == []


@pytest.mark.parametrize(
    "reference",
    [
        "needs . no-such-job.result",
        "needs.\n no-such-job.result",
        "needs \n . \n no-such-job.result",
        "needs \n [ 'no-such-job' ].result",
        "(needs).no-such-job.result",
        "(needs)['no-such-job'].result",
        "(( needs )).no-such-job.result",
        "NEEDS.no-such-job.result",
    ],
)
def test_needs_reference_scan_resolves_whitespace_around_access(reference: str) -> None:
    assert list(_needs_references(reference)) == ["no-such-job"]


@pytest.mark.parametrize(
    "reference",
    [
        "needs /* comment */ . no-such-job.result",
        "needs // comment\n . no-such-job.result",
    ],
)
def test_unsupported_comment_between_needs_tokens_fails_closed(reference: str) -> None:
    assert list(_needs_references(reference)) == [None]


def test_bare_needs_context_fails_closed() -> None:
    assert list(_needs_references("toJSON(needs)")) == [None]


def test_source_job_needs_drift_is_rejected(tmp_path: Path) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)

    ci_path = workflow_dir / "ci.yml"
    original = ci_path.read_text(encoding="utf-8")
    old = (
        "  stryker-shards:\n"
        "    name: Frontend mutation shard ${{ matrix.shard-index }}/64"
    )
    assert original.count(old) == 1
    source = original.replace(
        "      - pre-commit-security-and-types\n"
        "    if: ${{ github.event_name == 'pull_request' && needs.stryker-preflight.result",
        "      - pre-commit-security-and-types\n"
        "      - ci-diagnostic\n"
        "    if: ${{ github.event_name == 'pull_request' && needs.stryker-preflight.result",
        1,
    )
    assert source != original
    original_yaml = yaml.safe_load(original)
    changed_yaml = yaml.safe_load(source)
    original_needs = original_yaml["jobs"]["stryker-shards"]["needs"]
    assert changed_yaml["jobs"]["stryker-shards"]["needs"] == [
        *original_needs,
        "ci-diagnostic",
    ]
    changed_yaml["jobs"]["stryker-shards"]["needs"] = original_needs
    assert changed_yaml == original_yaml
    ci_path.write_text(source, encoding="utf-8")

    errors = _validate_changed_ci(tmp_path, value)
    assert any("needs differs from workflow" in error for error in errors), errors


@pytest.mark.parametrize(
    ("new_needs", "expected_error"),
    [
        (["stryker-preflight", "coverage-policy-gate", "no-such-job"], "unknown job"),
        (["stryker-preflight", "stryker-preflight"], "duplicate dependency"),
        (["stryker-preflight", "stryker-shards"], "self-dependency"),
    ],
)
def test_invalid_source_needs_edges_fail_closed(
    tmp_path: Path, new_needs: list[str], expected_error: str
) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    source["jobs"]["stryker-shards"]["needs"] = new_needs
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    ci_catalog = next(
        item for item in value["workflows"] if item["path"].endswith("ci.yml")
    )
    ci_catalog["jobs"]["stryker-shards"]["needs"] = new_needs

    errors = _validate_changed_ci(tmp_path, value)
    assert any(expected_error in error for error in errors), errors


@pytest.mark.parametrize(
    ("reference", "expected_error"),
    [
        ("needs.no-such-job.result", "undeclared needs reference"),
        ("needs['no-such-job'].result", "undeclared needs reference"),
        ('needs["no-such-job"].result', "undeclared needs reference"),
        ("needs[github.event.inputs.job].result", "dynamic needs reference"),
        ("(needs).no-such-job.result", "undeclared needs reference"),
        ("(needs)['no-such-job'].result", "undeclared needs reference"),
        ("NEEDS.no-such-job.result", "undeclared needs reference"),
    ],
)
def test_undeclared_or_dynamic_needs_expression_fails_closed(
    tmp_path: Path, reference: str, expected_error: str
) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    job = source["jobs"]["stryker-shards"]
    assert job["if"].endswith(" }}")
    job["if"] = job["if"][:-3] + f" && {reference} == 'success'" + " }}"
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    ci_catalog = next(
        item for item in value["workflows"] if item["path"].endswith("ci.yml")
    )
    ci_catalog["jobs"]["stryker-shards"]["guard"] = job["if"]

    errors = _validate_changed_ci(tmp_path, value)
    assert any(expected_error in error for error in errors), errors


@pytest.mark.parametrize("literal", ["}}", "a''}}b"])
def test_quoted_expression_delimiter_does_not_hide_needs_reference(
    tmp_path: Path, literal: str
) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    job = source["jobs"]["stryker-shards"]
    assert job["if"].endswith(" }}")
    job["if"] = (
        job["if"][:-3]
        + f" && contains('{literal}', 'x') && needs.no-such-job.result == 'success'"
        + " }}"
    )
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    ci_catalog = next(
        item for item in value["workflows"] if item["path"].endswith("ci.yml")
    )
    ci_catalog["jobs"]["stryker-shards"]["guard"] = job["if"]

    errors = _validate_changed_ci(tmp_path, value)
    assert any("undeclared needs reference" in error for error in errors), errors


def test_nested_needs_key_expression_is_validated(tmp_path: Path) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    source["jobs"]["stryker-shards"]["steps"][0]["with"]["needs"] = (
        "${{ needs.no-such-job.result }}"
    )
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")

    errors = _validate_changed_ci(tmp_path, value)
    assert any("undeclared needs reference" in error for error in errors), errors


def test_unterminated_actions_expression_fails_closed(tmp_path: Path) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    job = source["jobs"]["stryker-shards"]
    job["if"] = "${{ github.event_name == 'pull_request'"
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    ci_catalog = next(
        item for item in value["workflows"] if item["path"].endswith("ci.yml")
    )
    ci_catalog["jobs"]["stryker-shards"]["guard"] = job["if"]

    errors = _validate_changed_ci(tmp_path, value)
    assert any("unterminated Actions expression" in error for error in errors), errors


def test_whitespace_around_needs_dot_cannot_bypass_source_validation(
    tmp_path: Path,
) -> None:
    value = _catalog()
    workflow_dir = _source_repo(tmp_path, value)
    ci_path = workflow_dir / "ci.yml"
    source = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    job = source["jobs"]["stryker-shards"]
    assert job["if"].endswith(" }}")
    job["if"] = job["if"][:-3] + " && needs . no-such-job.result == 'success' }}"
    ci_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    ci_catalog = next(
        item for item in value["workflows"] if item["path"].endswith("ci.yml")
    )
    ci_catalog["jobs"]["stryker-shards"]["guard"] = job["if"]

    errors = _validate_changed_ci(tmp_path, value)
    assert any("undeclared needs reference" in error for error in errors), errors


def test_backend_integration_artifact_catalog_includes_mailpit_report() -> None:
    workflows = _catalog()["workflows"]
    backend = next(
        item
        for item in workflows
        if item["path"] == ".github/workflows/reusable-backend-tests.yml"
    )
    artifact = backend["jobs"]["integration-tests"]["artifacts"][0]
    assert artifact["path_pattern"] == "pytest-report.xml\nmfa-mailpit-report.xml\n"


def test_catalog_declares_matrix_governance_for_every_source_matrix() -> None:
    """Every matrix has a source-bound cap or an explicit owner justification."""

    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    catalog_by_path = {entry["path"]: entry for entry in workflows}

    for workflow_path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
        source = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        relative_path = workflow_path.relative_to(ROOT).as_posix()
        catalog_workflow = catalog_by_path[relative_path]
        catalog_jobs = catalog_workflow["jobs"]
        for job_id, source_job in source["jobs"].items():
            strategy = source_job.get("strategy")
            if not isinstance(strategy, dict) or "matrix" not in strategy:
                continue

            governance = catalog_jobs[job_id].get("matrix_governance")
            assert isinstance(governance, dict), (
                f"missing governance: {relative_path}::{job_id}"
            )
            if "max-parallel" in strategy:
                assert governance == {"max_parallel": strategy["max-parallel"]}
            else:
                justification = governance.get("unbounded_justification")
                assert isinstance(justification, dict)
                assert set(justification) == {"owner", "event_profile", "rationale"}
                assert all(
                    isinstance(justification[field], str)
                    and justification[field].strip()
                    for field in ("owner", "event_profile", "rationale")
                )


def test_matrix_governance_is_source_bound_and_fail_closed() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    ci = next(item for item in workflows if item["path"].endswith("ci.yml"))
    ci_jobs = ci["jobs"]
    bounded = ci_jobs["stryker-shards"]["matrix_governance"]
    bounded["max_parallel"] = 7
    unbounded = next(item for item in workflows if item["path"].endswith("codeql.yml"))[
        "jobs"
    ]["analyze"]["matrix_governance"]
    unbounded["max_parallel"] = 1

    errors = _errors(value)
    assert any("matrix max_parallel differs from workflow" in error for error in errors)
    assert any(
        "source has no max-parallel; use unbounded_justification" in error
        for error in errors
    )


def test_matrix_governance_is_required_only_for_matrix_jobs() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    ci = next(item for item in workflows if item["path"].endswith("ci.yml"))
    ci["jobs"]["ci-diagnostic"]["matrix_governance"] = {
        "max_parallel": 1,
    }
    ci["jobs"]["e2e-tests"].pop("matrix_governance")

    errors = _errors(value)
    assert any(
        "matrix_governance is present for a non-matrix job" in error for error in errors
    )
    assert any("matrix_governance is missing" in error for error in errors)


def test_catalog_cli_reports_current_inventory() -> None:
    assert (
        main(["--catalog", str(DEFAULT_CATALOG), "--schema", str(DEFAULT_SCHEMA)]) == 0
    )


def test_attempt_bound_sha_artifact_uses_attempt_provenance() -> None:
    artifacts = _artifact_inventory(
        {
            "steps": [
                {
                    "uses": "actions/upload-artifact@v7",
                    "with": {
                        "name": (
                            "quality-evidence-${{ github.sha }}-attempt-"
                            "${{ github.run_attempt }}"
                        ),
                        "path": "artifacts/coverage/quality-manifest.json",
                    },
                }
            ]
        }
    )

    assert artifacts == [
        {
            "name_pattern": (
                "quality-evidence-${{ github.sha }}-attempt-${{ github.run_attempt }}"
            ),
            "path_pattern": "artifacts/coverage/quality-manifest.json",
            "required": False,
            "provenance": "run_id_attempt",
        }
    ]


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


def test_catalog_declares_base_branch_policy_integrity_gate() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    workflow = next(
        item
        for item in workflows
        if item["path"] == ".github/workflows/security-policy-integrity.yml"
    )
    assert workflow["events"] == [
        {
            "event": "pull_request_target",
            "guard": (
                '{"branches":["main"],"types":'
                '["opened","synchronize","reopened","ready_for_review","edited"]}'
            ),
        }
    ]
    job = workflow["jobs"]["security-policy-integrity"]
    assert job["profile"] == "required-pr-target-main"
    assert value["profiles"]["required-pr-target-main"]["required_events"] == [
        "pull_request_target_main"
    ]
    assert _errors(value) == []


def test_sonarcloud_advisory_classification_matches_workflow_contract() -> None:
    value = _catalog()
    workflows = value["workflows"]
    assert isinstance(workflows, list)
    workflow = next(
        item for item in workflows if item["path"] == ".github/workflows/sonar.yml"
    )
    job = workflow["jobs"]["sonarcloud"]
    assert job["profile"] == "advisory"
    assert "required_events" not in job
    assert _errors(value) == []


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
