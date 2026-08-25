"""Fail-closed deployment contracts for MFA key rotation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy.yml"
SMOKE_PATH_VALIDATOR = ROOT / ".github" / "scripts" / "validate_mfa_smoke_path.py"
SMOKE_SCRIPT = ROOT / ".github" / "deployment-smoke" / "mfa-key-overlap.sh"
KEY_ROTATION_VALIDATOR = ROOT / ".github" / "scripts" / "verify_mfa_key_rotation.py"


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _step(name: str) -> dict[str, Any]:
    steps = _workflow()["jobs"]["deploy"]["steps"]
    return next(step for step in steps if step.get("name") == name)


def test_deploy_preflight_uses_the_same_helm_input_builder_as_upgrade() -> None:
    verify = _step("Verify effective Secret contract")
    rbac = _step("Verify rendered Helm resource RBAC")
    deploy = _step("Deploy Helm release atomically")

    assert "bash .github/scripts/deploy-helm.sh render-secret-contract" in str(
        verify["run"]
    )
    assert "bash .github/scripts/deploy-helm.sh lint" in str(deploy["run"])
    assert "bash .github/scripts/deploy-helm.sh upgrade" in str(deploy["run"])
    common_env = {
        "DEPLOY_ENVIRONMENT",
        "K8S_NAMESPACE",
        "HELM_RELEASE_NAME",
        "HELM_VALUES_FILE",
        "CONNECTIONS_SECRET_NAME",
        "APPLICATION_SECRETS_NAME",
        "BACKEND_IMAGE_DIGEST",
        "FRONTEND_IMAGE_DIGEST",
        "GATEWAY_IMAGE_DIGEST",
        "FILE_PROCESSOR_IMAGE_DIGEST",
    }
    assert common_env <= set(verify["env"])
    assert common_env <= set(rbac["env"])
    assert common_env <= set(deploy["env"])
    for name in common_env:
        assert verify["env"][name] == deploy["env"][name]
        assert rbac["env"][name] == deploy["env"][name]
    script = (ROOT / ".github" / "scripts" / "deploy-helm.sh").read_text(
        encoding="utf-8"
    )
    assert "--set deploymentContract.enabled=false" in script
    assert "--set deploymentContract.enabled=true" in script
    assert "--show-only templates/deployment-contract.yaml" in script
    assert '--set-string "global.imageRegistry="' in script
    for repository in (
        "$REGISTRY/$GITHUB_REPOSITORY/backend",
        "$REGISTRY/$GITHUB_REPOSITORY/frontend",
        "$REGISTRY/$GITHUB_REPOSITORY/gateway",
        "$REGISTRY/$GITHUB_REPOSITORY/file-processor",
    ):
        assert repository in script


def test_preflight_validates_effective_connection_and_application_secret_keys() -> None:
    verify = _step("Verify effective Secret contract")
    run = str(verify["run"])

    assert "application-secret-name" in run
    assert "application-secret-keys.json" in run
    assert "connection-secret-name" in run
    assert "connection-secret-keys.json" in run
    assert "jq --raw-output 'fromjson[]'" in run
    assert 'require_secret_keys "$application_secret_name"' in run
    assert 'require_secret_keys "$connection_secret_name"' in run
    assert "kubectl get secret" in run
    assert "missing non-empty key" in run


def test_external_secret_reconciliation_waits_for_fresh_ready_secret() -> None:
    validate = _step("Validate deployment contract")
    assert "APPLICATION_EXTERNAL_SECRET_NAME" in str(validate["run"])
    reconcile = _step("Reconcile application ExternalSecret")
    run = str(reconcile["run"])

    assert "kubectl get externalsecret" in run
    assert ".spec.target.name" in run
    assert "APPLICATION_SECRETS_NAME" in run
    assert "resourceVersion" in run
    assert "force-sync" in run
    assert "kubectl annotate externalsecret" in run
    assert 'condition_type="Ready"' in run
    assert ".type == $condition_type" in run
    assert "refreshTime" in run
    assert "new_refresh_time" in run
    assert "previous_refresh_time" in run
    assert "new_resource_version" in run
    assert "previous_resource_version" in run


def test_external_secret_rotation_is_explicit_and_normal_deploys_do_not_force_it() -> (
    None
):
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "rotate-mfa-keys:" in text
    assert "type: boolean" in text
    assert "default: false" in text
    assert _step("Reconcile application ExternalSecret")["if"] == (
        "${{ inputs.rotate-mfa-keys }}"
    )
    assert _step("Load rotated MFA Secret into consumers")["if"] == (
        "${{ inputs.rotate-mfa-keys }}"
    )
    assert _step("Prepare queued MFA overlap challenge")["if"] == (
        "${{ inputs.rotate-mfa-keys }}"
    )
    assert _step("Verify old MFA key-overlap behavior")["if"] == (
        "${{ inputs.rotate-mfa-keys }}"
    )
    assert _step("Verify new MFA key-overlap behavior")["if"] == (
        "${{ inputs.rotate-mfa-keys }}"
    )


def test_secret_rotation_restarts_only_backend_and_outbox_then_runs_required_smoke() -> (
    None
):
    restart = _step("Load rotated MFA Secret into consumers")
    run = str(restart["run"])
    assert "kubectl rollout restart" in run
    assert "kubectl rollout status" in run
    assert "app.kubernetes.io/component=$component" in run
    assert "resolve_component backend" in run
    assert "resolve_component outbox-worker" in run
    assert "gateway" not in run
    assert "availableReplicas" in run

    prepare = _step("Prepare queued MFA overlap challenge")
    prepare_run = str(prepare["run"])
    assert "kubectl scale" in prepare_run
    assert "--replicas=0" in prepare_run
    assert 'bash "$smoke_script" prepare' in prepare_run

    restore = _step("Restore outbox after MFA Secret reconciliation")
    assert "always()" in restore["if"]
    assert "kubectl scale" in str(restore["run"])

    old_hook = _step("Verify old MFA key-overlap behavior")
    new_hook = _step("Verify new MFA key-overlap behavior")
    assert 'bash "$smoke_script" verify-old' in str(old_hook["run"])
    assert 'bash "$smoke_script" verify-new' in str(new_hook["run"])
    assert "eval" not in str(old_hook["run"])
    assert "eval" not in str(new_hook["run"])


def test_old_overlap_verification_precedes_unrelated_helm_rollout() -> None:
    steps = _workflow()["jobs"]["deploy"]["steps"]
    names = [step.get("name") for step in steps]
    ordered = [
        "Prepare queued MFA overlap challenge",
        "Reconcile application ExternalSecret",
        "Verify rotated MFA key metadata",
        "Restore outbox after MFA Secret reconciliation",
        "Load rotated MFA Secret into consumers",
        "Verify old MFA key-overlap behavior",
        "Deploy Helm release atomically",
        "Verify new MFA key-overlap behavior",
    ]
    assert [names.index(name) for name in ordered] == sorted(
        names.index(name) for name in ordered
    )
    load_index = names.index("Load rotated MFA Secret into consumers")
    assert names[load_index + 1] == "Verify old MFA key-overlap behavior"
    reconcile = str(_step("Reconcile application ExternalSecret")["run"])
    load = str(_step("Load rotated MFA Secret into consumers")["run"])
    assert "SECONDS + 90" in reconcile
    assert "--timeout=90s" in load
    bounded_steps = (
        _step("Reconcile application ExternalSecret"),
        _step("Verify rotated MFA key metadata"),
        _step("Load rotated MFA Secret into consumers"),
        _step("Verify old MFA key-overlap behavior"),
    )
    assert [step["timeout-minutes"] for step in bounded_steps] == [2, 1, 2, 4]
    assert sum(step["timeout-minutes"] for step in bounded_steps) < 10


def test_rotation_contract_requires_reviewed_smoke_inputs() -> None:
    validate = _step("Validate deployment contract")
    run = str(validate["run"])
    assert 'if [[ "$ROTATE_MFA_KEYS" == "true" ]]' in run
    for required in (
        "MFA_OVERLAP_SMOKE_SCRIPT",
        "MFA_SMOKE_BASE_URL",
        "MFA_SMOKE_MAILBOX_URL",
        "MFA_SMOKE_EMAIL",
        "MFA_SMOKE_PASSWORD",
        "MFA_SMOKE_MAILBOX_TOKEN",
    ):
        assert required in validate["env"]
        assert required in run
    assert "validate_mfa_smoke_path.py" in run


def _validate_smoke_path(
    workspace: Path, candidate: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local contract validator
        [sys.executable, str(SMOKE_PATH_VALIDATOR), candidate],
        cwd=workspace,
        env={**os.environ, "GITHUB_WORKSPACE": str(workspace)},
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )


def _init_git_workspace(path: Path) -> None:
    git = which("git")
    assert git is not None
    subprocess.run([git, "init", "--quiet"], cwd=path, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [git, "config", "user.email", "contract@example.invalid"],
        cwd=path,
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "config", "user.name", "Contract Test"], cwd=path, check=True
    )


def test_smoke_path_validator_rejects_blank_missing_traversal_and_untracked(
    tmp_path: Path,
) -> None:
    _init_git_workspace(tmp_path)
    allowed = tmp_path / ".github" / "deployment-smoke"
    allowed.mkdir(parents=True)
    untracked = allowed / "untracked.sh"
    untracked.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    outside = tmp_path / "outside.sh"
    outside.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    for candidate in ("", str(allowed / "missing.sh"), str(outside), str(untracked)):
        result = _validate_smoke_path(tmp_path, candidate)
        assert result.returncode != 0, candidate


def test_smoke_path_validator_accepts_only_head_tracked_unmodified_file(
    tmp_path: Path,
) -> None:
    _init_git_workspace(tmp_path)
    allowed = tmp_path / ".github" / "deployment-smoke"
    allowed.mkdir(parents=True)
    tracked = allowed / "reviewed.sh"
    tracked.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    git = which("git")
    assert git is not None
    subprocess.run([git, "add", "."], cwd=tmp_path, check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [git, "commit", "--quiet", "-m", "review smoke"], cwd=tmp_path, check=True
    )

    accepted = _validate_smoke_path(tmp_path, ".github/deployment-smoke/reviewed.sh")
    assert accepted.returncode == 0, accepted.stderr
    assert Path(accepted.stdout.strip()) == tracked.resolve()

    tracked.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    modified = _validate_smoke_path(tmp_path, str(tracked))
    assert modified.returncode != 0


def test_checked_in_overlap_smoke_exercises_both_key_generations_and_delivery() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "prepare)" in text
    assert "verify-old)" in text
    assert "verify-new)" in text
    assert "old-verified" in text
    assert "/api/v1/auth/login/json" in text
    assert "/api/v1/auth/mfa/verify" in text
    assert "await_email_otp" in text
    assert "delivery_id" in text
    assert "access_token_v2" in text
    assert "old" in text
    assert "new" in text
    assert "health" not in text.lower()


def test_old_overlap_smoke_bounds_mailbox_wait_by_otp_expiry() -> None:
    text = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "otp_ttl_seconds=600" in text
    assert "otp_expiry_safety_seconds=30" in text
    assert "queued_at_epoch + otp_ttl_seconds" in text
    assert "old_delivery_timeout_seconds" in text
    assert 'await_delivery old "$old_challenge_token" "$old_delivery"' in text


def test_deployment_rbac_preflight_covers_deployment_observation_and_mutation() -> None:
    run = str(_step("Configure and verify cluster access")["run"])
    for verb in ("get", "list", "watch", "patch"):
        assert f"kubectl auth can-i {verb} deployments" in run


def test_deployment_rbac_preflight_covers_helm_storage_and_rendered_mutations() -> None:
    cluster = str(_step("Configure and verify cluster access")["run"])
    assert "create namespaces" in cluster
    assert "helm_secret_verbs=(get list watch create update patch delete)" in cluster
    assert 'kubectl auth can-i "$verb" secrets' in cluster

    rendered = _step("Verify rendered Helm resource RBAC")
    run = str(rendered["run"])
    assert "bash .github/scripts/deploy-helm.sh render" in run
    assert "kubectl create --dry-run=client --validate=false" in run
    assert "rendered_resource_verbs=(get list watch create update patch delete)" in run
    assert 'kubectl auth can-i "$verb" "$resource"' in run


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _test_key_material(label: str) -> bytes:
    return label.encode().ljust(32, b"!")


def _ring(*key_ids: str, materials: dict[str, bytes] | None = None) -> str:
    overrides = materials or {}
    return ",".join(
        f"{key_id}:{base64.urlsafe_b64encode(overrides.get(key_id, _test_key_material(key_id))).decode()}"
        for key_id in key_ids
    )


def _rotation_secret(active_suffix: str, *, retain_old: bool = True) -> dict[str, Any]:
    data: dict[str, str] = {}
    for prefix in ("otp", "delivery", "trusted"):
        active = f"{prefix}-{active_suffix}"
        old = f"{prefix}-old"
        ids = ([old] if retain_old and active != old else []) + [active]
        data[f"{prefix}-ring"] = _encoded(_ring(*ids))
        data[f"{prefix}-active"] = _encoded(active)
    return {"metadata": {"name": "application"}, "data": data}


def _key_contract(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                prefix: {
                    "ring": f"{prefix}-ring",
                    "active": f"{prefix}-active",
                }
                for prefix in ("otp", "delivery", "trusted")
            }
        ),
        encoding="utf-8",
    )


def _run_key_rotation_validator(
    mode: str,
    *,
    state_dir: Path,
    contract: Path,
    secret: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed repository validator
        [
            sys.executable,
            str(KEY_ROTATION_VALIDATOR),
            mode,
            "--state-dir",
            str(state_dir),
            "--contract-file",
            str(contract),
            "--expected-secret-name",
            "application",
        ],
        input=json.dumps(secret),
        env={**os.environ, "RUNNER_TEMP": str(state_dir.parent)},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_rotation_metadata_validator_requires_all_active_ids_to_change_with_overlap(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    before = _rotation_secret("old")
    for prefix in ("otp", "delivery", "trusted"):
        before["data"][f"{prefix}-ring"] = _encoded(_ring(f"{prefix}-old"))

    captured = _run_key_rotation_validator(
        "capture-pre", state_dir=state_dir, contract=contract, secret=before
    )
    assert captured.returncode == 0, captured.stderr
    assert captured.stdout == ""
    verified = _run_key_rotation_validator(
        "verify-post",
        state_dir=state_dir,
        contract=contract,
        secret=_rotation_secret("new"),
    )
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout == ""
    metadata = json.loads((state_dir / "post-key-metadata.json").read_text())
    assert set(metadata) == {"otp", "delivery", "trusted"}
    for group in ("otp", "delivery", "trusted"):
        assert set(metadata[group]) == {"active_id", "fingerprints"}
        assert set(metadata[group]["fingerprints"]) == {
            f"{group}-old",
            f"{group}-new",
        }
        assert all(
            len(fingerprint) == 64 and set(fingerprint) <= set("0123456789abcdef")
            for fingerprint in metadata[group]["fingerprints"].values()
        )


def test_rotation_metadata_validator_rejects_unchanged_or_missing_overlap(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    before = _rotation_secret("old")
    for prefix in ("otp", "delivery", "trusted"):
        before["data"][f"{prefix}-ring"] = _encoded(_ring(f"{prefix}-old"))
    assert (
        _run_key_rotation_validator(
            "capture-pre", state_dir=state_dir, contract=contract, secret=before
        ).returncode
        == 0
    )

    unchanged = _run_key_rotation_validator(
        "verify-post", state_dir=state_dir, contract=contract, secret=before
    )
    assert unchanged.returncode != 0
    missing_old = _run_key_rotation_validator(
        "verify-post",
        state_dir=state_dir,
        contract=contract,
        secret=_rotation_secret("new", retain_old=False),
    )
    assert missing_old.returncode != 0


@pytest.mark.parametrize("group", ("otp", "delivery", "trusted"))
def test_rotation_metadata_validator_rejects_duplicate_material_with_distinct_ids(
    tmp_path: Path,
    group: str,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    secret = _rotation_secret("old")
    duplicate = _test_key_material(f"{group}-duplicate")
    secret["data"][f"{group}-ring"] = _encoded(
        _ring(
            f"{group}-old",
            f"{group}-duplicate",
            materials={
                f"{group}-old": duplicate,
                f"{group}-duplicate": duplicate,
            },
        )
    )

    result = _run_key_rotation_validator(
        "capture-pre", state_dir=state_dir, contract=contract, secret=secret
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert f"{group}-duplicate" not in result.stderr
    assert base64.urlsafe_b64encode(duplicate).decode() not in result.stderr
    assert hashlib.sha256(duplicate).hexdigest() not in result.stderr


@pytest.mark.parametrize(
    ("first_group", "second_group"),
    (("otp", "delivery"), ("delivery", "trusted"), ("trusted", "otp")),
)
def test_rotation_metadata_validator_rejects_material_reused_across_rings(
    tmp_path: Path,
    first_group: str,
    second_group: str,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    secret = _rotation_secret("old")
    duplicate = _test_key_material("cross-ring-duplicate")
    for group in (first_group, second_group):
        key_id = f"{group}-old"
        secret["data"][f"{group}-ring"] = _encoded(
            _ring(key_id, materials={key_id: duplicate})
        )

    result = _run_key_rotation_validator(
        "capture-pre", state_dir=state_dir, contract=contract, secret=secret
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert first_group not in result.stderr
    assert second_group not in result.stderr
    assert base64.urlsafe_b64encode(duplicate).decode() not in result.stderr
    assert hashlib.sha256(duplicate).hexdigest() not in result.stderr


@pytest.mark.parametrize("group", ("otp", "delivery", "trusted"))
def test_rotation_metadata_validator_rejects_new_active_material_seen_before_rotation(
    tmp_path: Path,
    group: str,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    before = _rotation_secret("old")
    retired_id = f"{group}-retired"
    before["data"][f"{group}-ring"] = _encoded(_ring(f"{group}-old", retired_id))
    assert (
        _run_key_rotation_validator(
            "capture-pre", state_dir=state_dir, contract=contract, secret=before
        ).returncode
        == 0
    )
    after = _rotation_secret("new")
    reused_material = _test_key_material(retired_id)
    after["data"][f"{group}-ring"] = _encoded(
        _ring(
            f"{group}-old",
            f"{group}-new",
            materials={f"{group}-new": reused_material},
        )
    )

    result = _run_key_rotation_validator(
        "verify-post", state_dir=state_dir, contract=contract, secret=after
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert f"{group}-retired" not in result.stderr
    assert base64.urlsafe_b64encode(reused_material).decode() not in result.stderr
    assert hashlib.sha256(reused_material).hexdigest() not in result.stderr


@pytest.mark.parametrize(
    ("source_group", "target_group"),
    (("otp", "delivery"), ("delivery", "trusted"), ("trusted", "otp")),
)
def test_rotation_metadata_validator_rejects_new_active_material_from_another_pre_ring(
    tmp_path: Path,
    source_group: str,
    target_group: str,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    before = _rotation_secret("old")
    retired_id = f"{source_group}-retired"
    before["data"][f"{source_group}-ring"] = _encoded(
        _ring(f"{source_group}-old", retired_id)
    )
    assert (
        _run_key_rotation_validator(
            "capture-pre", state_dir=state_dir, contract=contract, secret=before
        ).returncode
        == 0
    )
    after = _rotation_secret("new")
    reused_material = _test_key_material(retired_id)
    after["data"][f"{target_group}-ring"] = _encoded(
        _ring(
            f"{target_group}-old",
            f"{target_group}-new",
            materials={f"{target_group}-new": reused_material},
        )
    )

    result = _run_key_rotation_validator(
        "verify-post", state_dir=state_dir, contract=contract, secret=after
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert retired_id not in result.stderr
    assert hashlib.sha256(reused_material).hexdigest() not in result.stderr


@pytest.mark.parametrize("group", ("otp", "delivery", "trusted"))
def test_rotation_metadata_validator_rejects_changed_overlap_material(
    tmp_path: Path,
    group: str,
) -> None:
    contract = tmp_path / "contract.json"
    state_dir = tmp_path / "state"
    _key_contract(contract)
    before = _rotation_secret("old")
    assert (
        _run_key_rotation_validator(
            "capture-pre", state_dir=state_dir, contract=contract, secret=before
        ).returncode
        == 0
    )
    after = _rotation_secret("new")
    changed_overlap = _test_key_material(f"changed-{group}-old")
    after["data"][f"{group}-ring"] = _encoded(
        _ring(
            f"{group}-old",
            f"{group}-new",
            materials={f"{group}-old": changed_overlap},
        )
    )

    result = _run_key_rotation_validator(
        "verify-post", state_dir=state_dir, contract=contract, secret=after
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert f"changed-{group}-old" not in result.stderr
    assert base64.urlsafe_b64encode(changed_overlap).decode() not in result.stderr
    assert hashlib.sha256(changed_overlap).hexdigest() not in result.stderr


def test_workflow_captures_and_verifies_all_mfa_key_metadata_without_logging() -> None:
    capture = str(_step("Capture pre-rotation MFA key metadata")["run"])
    verify = str(_step("Verify rotated MFA key metadata")["run"])
    assert "mfa-key-contract.json" in capture
    assert "verify_mfa_key_rotation.py capture-pre" in capture
    assert "verify_mfa_key_rotation.py verify-post" in verify
    assert "kubectl get secret" in capture
    assert "kubectl get secret" in verify
    assert "set -x" not in capture + verify
    contract = (
        ROOT
        / "charts"
        / "university-ecosystem"
        / "templates"
        / "deployment-contract.yaml"
    ).read_text(encoding="utf-8")
    for field in (
        "mfaEmailOtpHMACKeys",
        "mfaEmailOtpActiveHMACKeyId",
        "mfaEmailDeliveryKEKs",
        "mfaEmailDeliveryActiveKEKId",
        "mfaTrustedDeviceHMACKeys",
        "mfaTrustedDeviceActiveHMACKeyId",
    ):
        assert field in contract


def test_deployment_docs_define_external_secret_prerequisites_and_upgrade_order() -> (
    None
):
    for name in ("DEPLOY.md", "DEPLOY.en.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        for required in (
            "APPLICATION_EXTERNAL_SECRET_NAME",
            "MFA_OVERLAP_SMOKE_SCRIPT",
            "resourceVersion",
            "ExternalSecret",
            "MFA_EMAIL_OTP_HMAC_KEYS",
            "MFA_EMAIL_DELIVERY_KEKS",
            "MFA_TRUSTED_DEVICE_HMAC_KEYS",
        ):
            assert required in text, f"{required} missing from {name}"
        marker = (
            "Порядок безопасной ротации:"
            if name == "DEPLOY.md"
            else "Use this rotation order:"
        )
        rotation = text.split(marker, maxsplit=1)[1]
        assert "90" in rotation
        assert rotation.index("MFA_EMAIL_OTP_HMAC_KEYS") < rotation.index(
            "resourceVersion"
        )
