"""Mutation evidence stays complete in manual and nightly workflows only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
MANUAL = WORKFLOWS / "manual-mutation-evidence.yml"
NIGHTLY = WORKFLOWS / "nightly-full-gate.yml"
BACKEND = WORKFLOWS / "reusable-full-backend-mutation.yml"


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    value = workflow.get("on", workflow.get(True, {}))
    assert isinstance(value, dict)
    return value


def test_blocking_ci_keeps_security_and_coverage_but_has_no_mutation_execution() -> (
    None
):
    jobs = _workflow(CI)["jobs"]
    finalizer = jobs["ci-success"]

    assert not any("mutation" in job_id or "stryker" in job_id for job_id in jobs)
    assert not any(
        "mutation" in job_id or "stryker" in job_id for job_id in finalizer["needs"]
    )
    assert {
        "pre-commit-security-and-types",
        "security-audit",
        "coverage-policy-gate",
    } <= set(finalizer["needs"])


def test_manual_and_nightly_mutation_lanes_preserve_full_logical_inventories() -> None:
    manual = _workflow(MANUAL)
    manual_triggers = _triggers(manual)
    assert set(manual_triggers) == {"workflow_dispatch"}
    manual_jobs = manual["jobs"]

    stats = manual_jobs["manual-mutation-stats"]
    execution = manual_jobs["manual-mutation-tests"]
    assert stats["strategy"]["matrix"]["stats_shard"] == list(range(8))
    assert stats["strategy"]["max-parallel"] == 8
    assert execution["needs"] == "manual-mutation-stats"
    assert execution["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert execution["strategy"]["max-parallel"] == 20
    assert execution["strategy"]["fail-fast"] is False
    assert any(
        step.get("name") == "Require all manual mutmut stats shards"
        for step in execution["steps"]
    )

    manual_frontend = manual_jobs["manual-frontend-mutation-shards"]
    assert manual_frontend["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert manual_frontend["needs"] == "manual-frontend-mutation-preflight"
    assert manual_jobs["manual-frontend-mutation-aggregate"]["needs"] == [
        "manual-frontend-mutation-preflight",
        "manual-frontend-mutation-shards",
    ]
    assert manual_jobs["manual-frontend-mutation-roundtrip"]["needs"] == (
        "manual-frontend-mutation-aggregate"
    )

    nightly = _workflow(NIGHTLY)
    nightly_triggers = _triggers(nightly)
    assert "schedule" in nightly_triggers
    assert "workflow_dispatch" in nightly_triggers
    nightly_jobs = nightly["jobs"]
    backend_call = nightly_jobs["mutation-tests-full"]
    assert (
        backend_call["uses"] == "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    assert "github.ref == 'refs/heads/main'" in backend_call["if"]

    backend_jobs = _workflow(BACKEND)["jobs"]
    backend_mutation = backend_jobs["mutation-tests-full"]
    assert backend_jobs["mutation-tests-full-stats"]["strategy"]["matrix"][
        "stats_shard"
    ] == list(range(8))
    assert backend_mutation["strategy"]["matrix"]["shard"] == list(range(1, 129))
    assert backend_jobs["mutation-tests-full-aggregate"]["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full",
    ]

    nightly_frontend = nightly_jobs["frontend-mutation-shards"]
    assert nightly_frontend["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert nightly_frontend["strategy"]["matrix"]["shard-index"] == list(range(64))
    assert nightly_jobs["frontend-mutation-tests-full"]["needs"] == [
        "frontend-mutation-preflight",
        "frontend-mutation-shards",
    ]
    assert nightly_jobs["frontend-mutation-roundtrip"]["needs"] == (
        "frontend-mutation-tests-full"
    )
