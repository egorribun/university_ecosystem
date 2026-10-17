"""Stryker mutation evidence is complete, provenance-bound, and non-blocking."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
NIGHTLY = WORKFLOWS / "nightly-full-gate.yml"
MANUAL = WORKFLOWS / "manual-mutation-evidence.yml"


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("name") == name
    )


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    value = workflow.get("on", workflow.get(True, {}))
    assert isinstance(value, dict)
    return value


def test_full_stryker_inventory_is_nightly_not_a_blocking_ci_dependency() -> None:
    ci_jobs = _workflow(CI)["jobs"]
    assert not any("mutation" in job_id or "stryker" in job_id for job_id in ci_jobs)
    assert not any(
        "mutation" in need or "stryker" in need
        for need in ci_jobs["ci-success"]["needs"]
    )

    nightly = _workflow(NIGHTLY)
    triggers = _triggers(nightly)
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers
    jobs = nightly["jobs"]
    manual_guard = jobs["verify-default-branch-dispatch"]
    assert manual_guard["if"] == "${{ github.event_name == 'workflow_dispatch' }}"
    assert (
        "refs/heads/main"
        in _step(manual_guard, "Require protected default branch")["run"]
    )

    preflight = jobs["frontend-mutation-preflight"]
    assert preflight["if"] == "${{ github.ref == 'refs/heads/main' }}"
    upload_preflight = _step(preflight, "Upload immutable Stryker preflight")
    assert upload_preflight["with"]["name"] == (
        "frontend-mutation-preflight-${{ github.run_id }}-"
        "${{ github.run_attempt }}-${{ github.sha }}"
    )

    shards = jobs["frontend-mutation-shards"]
    assert shards["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert shards["needs"] == "frontend-mutation-preflight"
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert shards["strategy"]["max-parallel"] == 8

    selector = _step(shards, "Select immutable same-run Stryker preflight candidate")
    selector_run = selector["run"]
    for required in (
        '--run-id "${{ github.run_id }}"',
        '--consumer-run-attempt "${{ github.run_attempt }}"',
        '--commit-sha "${{ github.sha }}"',
        '--run-head-sha "${{ github.sha }}"',
        '--workflow-path ".github/workflows/nightly-full-gate.yml"',
        '--artifact-prefix "frontend-mutation-preflight-"',
        "--attempt-policy current-or-earlier",
    ):
        assert required in selector_run
    assert selector["env"] == {"GH_TOKEN": "${{ github.token }}"}


def test_nightly_stryker_aggregate_checks_all_shards_and_round_trips_bound_evidence() -> (
    None
):
    jobs = _workflow(NIGHTLY)["jobs"]
    aggregate = jobs["frontend-mutation-tests-full"]
    assert aggregate["needs"] == [
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
    ]
    assert "always()" in aggregate["if"]
    assert "!cancelled()" in aggregate["if"]
    assert "refs/heads/main" in aggregate["if"]

    require_shards = _step(
        aggregate, "Require same-run nightly Stryker shard candidates"
    )
    assert "set -euo pipefail" in require_shards["run"]
    assert 'test ! -L "$root"' in require_shards["run"]
    assert "type l" in require_shards["run"]
    verify = _step(aggregate, "Aggregate and verify nightly frontend mutation evidence")
    assert "npm run test:mutation" in verify["run"]
    assert "npm run test:mutation:verify" in verify["run"]

    upload = _step(aggregate, "Upload validated nightly frontend mutation evidence")
    assert upload["if"] == "${{ success() }}"
    assert upload["with"]["name"] == (
        "frontend-mutation-validated-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert upload["with"]["if-no-files-found"] == "error"

    roundtrip = jobs["frontend-mutation-roundtrip"]
    assert roundtrip["needs"] == "frontend-mutation-tests-full"
    selector = _step(
        roundtrip, "Select immutable same-run validated Stryker evidence candidate"
    )
    assert '--run-id "${{ github.run_id }}"' in selector["run"]
    assert '--consumer-run-attempt "${{ github.run_attempt }}"' in selector["run"]
    assert '--commit-sha "${{ github.sha }}"' in selector["run"]
    reverify = _step(
        roundtrip, "Re-verify downloaded nightly frontend mutation evidence"
    )
    assert reverify["run"] == "npm run test:mutation:verify"


def test_manual_stryker_keeps_its_independent_64_shard_evidence_chain() -> None:
    manual = _workflow(MANUAL)
    assert set(_triggers(manual)) == {"workflow_dispatch"}
    jobs = manual["jobs"]
    shards = jobs["manual-frontend-mutation-shards"]
    assert shards["needs"] == "manual-frontend-mutation-preflight"
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["matrix"]["shard-index"] == list(range(64))

    aggregate = jobs["manual-frontend-mutation-aggregate"]
    assert aggregate["needs"] == [
        "manual-frontend-mutation-preflight",
        "manual-frontend-mutation-shards",
    ]
    assert "always()" in aggregate["if"]
    assert "!cancelled()" in aggregate["if"]
    upload = _step(aggregate, "Upload validated manual frontend mutation evidence")
    assert upload["if"] == "${{ success() }}"
    assert "run_attempt" in upload["with"]["name"]
    assert jobs["manual-frontend-mutation-roundtrip"]["needs"] == (
        "manual-frontend-mutation-aggregate"
    )
