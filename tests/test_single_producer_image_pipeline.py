from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PRODUCER = WORKFLOWS / "build-release-images.yml"
DEPLOY = WORKFLOWS / "deploy.yml"
RELEASE = WORKFLOWS / "release.yml"

EXPECTED_IMAGES = {
    "backend",
    "caddy",
    "frontend",
    "ws-hub",
    "gateway",
    "file-processor",
}


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dispatch_inputs(workflow: dict) -> dict:
    triggers = workflow.get("on") or workflow.get(True)
    return triggers["workflow_dispatch"]["inputs"]


def _run_text(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def test_exact_six_images_have_one_canonical_main_only_producer() -> None:
    producer = _workflow(PRODUCER)
    inputs = _dispatch_inputs(producer)
    assert inputs["release-sha"]["required"] is True
    assert inputs["quality-run-id"]["required"] is True
    assert producer["concurrency"] == {
        "group": "canonical-release-images-main",
        "cancel-in-progress": False,
    }
    assert producer["jobs"]["certify"]["if"] == "${{ github.ref == 'refs/heads/main' }}"

    build = producer["jobs"]["build"]
    assert build["needs"] == ["certify"]
    matrix = {
        entry["image_name"]: entry for entry in build["strategy"]["matrix"]["include"]
    }
    assert set(matrix) == EXPECTED_IMAGES
    assert matrix["caddy"] == {
        "image_name": "caddy",
        "file": "services/caddy/Dockerfile",
        "context": "services/caddy",
    }
    assert build["with"]["canonical_frontend"] == (
        "${{ matrix.image_name == 'frontend' }}"
    )
    reusable = _workflow(WORKFLOWS / "reusable-build-and-sign.yml")
    build_args = str(reusable["jobs"]["build"]["steps"])
    for required in (
        "VITE_APP_RELEASE={0}",
        "VITE_ENABLE_WEB_VITALS=true",
        "VITE_CWV_TRUSTED_RUM=true",
        "VITE_WEB_VITALS_ENDPOINT=/api/v1/cwv",
    ):
        assert required in build_args

    aggregate = producer["jobs"]["aggregate-image-provenance"]
    assert aggregate["needs"] == ["certify", "build"]
    aggregate_text = _run_text(aggregate)
    assert "aggregate_release_image_evidence.py" in aggregate_text
    assert '--build-run-id "$BUILD_RUN_ID"' in aggregate_text
    assert '--build-run-attempt "$BUILD_RUN_ATTEMPT"' in aggregate_text
    assert '--quality-run-id "$QUALITY_RUN_ID"' in aggregate_text
    assert "release-image-manifest.json.sha256" in aggregate_text


def test_deploy_and_release_only_consume_the_canonical_manifest() -> None:
    producer = _workflow(PRODUCER)
    deploy = _workflow(DEPLOY)
    release = _workflow(RELEASE)

    assert "reusable-build-and-sign.yml" in str(producer)
    for workflow in (deploy, release):
        inputs = _dispatch_inputs(workflow)
        assert inputs["image-build-run-id"]["required"] is True
        assert inputs["image-build-run-attempt"]["required"] is True
        assert "reusable-build-and-sign.yml" not in str(workflow)
        assert not any(name.startswith("build-") for name in workflow["jobs"])
        assert "build" not in workflow["jobs"]
        assert all(
            job.get("permissions", {}).get("packages") != "write"
            for job in workflow["jobs"].values()
        )

    assert "cwv-certified-frontend-image-digest" not in _dispatch_inputs(deploy)
    resolver = deploy["jobs"]["resolve-images"]
    assert resolver["permissions"] == {
        "actions": "read",
        "attestations": "read",
        "contents": "read",
        "packages": "read",
    }
    resolver_text = _run_text(resolver)
    for required in (
        ".github/workflows/build-release-images.yml",
        "workflow_dispatch",
        "release-image-provenance-$RELEASE_SHA-attempt-$BUILD_RUN_ATTEMPT",
        "verify_release_image_manifest.py",
        "--signer-workflow",
        "--source-digest",
        "--source-ref",
    ):
        assert required in resolver_text

    release_resolver = release["jobs"]["resolve-images"]
    assert release_resolver["permissions"]["packages"] == "read"
    assert _run_text(release_resolver).count("verify_release_image_manifest.py") == 1
    assert release["jobs"]["publish"]["needs"] == ["resolve-images"]


def test_staging_receipt_and_cwv_certificate_bind_the_canonical_manifest() -> None:
    deploy = _workflow(DEPLOY)
    deployment = deploy["jobs"]["deploy"]
    assert "resolve-images" in deployment["needs"]
    deploy_text = _run_text(deployment)
    for output in (
        "backend-digest",
        "frontend-digest",
        "ws-hub-digest",
        "gateway-digest",
        "file-processor-digest",
        "caddy-digest",
        "manifest-sha256",
    ):
        assert f"needs.resolve-images.outputs.{output}" in str(deployment)
    assert "image_manifest_sha256" in deploy_text
    assert "image_build_run_id" in deploy_text
    assert "image_build_run_attempt" in deploy_text

    cwv = _workflow(WORKFLOWS / "cwv-field-certification.yml")
    cwv_inputs = _dispatch_inputs(cwv)
    assert cwv_inputs["image-build-run-id"]["required"] is True
    assert cwv_inputs["image-build-run-attempt"]["required"] is True
    cwv_text = _run_text(cwv["jobs"]["certify"])
    assert "image_manifest_sha256" in cwv_text
    assert "image_build_run_id" in cwv_text
    assert "image_build_run_attempt" in cwv_text
