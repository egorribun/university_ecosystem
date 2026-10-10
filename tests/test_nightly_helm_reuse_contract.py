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
    nightly = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    nightly_jobs = nightly["jobs"]
    producer_call = nightly_jobs["nightly-helm-dependencies"]
    mutation_call = nightly_jobs["mutation-tests-full"]

    assert nightly["permissions"] == {"contents": "read"}
    assert (
        producer_call["if"]
        == "${{ github.repository == 'egorribun/university_ecosystem' && github.ref == 'refs/heads/main' }}"
    )
    assert producer_call["uses"] == "./.github/workflows/reusable-helm-dependencies.yml"
    assert producer_call["with"] == {"source_sha": "${{ github.sha }}"}
    assert mutation_call["uses"] == (
        "./.github/workflows/reusable-full-backend-mutation.yml"
    )
    assert mutation_call["with"]["helm_artifact_name"] == (
        "${{ needs.nightly-helm-dependencies.outputs.artifact_name }}"
    )

    reusable = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "reusable-helm-dependencies.yml").read_text(
            encoding="utf-8"
        )
    )
    assert reusable["permissions"] == {"contents": "read"}
    workflow_call = reusable.get("on", reusable.get(True))["workflow_call"]
    assert workflow_call["inputs"]["source_sha"]["required"] is True
    assert workflow_call["outputs"]["artifact_name"]["value"] == (
        "${{ jobs.produce.outputs.artifact_name }}"
    )
    producer = reusable["jobs"]["produce"]
    verify = _step(producer, "Verify Helm producer caller and source provenance")
    assert "JOB_CONTEXT_JSON" in verify["env"]
    assert verify["env"]["JOB_CONTEXT_JSON"] == "${{ toJSON(job) }}"
    assert verify["env"]["GITHUB_WORKFLOW_REF_VALUE"] == "${{ github.workflow_ref }}"
    assert verify["env"]["GITHUB_WORKFLOW_SHA_VALUE"] == "${{ github.workflow_sha }}"
    producer_stage = _step(producer, "Stage verified Helm dependency artifact")["run"]
    assert "helm_dependency_artifact.py create" in producer_stage
    assert '--commit-sha "$COMMIT_SHA"' in producer_stage
    assert '--run-attempt "$RUN_ATTEMPT"' in producer_stage
    upload = _step(producer, "Upload verified Helm dependency artifact")
    assert upload["with"]["name"] == "${{ steps.verify.outputs.artifact_name }}"
    assert upload["with"]["if-no-files-found"] == "error"

    full = yaml.safe_load(
        (
            ROOT / ".github" / "workflows" / "reusable-full-backend-mutation.yml"
        ).read_text(encoding="utf-8")
    )
    jobs = full["jobs"]
    assert jobs["mutation-tests-full-stats"]["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-generation-base",
    ]
    assert jobs["mutation-tests-full-plan"]["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-stats",
    ]
    assert jobs["mutation-tests-full"]["needs"] == [
        "verify-full-mutation-provenance",
        "mutation-tests-full-plan",
    ]
    for job_name in (
        "mutation-tests-full-stats",
        "mutation-tests-full-plan",
        "mutation-tests-full",
    ):
        job = jobs[job_name]
        assert job["permissions"] == {"contents": "read", "actions": "read"}
        selector = _step(job, "Select same-run Helm dependency artifact")
        selector_run = selector["run"]
        assert "select_same_run_artifact_cli.py" in selector_run
        assert (
            '--artifact-prefix "${{ needs.verify-full-mutation-provenance.outputs.helm_artifact_prefix }}"'
            in selector_run
        )
        assert "--attempt-policy current-or-earlier" in selector_run
        download = _step(job, "Download same-run Helm dependency artifact")
        assert download["with"]["artifact-ids"] == (
            "${{ steps.select_nightly_helm.outputs.artifact_id }}"
        )
        restore_index = job["steps"].index(
            _step(job, "Restore verified Helm dependency archives")
        )
        helm_index = job["steps"].index(_step(job, "Resolve Helm chart dependencies"))
        assert restore_index < helm_index
        restore = _step(job, "Restore verified Helm dependency archives")["run"]
        assert "helm_dependency_artifact.py restore" in restore
        assert "--producer-attempt-policy at-or-before" in restore
        assert '"$GITHUB_WORKSPACE" charts/university-ecosystem/charts' in restore
        helm = _step(job, "Resolve Helm chart dependencies")["run"]
        assert "--skip-refresh" in helm
        assert "helm dependency build" not in helm
