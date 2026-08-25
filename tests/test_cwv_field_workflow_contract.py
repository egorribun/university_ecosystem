from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
CERTIFICATION_WORKFLOW = ROOT / ".github" / "workflows" / "cwv-field-certification.yml"


def _load(path: Path) -> dict[str, object]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _triggers(workflow: dict[str, object]) -> dict[str, object]:
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job["steps"]
    assert isinstance(steps, list)
    step = next(item for item in steps if item.get("name") == name)
    assert isinstance(step, dict)
    return step


def test_staging_deploy_emits_sha_bound_metadata_after_verification() -> None:
    workflow = _load(DEPLOY_WORKFLOW)
    deploy = workflow["jobs"]["deploy"]

    create = _step(deploy, "Create staging field-evidence metadata")
    upload = _step(deploy, "Upload staging field-evidence metadata")
    smoke_index = deploy["steps"].index(_step(deploy, "Post-deployment smoke test"))
    create_index = deploy["steps"].index(create)

    assert create_index > smoke_index
    assert create["if"] == "${{ inputs.environment == 'staging' }}"
    assert create["env"] == {
        "RELEASE_SHA": "${{ inputs.release-sha }}",
        "FRONTEND_IMAGE_DIGEST": "${{ steps.release-images.outputs.frontend-digest }}",
        "DEPLOYMENT_URL": "${{ vars.DEPLOYMENT_URL }}",
        "DEPLOYED_AT": "${{ steps.field-evidence-time.outputs.timestamp }}",
        "DEPLOY_RUN_ID": "${{ github.run_id }}",
        "DEPLOY_RUN_ATTEMPT": "${{ github.run_attempt }}",
    }
    create_script = create["run"]
    assert "staging-deployment.json" in create_script
    assert "staging-deployment.json.sha256" in create_script
    assert "sha256sum" in create_script

    assert upload["if"] == "${{ inputs.environment == 'staging' }}"
    assert str(upload["uses"]).startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == "staging-deployment-${{ inputs.release-sha }}"
    assert upload["with"]["path"] == (
        "artifacts/cwv/staging-deployment.json\n"
        "artifacts/cwv/staging-deployment.json.sha256\n"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 30


def test_field_certification_accepts_only_exact_protected_main_deploy() -> None:
    workflow = _load(CERTIFICATION_WORKFLOW)
    assert set(_triggers(workflow)) == {"workflow_dispatch"}
    dispatch = _triggers(workflow)["workflow_dispatch"]
    assert set(dispatch["inputs"]) == {
        "deploy-run-id",
        "deploy-run-attempt",
        "release-sha",
        "frontend-image-digest",
    }
    assert all(item["required"] is True for item in dispatch["inputs"].values())
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}

    certify = workflow["jobs"]["certify"]
    assert certify["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert certify["environment"] == "staging"
    assert certify["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "attestations": "write",
    }

    verify = _step(certify, "Verify exact successful staging deployment")
    assert verify["env"]["WORKFLOW_SHA"] == "${{ github.workflow_sha }}"
    assert verify["env"]["DISPATCH_SHA"] == "${{ github.sha }}"
    script = verify["run"]
    for invariant in (
        ".head_sha",
        ".run_attempt",
        ".conclusion",
        ".event",
        ".head_branch",
        ".path",
        ".github/workflows/deploy.yml",
        "refs/remotes/origin/main",
        "staging-deployment-$RELEASE_SHA",
    ):
        assert invariant in script
    assert 'test "$WORKFLOW_SHA" = "$RELEASE_SHA"' in script
    assert 'test "$DISPATCH_SHA" = "$RELEASE_SHA"' in script

    download = _step(certify, "Download exact deployment metadata")
    assert str(download["uses"]).startswith("actions/download-artifact@")
    assert download["with"] == {
        "name": "staging-deployment-${{ inputs.release-sha }}",
        "run-id": "${{ inputs.deploy-run-id }}",
        "github-token": "${{ github.token }}",
        "path": "artifacts/cwv/deployment",
    }


def test_field_report_comes_from_oidc_authenticated_staging_exporter() -> None:
    workflow = _load(CERTIFICATION_WORKFLOW)
    certify = workflow["jobs"]["certify"]

    oidc = _step(certify, "Request exporter OIDC token")
    assert str(oidc["uses"]).startswith("actions/github-script@")
    assert (
        oidc["with"]["script"].count("core.getIDToken('university-cwv-exporter')") == 1
    )
    assert "core.setSecret(token)" in oidc["with"]["script"]

    export = _step(certify, "Export immutable staging field report")
    assert export["env"]["OIDC_TOKEN"] == "${{ steps.exporter-token.outputs.token }}"
    export_script = export["run"]
    assert "artifacts/cwv/deployment/staging-deployment.json" in export_script
    assert 'CWV_EXPORT_URL="${deployment_url%/}/api/v1/cwv/export"' in export_script
    assert "Authorization: Bearer $OIDC_TOKEN" in export_script
    assert "--fail-with-body" in export_script
    assert "--max-redirs 0" in export_script
    assert "--location" not in export_script
    assert '--data-urlencode "release_sha=$RELEASE_SHA"' in export_script
    assert (
        '--data-urlencode "frontend_image_digest=$FRONTEND_IMAGE_DIGEST"'
        in export_script
    )
    assert '--data-urlencode "deployment_run_id=$DEPLOY_RUN_ID"' in export_script
    assert (
        '--data-urlencode "deployment_run_attempt=$DEPLOY_RUN_ATTEMPT"' in export_script
    )

    validate = _step(certify, "Validate and certify field report")
    validate_script = validate["run"]
    assert "sha256sum --check" in validate_script
    assert "scripts/quality/evaluate_cwv_field.py" in validate_script
    assert (
        "--deployment-metadata artifacts/cwv/deployment/staging-deployment.json"
        in validate_script
    )
    assert (
        "--deployment-checksum artifacts/cwv/deployment/staging-deployment.json.sha256"
        in validate_script
    )
    assert (
        "--deployment-schema quality/cwv-deployment-metadata.schema.json"
        in validate_script
    )
    assert '--expected-commit-sha "$RELEASE_SHA"' in validate_script
    assert '--expected-image-digest "$FRONTEND_IMAGE_DIGEST"' in validate_script
    assert '--expected-deployment-run-id "$DEPLOY_RUN_ID"' in validate_script
    assert '--expected-deployment-run-attempt "$DEPLOY_RUN_ATTEMPT"' in validate_script

    upload = _step(certify, "Upload field certification evidence")
    assert str(upload["uses"]).startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == "cwv-field-certificate-${{ inputs.release-sha }}"
    assert upload["with"]["path"] == (
        "artifacts/cwv/certificate/**\n"
        "artifacts/cwv/deployment/**\n"
        "artifacts/cwv/provenance/**\n"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 30

    attest = _step(certify, "Attest field certification evidence")
    assert str(attest["uses"]).startswith("actions/attest-build-provenance@")
    assert attest["with"]["subject-path"] == "artifacts/cwv/**"


def test_production_deploy_requires_exact_field_certificate() -> None:
    workflow = _load(DEPLOY_WORKFLOW)
    dispatch = _triggers(workflow)["workflow_dispatch"]
    assert "cwv-certification-run-id" in dispatch["inputs"]
    assert "cwv-certified-frontend-image-digest" in dispatch["inputs"]
    deploy = workflow["jobs"]["deploy"]
    assert deploy["permissions"]["actions"] == "read"

    select_image = _step(deploy, "Select immutable frontend image")
    assert select_image["env"]["CERTIFIED_FRONTEND_IMAGE_DIGEST"] == (
        "${{ inputs.cwv-certified-frontend-image-digest }}"
    )
    assert "^sha256:[0-9a-f]{64}$" in select_image["run"]

    verify = _step(deploy, "Verify production field certification run")
    download = _step(deploy, "Download production field certification")
    validate = _step(deploy, "Validate production field certification")
    production_guard = "${{ inputs.environment == 'production' }}"
    assert verify["if"] == production_guard
    assert download["if"] == production_guard
    assert validate["if"] == production_guard
    assert verify["env"]["CERTIFICATION_RUN_ID"] == (
        "${{ inputs.cwv-certification-run-id }}"
    )
    verify_script = verify["run"]
    for invariant in (
        ".head_sha",
        ".conclusion",
        ".event",
        ".head_branch",
        ".path",
        ".github/workflows/cwv-field-certification.yml",
        "cwv-field-certificate-$RELEASE_SHA",
    ):
        assert invariant in verify_script
    assert download["with"]["run-id"] == "${{ inputs.cwv-certification-run-id }}"
    validate_script = validate["run"]
    assert "production-certificate/certificate" in validate_script
    assert "sha256sum --check field-verdict.json.sha256" in validate_script
    assert '--arg sha "$RELEASE_SHA"' in validate_script
    assert '--arg digest "$FRONTEND_IMAGE_DIGEST"' in validate_script
    assert ".valid == true" in validate_script
    assert "generated_at" in validate_script
    assert "current_epoch - generated_epoch" in validate_script
    assert "259200" in validate_script
