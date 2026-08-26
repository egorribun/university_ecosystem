"""Helm contract tests for rotatable MFA key material."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"

MFA_SECRET_KEYS = {
    "MFA_EMAIL_OTP_HMAC_KEYS": "otp-ring-custom",
    "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID": "otp-active-custom",
    "MFA_EMAIL_DELIVERY_KEKS": "delivery-ring-custom",
    "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID": "delivery-active-custom",
    "MFA_TRUSTED_DEVICE_HMAC_KEYS": "trusted-ring-custom",
    "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID": "trusted-active-custom",
}

MFA_VALUE_KEYS = {
    "MFA_EMAIL_OTP_HMAC_KEYS": "mfaEmailOtpHMACKeys",
    "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID": "mfaEmailOtpActiveHMACKeyId",
    "MFA_EMAIL_DELIVERY_KEKS": "mfaEmailDeliveryKEKs",
    "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID": "mfaEmailDeliveryActiveKEKId",
    "MFA_TRUSTED_DEVICE_HMAC_KEYS": "mfaTrustedDeviceHMACKeys",
    "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID": ("mfaTrustedDeviceActiveHMACKeyId"),
}

FIXED_APPLICATION_SECRET_KEYS = {
    "jwt-secret",
    "jwt-rsa-private-key",
    "jwt-rsa-public-key",
    "internal-hmac-secret",
    "ws-hub-internal-secret",
    "csrf-hmac-secret",
    "spotify-token-secret",
    "elasticsearch-password",
    "spicedb-preshared-key",
    "audit-log-secret",
    "idempotency-hmac-secret",
    "minio-access-key",
    "minio-secret-key",
    "temporal-api-key",
}


def _helm() -> str:
    helm = shutil.which("helm")
    if helm is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun
    return helm


def _bash() -> str:
    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path(shutil.which("bash") or ""),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    pytest.skip("bash is not installed")  # QUALITY-123 @egorribun


def _base_args() -> list[str]:
    return [
        _helm(),
        "template",
        "mfa-contract",
        str(CHART),
        "--dependency-update=false",
        "--set",
        "redis.enabled=false",
        "--set",
        "revocationRedis.enabled=false",
        "--set",
        "nats.enabled=false",
        "--set",
        "fileProcessor.enabled=false",
        "--set",
        "global.imageTag=contract-sha",
    ]


def _render(*extra: str) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [*_base_args(), *extra],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def _deployment_env(
    resources: list[dict[str, Any]], component: str
) -> dict[str, dict[str, Any]]:
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == component
    )
    items = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    names = [item["name"] for item in items]
    assert len(names) == len(set(names)), f"duplicate env variables in {component}"
    return {item["name"]: item for item in items}


def test_external_application_secret_maps_all_mfa_keys_to_both_workloads() -> None:
    overrides = [
        "--set",
        "applicationSecrets.existingSecret=eso-application-secret",
        "--set-string",
        "backend.env.MFA_EMAIL_OTP_HMAC_KEYS=inline-bypass",
        "--set-string",
        "outboxWorker.env.MFA_EMAIL_OTP_HMAC_KEYS=inline-bypass",
    ]
    for variable, value_key in MFA_VALUE_KEYS.items():
        overrides.extend(
            (
                "--set-string",
                f"applicationSecrets.keys.{value_key}={MFA_SECRET_KEYS[variable]}",
            )
        )

    resources = _render(*overrides)

    assert not any(resource.get("kind") == "Secret" for resource in resources)
    backend_env = _deployment_env(resources, "backend")
    for variable, secret_key in MFA_SECRET_KEYS.items():
        assert backend_env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": "eso-application-secret",
            "key": secret_key,
        }
        assert "value" not in backend_env[variable]

    outbox_env = _deployment_env(resources, "outbox-worker")
    assert outbox_env["MFA_EMAIL_DELIVERY_KEKS"]["valueFrom"]["secretKeyRef"] == {
        "name": "eso-application-secret",
        "key": MFA_SECRET_KEYS["MFA_EMAIL_DELIVERY_KEKS"],
    }
    assert set(MFA_SECRET_KEYS) - {"MFA_EMAIL_DELIVERY_KEKS"} <= (
        set(MFA_SECRET_KEYS) - set(outbox_env)
    )


def test_mfa_values_schema_requires_valid_parameterized_secret_key_names() -> None:
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    key_schema = schema["properties"]["applicationSecrets"]["properties"]["keys"]

    assert set(MFA_VALUE_KEYS.values()) <= set(key_schema["required"])
    for value_key in MFA_VALUE_KEYS.values():
        assert key_schema["properties"][value_key]["minLength"] == 1
        assert key_schema["properties"][value_key]["maxLength"] == 253
        assert key_schema["properties"][value_key]["pattern"] == (r"^[A-Za-z0-9._-]+$")


def test_render_rejects_an_empty_mfa_secret_key_name() -> None:
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *_base_args(),
            "--set",
            "applicationSecrets.existingSecret=eso-application-secret",
            "--set-string",
            "applicationSecrets.keys.mfaEmailOtpHMACKeys=",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "mfaEmailOtpHMACKeys" in result.stderr


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (
            "applicationSecrets.keys.mfaEmailOtpHMACKeys="
            "mfa-email-otp-active-hmac-key-id",
            "MFA Secret key names must be pairwise unique",
        ),
        (
            "applicationSecrets.keys.mfaEmailOtpHMACKeys=jwt-secret",
            "MFA Secret key names must not collide with fixed application Secret keys",
        ),
    ],
)
def test_render_rejects_mfa_secret_key_name_collisions(
    override: str, expected: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *_base_args(),
            "--set",
            "applicationSecrets.existingSecret=eso-application-secret",
            "--set-string",
            override,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize("environment", ["Production", "prod", "qa", ""])
def test_render_rejects_non_canonical_environment_names(environment: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *_base_args(),
            "--set",
            "applicationSecrets.existingSecret=eso-application-secret",
            "--set-string",
            f"global.environment={environment}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "global/environment" in result.stderr


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_non_development_render_rejects_inline_mfa_key_material(
    environment: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *_base_args(),
            "--set",
            f"global.environment={environment}",
            "--set",
            "applicationSecrets.existingSecret=eso-application-secret",
            "--set",
            "backend.config.minioSecure=true",
            "--set",
            "gateway.config.grpcUseTLS=true",
            "--set-string",
            "backend.config.mfaEmailOtpHMACKeys=active:inline-material",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "MFA key material must not be stored in Helm values" in result.stderr


def test_secret_preflight_contract_matches_rendered_workload_references() -> None:
    overrides = [
        "--set",
        "applicationSecrets.existingSecret=eso-application-secret",
        "--set",
        "deploymentContract.enabled=true",
        "--set",
        "fileProcessor.enabled=true",
    ]
    for variable, value_key in MFA_VALUE_KEYS.items():
        overrides.extend(
            (
                "--set-string",
                f"applicationSecrets.keys.{value_key}={MFA_SECRET_KEYS[variable]}",
            )
        )
    resources = _render(*overrides)
    contract = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"].endswith("-deployment-contract")
    )
    assert contract["data"]["application-secret-name"] == "eso-application-secret"
    application_keys = set(json.loads(contract["data"]["application-secret-keys.json"]))
    connection_keys = set(json.loads(contract["data"]["connection-secret-keys.json"]))
    mfa_key_contract = json.loads(contract["data"]["mfa-key-contract.json"])
    assert FIXED_APPLICATION_SECRET_KEYS <= application_keys
    assert set(MFA_SECRET_KEYS.values()) <= application_keys
    assert mfa_key_contract == {
        "otp": {
            "ring": MFA_SECRET_KEYS["MFA_EMAIL_OTP_HMAC_KEYS"],
            "active": MFA_SECRET_KEYS["MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID"],
        },
        "delivery": {
            "ring": MFA_SECRET_KEYS["MFA_EMAIL_DELIVERY_KEKS"],
            "active": MFA_SECRET_KEYS["MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID"],
        },
        "trusted": {
            "ring": MFA_SECRET_KEYS["MFA_TRUSTED_DEVICE_HMAC_KEYS"],
            "active": MFA_SECRET_KEYS["MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID"],
        },
    }

    workload_contracts = {
        "backend": set(json.loads(contract["data"]["backend-secret-keys.json"])),
        "outbox-worker": set(
            json.loads(contract["data"]["outbox-worker-secret-keys.json"])
        ),
    }
    deployments = {
        resource["metadata"]["labels"]["app.kubernetes.io/component"]: resource
        for resource in resources
        if resource.get("kind") == "Deployment"
    }
    for component, expected_keys in workload_contracts.items():
        pod_spec = deployments[component]["spec"]["template"]["spec"]
        refs = {
            ref["key"]
            for env in pod_spec["containers"][0]["env"]
            if (ref := env.get("valueFrom", {}).get("secretKeyRef"))
            and ref["name"] == "eso-application-secret"
        }
        refs.update(
            item["key"]
            for volume in pod_spec.get("volumes", [])
            if volume.get("secret", {}).get("secretName") == "eso-application-secret"
            for item in volume["secret"].get("items", [])
        )
        assert refs == expected_keys
        connection_refs = {
            ref["key"]
            for env in pod_spec["containers"][0]["env"]
            if (ref := env.get("valueFrom", {}).get("secretKeyRef"))
            and ref["name"] == "university-connections"
        }
        assert connection_refs
        assert connection_refs <= connection_keys
        secret_names = {
            env["valueFrom"]["secretKeyRef"]["name"]
            for env in pod_spec["containers"][0]["env"]
            if "secretKeyRef" in env.get("valueFrom", {})
        }
        assert secret_names <= {"eso-application-secret", "university-connections"}


def test_chart_patch_version_documents_the_mfa_secret_contract_upgrade() -> None:
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart["version"] == "0.2.1"


def test_deploy_renderer_clears_values_registry_without_rewriting_dependencies(
    tmp_path: Path,
) -> None:
    bash = _bash()
    values_file = tmp_path / "registry-values.yaml"
    values_file.write_text(
        "global:\n  imageRegistry: mirror.invalid\n",
        encoding="utf-8",
    )
    digest = f"sha256:{'a' * 64}"
    environment = {
        **os.environ,
        "DEPLOY_ENVIRONMENT": "development",
        "K8S_NAMESPACE": "contract",
        "HELM_RELEASE_NAME": "registry-contract",
        "HELM_VALUES_FILE": str(values_file),
        "CONNECTIONS_SECRET_NAME": "connections",  # pragma: allowlist secret
        "APPLICATION_SECRETS_NAME": "application",  # pragma: allowlist secret
        "REGISTRY": "ghcr.io",
        "GITHUB_REPOSITORY": "example/university",
        "DEPLOY_VERSION": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
        "BACKEND_IMAGE_DIGEST": digest,
        "FRONTEND_IMAGE_DIGEST": digest,
        "WS_HUB_IMAGE_DIGEST": digest,
        "GATEWAY_IMAGE_DIGEST": digest,
        "FILE_PROCESSOR_IMAGE_DIGEST": digest,
    }
    result = subprocess.run(  # noqa: S603 - fixed repository deploy renderer
        [bash, ".github/scripts/deploy-helm.sh", "render"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    resources = [item for item in yaml.safe_load_all(result.stdout) if item]
    images = {
        container["image"]
        for resource in resources
        for container in resource.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    }
    expected_first_party = {
        f"ghcr.io/example/university/{component}@{digest}"
        for component in (
            "backend",
            "frontend",
            "ws-hub",
            "gateway",
            "file-processor",
        )
    }
    assert expected_first_party <= images
    assert not any(image.startswith("mirror.invalid/") for image in images)
    dependency_images = images - expected_first_party
    assert any("bitnami/redis" in image for image in dependency_images)
    assert any("nats" in image for image in dependency_images)
    assert not any(
        image.startswith("ghcr.io/example/university/") for image in dependency_images
    )


def test_deploy_renderer_executes_canonical_staging_without_required_markers() -> None:
    bash = _bash()
    digest = f"sha256:{'a' * 64}"
    environment = {
        **os.environ,
        "DEPLOY_ENVIRONMENT": "staging",
        "K8S_NAMESPACE": "university-ecosystem",
        "HELM_RELEASE_NAME": "staging-execution-contract",
        "HELM_VALUES_FILE": str(CHART / "values-staging.yaml"),
        "CONNECTIONS_SECRET_NAME": "university-connections",  # pragma: allowlist secret
        "APPLICATION_SECRETS_NAME": "university-application",  # pragma: allowlist secret
        "REGISTRY": "ghcr.io",
        "GITHUB_REPOSITORY": "example/university",
        "DEPLOY_VERSION": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
        "DEPLOYMENT_URL": "https://university.staging.example.org",
        "CWV_EXPORT_OIDC_SUBJECT": ("repo:example/university:environment:staging"),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "FRONTEND_HOST": "university.staging.example.org",
        "API_HOST": "api.university.staging.example.org",
        "TLS_SECRET_NAME": "university-ecosystem-tls",  # pragma: allowlist secret
        "CERT_MANAGER_ISSUER_NAME": "university-staging-issuer",
        "ELASTICSEARCH_URL": "https://elasticsearch.staging.internal",
        "FLAGD_HOST": "flagd.staging.internal",
        "OTLP_ENDPOINT": "otel-collector.staging.internal:4317",
        "MINIO_ENDPOINT": "minio.staging.internal:443",
        "TEMPORAL_HOST": "temporal.staging.internal:7233",
        "BACKEND_IMAGE_DIGEST": digest,
        "FRONTEND_IMAGE_DIGEST": digest,
        "WS_HUB_IMAGE_DIGEST": digest,
        "GATEWAY_IMAGE_DIGEST": digest,
        "FILE_PROCESSOR_IMAGE_DIGEST": digest,
        "REDIS_IMAGE_DIGEST": digest,
        "REDIS_METRICS_IMAGE_DIGEST": digest,
        "REVOCATION_REDIS_IMAGE_DIGEST": digest,
        "REVOCATION_REDIS_METRICS_IMAGE_DIGEST": digest,
        "NATS_IMAGE_DIGEST": digest,
    }
    result = subprocess.run(  # noqa: S603 - fixed repository deploy renderer
        [bash, ".github/scripts/deploy-helm.sh", "render"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "REQUIRED_" not in result.stdout
    resources = [item for item in yaml.safe_load_all(result.stdout) if item]
    ws_hub = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == "ws-hub"
    )
    assert (
        ws_hub["spec"]["template"]["metadata"]["annotations"][
            "university-ecosystem.io/source-sha"
        ]
        == environment["DEPLOY_VERSION"]
    )
