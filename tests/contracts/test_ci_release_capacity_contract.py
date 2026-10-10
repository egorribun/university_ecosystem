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
FRONTEND = WORKFLOWS / "reusable-frontend-tests.yml"
NIGHTLY = WORKFLOWS / "nightly-full-gate.yml"
LIVE_ACCEPTANCE = WORKFLOWS / "live-acceptance.yml"
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
    gate = _check_step(finalizer, "Check all jobs passed")["run"]

    # Q1/Q4 evidence is outside blocking CI. The finalizer must still fail
    # closed over every remaining direct dependency, including security and
    # coverage qualification, rather than accepting an unexpected skip.
    deferred = {
        "mutation-tests-full",
        "mutation-tests-full-stats",
        "mutation-tests-full-universe",
        "mutation-tests-incremental",
        "stryker-preflight",
        "stryker-shards",
        "stryker-aggregate",
        "e2e-tests-cross-browser",
        "schemathesis-api-tests-shard",
        "schemathesis-api-tests",
        "chaos-tests",
        "chaos-loadtest-orchestrator",
        "load-and-chaos",
        "performance-gate",
    }
    assert not (deferred & required_needs)
    assert not (deferred & jobs.keys())
    assert {
        "pre-commit-security-and-types",
        "security-audit",
        "coverage-policy-gate",
    } <= required_needs

    for producer in required_needs - {"coverage-policy-gate", "codecov-upload"}:
        assert f'"{producer}|${{{{ needs.{producer}.result }}}}"' in gate
    assert '"coverage-policy-gate|$COVERAGE_RESULT"' in gate
    assert "coverage_expected_result=success" in gate
    assert "performance_expected_result" not in gate
    assert 'if [[ "$result" != "$expected_result" ]]' in gate
    assert '"$result" == "success" || "$result" == "skipped"' not in gate
    assert 'assert_event_result "codecov-upload"' in gate

    summary = _check_step(
        finalizer, "Report integration and migration quality results"
    )["run"]
    assert "advisory" not in summary.lower()
    assert "required" in summary.lower()


