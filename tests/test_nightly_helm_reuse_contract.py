from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "nightly-full-gate.yml"


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    steps = cast(list[dict[str, Any]], job["steps"])
    return next(step for step in steps if step.get("name") == name)


def test_nightly_helm_archives_have_one_producer_and_hash_bound_consumers() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    producer = jobs["nightly-helm-dependencies"]

    assert workflow["permissions"] == {"contents": "read"}
    assert producer["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert (
        "nightly-helm-dependencies"
        in _step(producer, "Upload verified nightly Helm dependency artifact")["with"][
            "name"
        ]
    )
    producer_stage = _step(producer, "Stage verified Helm dependency artifact")["run"]
    assert "helm_dependency_artifact.py create" in producer_stage
    assert '--commit-sha "$COMMIT_SHA"' in producer_stage
    assert '--run-attempt "$RUN_ATTEMPT"' in producer_stage

    for job_name in ("mutation-tests-full-stats", "mutation-tests-full"):
        job = jobs[job_name]
        assert job["permissions"] == {"contents": "read", "actions": "read"}
        assert "nightly-helm-dependencies" in (
            job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
        )
        selector = _step(job, "Select same-run Helm dependency artifact")
        selector_run = selector["run"]
        assert "select_same_run_artifact_cli.py" in selector_run
        assert '--artifact-prefix "nightly-helm-dependencies-"' in selector_run
        assert "--attempt-policy current-or-earlier" in selector_run
        download = _step(job, "Download nightly Helm dependency artifact")
        assert download["with"]["artifact-ids"] == (
            "${{ steps.select_nightly_helm.outputs.artifact_id }}"
        )
        restore_index = job["steps"].index(
            _step(job, "Restore verified Helm dependency archives")
        )
        helm_index = job["steps"].index(_step(job, "Resolve Helm chart dependencies"))
        assert restore_index < helm_index
        restore = _step(job, "Restore verified Helm dependency archives")["run"]
        assert "helm_dependency_artifact.py validate" in restore
        assert "--producer-attempt-policy at-or-before" in restore
        assert "cp --no-preserve=mode,ownership" in restore
        helm = _step(job, "Resolve Helm chart dependencies")["run"]
        assert "--skip-refresh" in helm
        assert "helm dependency build" not in helm
