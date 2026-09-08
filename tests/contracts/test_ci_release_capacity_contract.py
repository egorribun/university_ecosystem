"""Fail-closed contracts for the CI release finalizer and runner budget.

These tests intentionally inspect the workflow source instead of a single
GitHub run.  A green run cannot prove that a cancelled/missing dependency is
handled correctly or that the logical mutation inventory was not reduced.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
SBOM = WORKFLOWS / "sbom.yml"
POLICY = ROOT / "quality" / "release-required-checks.json"


def _workflow(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _check_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    for step in job.get("steps", []):
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def test_ci_success_is_an_always_on_fail_closed_finalizer() -> None:
    jobs = _workflow(CI)["jobs"]
    finalizer = jobs["ci-success"]

    assert finalizer["if"] == "${{ always() }}"
    required_needs = set(finalizer["needs"])
    for producer in (
        "e2e-tests-cross-browser",
        "chaos-tests",
        "db-migration-integrity",
    ):
        assert producer in required_needs

    gate = _check_step(finalizer, "Check all jobs passed")["run"]
    for producer in (
        "e2e-tests-cross-browser",
        "chaos-tests",
        "db-migration-integrity",
    ):
        assert f'"{producer}|${{{{ needs.{producer}.result }}}}"' in gate
    assert 'if [[ "$result" != "$expected_result" ]]' in gate
    assert '"$result" == "success" || "$result" == "skipped"' not in gate

    summary = _check_step(finalizer, "Report integration and extended quality results")[
        "run"
    ]
    assert "advisory" not in summary.lower()
    assert "release-blocking" in summary.lower()


def test_cross_browser_lane_is_blocking_without_changing_the_matrix() -> None:
    jobs = _workflow(CI)["jobs"]
    cross_browser = jobs["e2e-tests-cross-browser"]
    assert cross_browser["strategy"]["matrix"]["browser"] == [
        "firefox",
        "webkit",
        "mobile-webkit",
    ]
    assert cross_browser["with"].get("advisory", False) is False


def test_mutation_budget_preserves_complete_logical_inventories() -> None:
    jobs = _workflow(CI)["jobs"]
    stryker = jobs["stryker-shards"]
    mutmut = jobs["mutation-tests-incremental"]
    stats = jobs["mutation-tests-stats"]

    assert stryker["strategy"]["max-parallel"] == 6
    assert mutmut["strategy"]["max-parallel"] == 10
    assert stats["strategy"]["max-parallel"] == 8
    assert (
        stryker["strategy"]["max-parallel"] + mutmut["strategy"]["max-parallel"] <= 16
    )
    assert stryker["strategy"]["fail-fast"] is False
    assert mutmut["strategy"]["fail-fast"] is False
    assert stryker["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert "expected-shards 128" in "\n".join(
        str(step.get("run", ""))
        for step in jobs["mutation-tests-universe"]["steps"]
        if isinstance(step, dict)
    )
    assert "target-groups 64" in "\n".join(
        str(step.get("run", ""))
        for step in jobs["mutation-tests-universe"]["steps"]
        if isinstance(step, dict)
    )


def test_mutmut_artifact_producers_use_explicit_read_only_permissions() -> None:
    jobs = _workflow(CI)["jobs"]
    expected_permissions = {"contents": "read", "actions": "read"}

    for job_name in ("mutation-tests-stats", "mutation-tests-universe"):
        assert jobs[job_name]["permissions"] == expected_permissions


def test_stryker_preflight_does_not_wait_for_frontend_lighthouse() -> None:
    jobs = _workflow(CI)["jobs"]
    preflight = jobs["stryker-preflight"]
    assert preflight["needs"] == ["pre-commit-check"]
    assert "needs.frontend-tests.result" not in str(preflight.get("if", ""))
    assert jobs["stryker-shards"]["needs"] == [
        "stryker-preflight",
        "coverage-policy-gate",
        "pre-commit-security-and-types",
    ]
    reusable_text = (WORKFLOWS / "reusable-frontend-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "run-lighthouse" in reusable_text
    assert "lighthouse-shards:" in reusable_text
    assert "lighthouse:" in reusable_text


def test_stryker_fanout_waits_for_security_type_qualification() -> None:
    """A red security/type qualification must not allocate 64 Stryker runners."""

    jobs = _workflow(CI)["jobs"]
    shards = jobs["stryker-shards"]
    assert shards["needs"] == [
        "stryker-preflight",
        "coverage-policy-gate",
        "pre-commit-security-and-types",
    ]
    assert "needs.pre-commit-security-and-types.result == 'success'" in shards["if"]

    aggregate = jobs["stryker-aggregate"]
    assert "pre-commit-security-and-types" in aggregate["needs"]
    assert "needs.pre-commit-security-and-types.result == 'success'" in aggregate["if"]

    finalizer = _check_step(jobs["ci-success"], "Check all jobs passed")["run"]
    assert '"$PRE_COMMIT_SECURITY_RESULT" == "success"' in finalizer


def test_pr_vulnerability_gate_has_a_read_only_producer() -> None:
    workflow = _workflow(SBOM)
    trigger = workflow.get("on", workflow.get(True))
    assert isinstance(trigger, dict)
    assert "pull_request" in trigger

    jobs = workflow["jobs"]
    assert jobs["vuln-gate"]["if"] == (
        "${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}"
    )
    pr_gate = jobs["vuln-gate-pr"]
    assert pr_gate["name"] == "Vulnerability gate (CRITICAL/HIGH)"
    assert pr_gate["if"] == "${{ github.event_name == 'pull_request' }}"
    assert pr_gate["permissions"] == {"contents": "read"}
    assert all(
        key not in pr_gate["permissions"]
        for key in ("id-token", "attestations", "security-events", "actions")
    )
    checkout = pr_gate["steps"][0]
    assert checkout["with"]["persist-credentials"] is False
    install = next(
        step
        for step in pr_gate["steps"]
        if step.get("name") == "Install pinned Python audit tools"
    )
    assert "--no-install-project" in install["run"]
    pr_steps = "\n".join(
        str(step.get("run", "")) for step in pr_gate["steps"] if isinstance(step, dict)
    )
    for scanner in ("osv_batch_audit.py", "govulncheck", "cargo audit"):
        assert scanner in pr_steps

    for job_name in ("sbom-go", "vuln-gate", "vuln-gate-pr"):
        setup_go = next(
            step for step in jobs[job_name]["steps"] if step.get("name") == "Set up Go"
        )
        assert setup_go["with"]["go-version"] == "1.26.6"
        assert "go-version-file" not in setup_go["with"]

    for job_name in ("sbom-python", "sbom-go", "sbom-rust"):
        assert jobs[job_name]["if"] == (
            "${{ github.ref == 'refs/heads/main' && "
            "github.event_name != 'pull_request' }}"
        )
    assert "id-token" not in pr_steps


def test_privileged_sbom_jobs_are_bound_to_the_protected_main_ref() -> None:
    """Manual dispatch must not promote a non-main checkout into a signer."""

    workflow = _workflow(SBOM)
    expected_guard = (
        "${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}"
    )
    for job_name in ("sbom-python", "sbom-go", "sbom-rust", "vuln-gate"):
        assert workflow["jobs"][job_name]["if"] == expected_guard


def test_release_policy_declares_a_pr_event_without_removing_push_policy() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert set(policy["events"]) >= {"push_main", "pull_request_main"}
    push_names = {
        item["name"] for item in policy["events"]["push_main"]["required_checks"]
    }
    pr_checks = policy["events"]["pull_request_main"]["required_checks"]
    pr_names = {item["name"] for item in pr_checks}
    assert "CI Success" in pr_names
    assert "Vulnerability gate (CRITICAL/HIGH)" in pr_names
    assert "Trusted Codecov Upload" not in pr_names
    assert push_names - {"Trusted Codecov Upload"} <= pr_names