def test_full_browser_matrix_is_nightly_and_live_core_smoke_remains_on_pr() -> None:
    nightly_jobs = _workflow(NIGHTLY)["jobs"]
    browser_matrix = nightly_jobs["browser-matrix"]
    assert browser_matrix["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert browser_matrix["strategy"]["fail-fast"] is False
    assert browser_matrix["strategy"]["max-parallel"] == 2
    browser_entries = browser_matrix["strategy"]["matrix"]["include"]
    assert sum(entry["browser"] == "chromium" for entry in browser_entries) == 4
    assert {entry["browser"] for entry in browser_entries} == {
        "chromium",
        "firefox",
        "webkit",
        "mobile-webkit",
    }

    live = _workflow(LIVE_ACCEPTANCE)
    trigger = live.get("on", live.get(True))
    assert "pull_request" in trigger
    live_job = live["jobs"]["live-acceptance"]
    assert "github.event_name == 'pull_request'" in live_job["if"]
    assert "'smoke'" in live_job["env"]["LIVE_E2E_MODE"]
    start = _check_step(live_job, "Start the owned live stand")
    assert "--stack core" in start["run"]
    assert "live-acceptance" not in _workflow(CI)["jobs"]["ci-success"]["needs"]


def test_mutation_budget_preserves_complete_logical_inventories() -> None:
    ci_jobs = _workflow(CI)["jobs"]
    nightly_jobs = _workflow(NIGHTLY)["jobs"]
    reusable_jobs = _workflow(WORKFLOWS / "reusable-full-backend-mutation.yml")["jobs"]

    assert not any("mutation" in name or "stryker" in name for name in ci_jobs)
    assert nightly_jobs["mutation-tests-full"]["uses"] == (
        "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    assert nightly_jobs["mutation-tests-full"]["if"] == (
        "${{ github.repository == 'egorribun/university_ecosystem' && "
        "github.ref == 'refs/heads/main' }}"
    )

    stryker = nightly_jobs["frontend-mutation-shards"]
    assert stryker["strategy"]["max-parallel"] == 8
    assert stryker["strategy"]["fail-fast"] is False
    assert stryker["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert "--num-shards 128" in "\n".join(
        str(step.get("run", ""))
        for step in reusable_jobs["mutation-tests-full-plan"]["steps"]
        if isinstance(step, dict)
    )
    backend_mutation = reusable_jobs["mutation-tests-full"]
    assert backend_mutation["strategy"]["max-parallel"] == 8
    assert backend_mutation["strategy"]["fail-fast"] is False
    assert backend_mutation["strategy"]["matrix"]["shard"] == list(range(1, 129))


def test_high_fanout_lanes_are_bounded_without_reducing_matrix_cardinality() -> None:
    """Bound runner contention while keeping every required matrix entry."""

    ci_jobs = _workflow(CI)["jobs"]
    expected_pr_caps = {
        "backend-tests": 2,
        "go-tests": 2,
    }
    expected_cardinality = {
        "backend-tests": 4,
        "go-tests": 7,
    }
    for job_name, cap in expected_pr_caps.items():
        strategy = ci_jobs[job_name]["strategy"]
        assert strategy["fail-fast"] is False
        assert strategy["max-parallel"] == cap
        matrix = strategy["matrix"]
        entries = (
            matrix["include"]
            if "include" in matrix
            else next(value for value in matrix.values() if isinstance(value, list))
        )
        assert len(entries) == expected_cardinality[job_name]

    frontend_jobs = _workflow(FRONTEND)["jobs"]
    assert frontend_jobs["unit-tests-shard"]["strategy"]["max-parallel"] == 2
    assert frontend_jobs["unit-tests-shard"]["strategy"]["matrix"]["shard"] == [
        1,
        2,
        3,
        4,
    ]
    assert frontend_jobs["lighthouse-shards"]["strategy"]["max-parallel"] == 2
    assert len(frontend_jobs["lighthouse-shards"]["strategy"]["matrix"]["include"]) == 4

    nightly_jobs = _workflow(NIGHTLY)["jobs"]
    full_backend_call = nightly_jobs["mutation-tests-full"]
    assert full_backend_call["uses"] == (
        "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    reusable_backend_jobs = _workflow(WORKFLOWS / "reusable-full-backend-mutation.yml")[
        "jobs"
    ]
    reusable_caps = {
        "mutation-tests-full-stats": 4,
        "mutation-tests-full": 8,
    }
    for job_name, cap in {
        **reusable_caps,
        "frontend-mutation-shards": 8,
        "backend-full": 2,
        "backend-integration": 2,
        "go-integration": 2,
        "browser-matrix": 2,
        "schemathesis-api-tests-shard": 4,
    }.items():
        jobs = reusable_backend_jobs if job_name in reusable_caps else nightly_jobs
        strategy = jobs[job_name]["strategy"]
        assert strategy["fail-fast"] is False
        assert strategy["max-parallel"] == cap

    stats_matrix = reusable_backend_jobs["mutation-tests-full-stats"]["strategy"][
        "matrix"
    ]
    execution_matrix = reusable_backend_jobs["mutation-tests-full"]["strategy"][
        "matrix"
    ]
    assert stats_matrix["stats_shard"] == list(range(8))
    assert execution_matrix["shard"] == list(range(1, 129))
    assert nightly_jobs["frontend-mutation-shards"]["strategy"]["max-parallel"] == 8
    assert nightly_jobs["frontend-mutation-shards"]["strategy"]["matrix"][
        "shard-index"
    ] == list(range(64))
    assert len(nightly_jobs["browser-matrix"]["strategy"]["matrix"]["include"]) == 7
    assert nightly_jobs["schemathesis-api-tests-shard"]["strategy"]["matrix"][
        "shard"
    ] == list(range(8))

    ci_call = ci_jobs["frontend-tests"]["with"]
    assert ci_call["run-lighthouse"] is False
    assert "performance-gate" not in ci_jobs


def test_manual_and_active_scan_workflows_serialize_duplicate_dispatches() -> None:
    """Do not spend runner slots on duplicate long-lived evidence runs."""

    for filename, expected_group in (
        ("dast.yml", "dast-main"),
        (
            "manual-performance-evidence.yml",
            "manual-performance-evidence-${{ github.ref }}",
        ),
        ("quality-promotion-check.yml", "quality-promotion-main"),
    ):
        workflow = _workflow(WORKFLOWS / filename)
        concurrency = workflow.get("concurrency")
        assert concurrency == {
            "group": expected_group,
            "cancel-in-progress": False,
        }


def test_required_pr_and_advisory_nightly_have_independent_admission_contract() -> None:
    """PR and nightly queues must not evict one another's pending run."""

    ci_concurrency = _workflow(CI)["concurrency"]
    assert ci_concurrency == {
        "group": (
            "${{ github.event_name == 'pull_request'\n"
            "  && format('quality-heavy-pr-{0}', github.event.pull_request.number)\n"
            "  || format('ci-matrix-{0}', github.ref) }}"
        ),
        "cancel-in-progress": True,
    }

    nightly_concurrency = _workflow(NIGHTLY)["concurrency"]
    assert nightly_concurrency == {
        "group": "quality-heavy-nightly-${{ github.repository }}",
        "cancel-in-progress": False,
    }

    # GitHub keeps only one running and one pending run per concurrency group;
    # separate groups prevent an advisory nightly dispatch from replacing a
    # pending required PR run (or vice versa).
    assert ci_concurrency["group"] != nightly_concurrency["group"]
    for path in WORKFLOWS.glob("*.yml"):
        workflow = _workflow(path)
        concurrency = workflow.get("concurrency")
        if path in {CI, NIGHTLY}:
            continue
        serialized = str(concurrency)
        assert "quality-heavy-pr-" not in serialized
        assert "quality-heavy-nightly-" not in serialized


def test_mutmut_artifact_producers_use_explicit_read_only_permissions() -> None:
    jobs = _workflow(WORKFLOWS / "reusable-full-backend-mutation.yml")["jobs"]
    expected_permissions = {"contents": "read", "actions": "read"}

    for job_name in ("mutation-tests-full-stats", "mutation-tests-full"):
        assert jobs[job_name]["permissions"] == expected_permissions


def test_stryker_preflight_and_all_shards_remain_nightly_evidence() -> None:
    jobs = _workflow(NIGHTLY)["jobs"]
    preflight = jobs["frontend-mutation-preflight"]
    assert preflight["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert preflight["env"]["STRYKER_SHARD_COUNT"] == "64"
    shards = jobs["frontend-mutation-shards"]
    assert shards["needs"] == "frontend-mutation-preflight"
    assert shards["strategy"]["matrix"]["shard-index"] == list(range(64))
    aggregate = jobs["frontend-mutation-tests-full"]
    assert set(aggregate["needs"]) == {
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
    }
    assert "always()" in aggregate["if"]
    assert "!cancelled()" in aggregate["if"]
    assert (
        jobs["frontend-mutation-roundtrip"]["needs"] == "frontend-mutation-tests-full"
    )

    reusable_text = (WORKFLOWS / "reusable-frontend-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "run-lighthouse" in reusable_text
    assert "lighthouse-shards:" in reusable_text
    assert "lighthouse:" in reusable_text


def test_security_and_type_qualification_remain_blocking_after_mutation_migration() -> (
    None
):
    ci_jobs = _workflow(CI)["jobs"]
    assert "pre-commit-security-and-types" in ci_jobs["ci-success"]["needs"]
    assert "security-audit" in ci_jobs["ci-success"]["needs"]

    finalizer = _check_step(ci_jobs["ci-success"], "Check all jobs passed")["run"]
    assert (
        '"pre-commit-security-and-types|${{ needs.pre-commit-security-and-types.result }}"'
        in finalizer
    )
    assert '"security-audit|${{ needs.security-audit.result }}"' in finalizer
    assert not any(
        "mutation" in need or "stryker" in need
        for need in ci_jobs["ci-success"]["needs"]
    )


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
        assert setup_go["with"]["go-version"] == "1.26.9"
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


def test_base_branch_policy_uses_the_pull_request_target_event_alias() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    target_event = policy["events"]["pull_request_target_main"]
    assert target_event["github_event"] == "pull_request_target"
    assert target_event["github_ref"] == "refs/heads/main"
    target_checks = target_event["required_checks"]
    assert [check["name"] for check in target_checks] == ["Security Policy Integrity"]

    pull_request_names = {
        check["name"]
        for check in policy["events"]["pull_request_main"]["required_checks"]
    }
    assert "Security Policy Integrity" not in pull_request_names
