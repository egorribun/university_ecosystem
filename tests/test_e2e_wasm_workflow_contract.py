"""Fail-closed contracts for the shared E2E WebAssembly build artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI_PATH = WORKFLOWS / "ci.yml"
NIGHTLY_PATH = WORKFLOWS / "nightly-full-gate.yml"
E2E_PATH = WORKFLOWS / "reusable-e2e-tests.yml"
PRODUCER_PATH = WORKFLOWS / "reusable-e2e-wasm-build.yml"


def _load(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), path
    return loaded


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    value = workflow.get("on", workflow.get(True, {}))
    assert isinstance(value, dict), value
    return value


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    for step in job.get("steps", []):
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def test_shared_e2e_wasm_producer_is_immutable_and_fail_closed() -> None:
    workflow = _load(PRODUCER_PATH)
    call = _triggers(workflow)["workflow_call"]
    assert call["outputs"]["artifact_id"]["value"] == (
        "${{ jobs.build.outputs.artifact_id }}"
    )
    assert call["outputs"]["artifact_name"]["value"] == (
        "${{ jobs.build.outputs.artifact_name }}"
    )
    assert call["outputs"]["artifact_digest"]["value"] == (
        "${{ jobs.build.outputs.artifact_digest }}"
    )

    jobs = workflow["jobs"]
    assert set(jobs) == {"build"}
    build = jobs["build"]
    assert build["runs-on"] == "ubuntu-24.04"
    assert build["timeout-minutes"] == 15
    assert build["permissions"] == {"contents": "read"}
    assert "needs" not in build
    assert build["outputs"]["artifact_id"] == "${{ steps.upload.outputs.artifact-id }}"
    assert (
        build["outputs"]["artifact_name"]
        == "${{ steps.publish.outputs.artifact_name }}"
    )
    assert build["outputs"]["artifact_digest"] == (
        "${{ steps.upload.outputs.artifact-digest }}"
    )

    checkout = next(
        step for step in build["steps"] if "actions/checkout@" in step.get("uses", "")
    )
    assert checkout["with"]["persist-credentials"] is False

    publish = _step(build, "Write immutable WASM provenance")
    publish_run = str(publish["run"])
    for required in (
        "git rev-parse HEAD",
        "WASM_PROVENANCE.json",
        "WASM_INVENTORY.json",
    ):
        assert required in publish_run
    assert set(
        (
            "EXPECTED_SHA",
            "PR_HEAD_SHA",
            "WORKFLOW_REF",
            "WORKFLOW_SHA",
            "RUN_ID",
            "RUN_ATTEMPT",
        )
    ) <= set(publish["env"])

    build_step = _step(build, "Build immutable WASM modules")
    build_run = str(build_step["run"])
    assert build_run.count("wasm-pack build") == 2
    assert "crypto_pid=$!" in build_run
    assert "sanitizer_pid=$!" in build_run
    assert 'wait "$crypto_pid"' in build_run
    assert 'wait "$sanitizer_pid"' in build_run
    assert "for attempt in 1 2 3" in build_run
    assert "node scripts/verify-wasm-artifacts.mjs" in build_run

    upload = _step(build, "Upload immutable E2E WASM modules")
    assert upload["with"] == {
        "name": "${{ steps.publish.outputs.artifact_name }}",
        "path": (
            "frontend/rust-crypto/pkg\n"
            "frontend/wasm-sanitizer/pkg\n"
            "frontend/WASM_PROVENANCE.json\n"
            "frontend/WASM_INVENTORY.json\n"
        ),
        "if-no-files-found": "error",
        "overwrite": False,
        "retention-days": 1,
        "compression-level": 0,
        "include-hidden-files": True,
    }


def test_e2e_consumer_accepts_all_or_none_artifact_inputs() -> None:
    workflow = _load(E2E_PATH)
    inputs = _triggers(workflow)["workflow_call"]["inputs"]
    for name in ("wasm-artifact-id", "wasm-artifact-name", "wasm-artifact-digest"):
        assert inputs[name]["type"] == "string"
        assert inputs[name]["required"] is False
        assert inputs[name]["default"] == ""

    job = workflow["jobs"]["e2e"]
    env = job["env"]
    assert env["SKIP_WASM_BUILD"] == "1"
    assert "wasm-artifact-id" in str(job["steps"])

    download = _step(job, "Download immutable E2E WASM modules")
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"]["artifact-ids"] == "${{ inputs.wasm-artifact-id }}"
    assert download["with"]["path"] == "frontend"

    validate = _step(job, "Verify immutable E2E WASM provenance")
    contract = _step(job, "Validate E2E WASM artifact input contract")
    assert "all three" in str(contract["run"])
    validate_run = str(validate["run"])
    for required in (
        "WASM_PROVENANCE.json",
        "WASM_INVENTORY.json",
        "verify-wasm-artifacts.mjs",
    ):
        assert required in validate_run
    assert set(("EXPECTED_SHA", "EXPECTED_RUN_ID", "EXPECTED_RUN_ATTEMPT")) <= set(
        validate["env"]
    )

    fallback = _step(job, "Build WASM modules")
    assert "inputs.wasm-artifact-id == ''" in str(fallback["if"])
    assert "for attempt in 1 2 3" in str(fallback["run"])


def test_ci_e2e_matrix_depends_on_shared_producer_not_frontend_suite() -> None:
    jobs = _load(CI_PATH)["jobs"]
    producer = jobs["e2e-wasm-build"]
    assert producer["uses"] == "./.github/workflows/reusable-e2e-wasm-build.yml"
    assert "needs" not in producer

    for job_name in ("e2e-tests", "e2e-tests-cross-browser"):
        caller = jobs[job_name]
        assert set(caller["needs"]) == {"pre-commit-check", "e2e-wasm-build"}
        with_values = caller["with"]
        assert with_values["wasm-artifact-id"] == (
            "${{ needs.e2e-wasm-build.outputs.artifact_id }}"
        )
        assert with_values["wasm-artifact-name"] == (
            "${{ needs.e2e-wasm-build.outputs.artifact_name }}"
        )
        assert with_values["wasm-artifact-digest"] == (
            "${{ needs.e2e-wasm-build.outputs.artifact_digest }}"
        )

    assert "frontend-tests" not in producer.get("needs", [])


def test_nightly_browser_matrix_uses_shared_producer() -> None:
    jobs = _load(NIGHTLY_PATH)["jobs"]
    producer = jobs["e2e-wasm-build"]
    assert producer["uses"] == "./.github/workflows/reusable-e2e-wasm-build.yml"
    assert "needs" not in producer

    browser = jobs["browser-matrix"]
    assert browser["needs"] == "e2e-wasm-build"
    assert browser["with"]["wasm-artifact-id"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_id }}"
    )
    assert browser["with"]["wasm-artifact-name"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_name }}"
    )
    assert browser["with"]["wasm-artifact-digest"] == (
        "${{ needs.e2e-wasm-build.outputs.artifact_digest }}"
    )
    assert "e2e-wasm-build" in jobs["notify-failure"]["needs"]
