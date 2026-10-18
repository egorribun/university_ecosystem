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
MFA_HELM_RELEASE_NAME = "mfa-contract"
MFA_EXTERNAL_APPLICATION_SECRET = "eso-application-secret"
MFA_TOTP_ACTIVE_KEY_ID = "totp-active-contract"

MFA_SECRET_KEYS = {
    "MFA_TOTP_ENCRYPTION_KEYS": "totp-ring-custom",
    "MFA_EMAIL_OTP_HMAC_KEYS": "otp-ring-custom",
    "MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID": "otp-active-custom",
    "MFA_EMAIL_DELIVERY_KEKS": "delivery-ring-custom",
    "MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID": "delivery-active-custom",
    "MFA_TRUSTED_DEVICE_HMAC_KEYS": "trusted-ring-custom",
    "MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID": "trusted-active-custom",
}

MFA_VALUE_KEYS = {
    "MFA_TOTP_ENCRYPTION_KEYS": "mfaTotpEncryptionKeys",
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
    "token-hmac-secret",
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
        MFA_HELM_RELEASE_NAME,
        str(CHART),
        "--dependency-update=false",
        "--set",
        "fileProcessor.enabled=false",
        "--set",
        "global.environment=development",
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


def _deployment_pod_and_container(
    resources: list[dict[str, Any]], component: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == component
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    names = [item["name"] for item in container["env"]]
    assert len(names) == len(set(names)), f"duplicate env variables in {component}"
    return pod_spec, container


def _deployment_env(
    resources: list[dict[str, Any]], component: str
) -> dict[str, dict[str, Any]]:
    _, container = _deployment_pod_and_container(resources, component)
    return {item["name"]: item for item in container["env"]}


def _secret_volume_names(pod_spec: dict[str, Any]) -> set[str]:
    return {
        volume["name"] for volume in pod_spec.get("volumes", []) if "secret" in volume
    }


def _projected_secret_items(
    pod_spec: dict[str, Any],
    container: dict[str, Any],
    *,
    volume_name: str,
    secret_name: str,
) -> dict[str, str]:
    volumes = [
        volume
        for volume in pod_spec.get("volumes", [])
        if volume["name"] == volume_name
    ]
    assert len(volumes) == 1
    secret_volume = volumes[0]["secret"]
    assert secret_volume["secretName"] == secret_name
    assert secret_volume.get("optional", False) is False
    assert secret_volume["defaultMode"] == 0o440
    items = secret_volume["items"]
    assert len(items) == len({item["key"] for item in items})
    item_paths = {item["key"]: item["path"] for item in items}
    assert item_paths == {key: key for key in item_paths}

    mounts = [
        mount
        for mount in container.get("volumeMounts", [])
        if mount["name"] == volume_name
    ]
    assert len(mounts) == 1
    mount = mounts[0]
    assert mount["mountPath"] == f"/run/secrets/{secret_name}"
    assert mount["readOnly"] is True
    assert "subPath" not in mount
    return item_paths


def _assert_file_secret_environment(
    container: dict[str, Any], expected_paths: set[str]
) -> None:
    env_items = container["env"]
    env = {item["name"]: item for item in env_items}
    file_paths = {
        item.get("value")
        for item in env_items
        if item["name"].endswith("_FILE") or item["name"] == "JWT_PRIVATE_KEY_PATH"
    }
    assert file_paths == expected_paths
    for name in env:
        if name.endswith("_FILE"):
            assert name[:-5] not in env
    if "JWT_PRIVATE_KEY_PATH" in env:
        assert "JWT_PRIVATE_KEY" not in env
    assert not any("secretKeyRef" in item.get("valueFrom", {}) for item in env_items)


def test_external_application_secret_maps_mfa_keys_to_authorized_workloads() -> None:
    overrides = [
        "--set",
        f"applicationSecrets.existingSecret={MFA_EXTERNAL_APPLICATION_SECRET}",
        "--set-string",
        f"backend.config.mfaTotpActiveEncryptionKeyId={MFA_TOTP_ACTIVE_KEY_ID}",
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

    application_secret_helper = (CHART / "templates" / "_helpers.tpl").read_text(
        encoding="utf-8"
    )
    assert (
        'default (printf "%s-secrets" .Release.Name) '
        ".Values.applicationSecrets.existingSecret"
    ) in application_secret_helper
    application_secret_names = {
        f"{MFA_HELM_RELEASE_NAME}-secrets",
        MFA_EXTERNAL_APPLICATION_SECRET,
    }
    secret_resources = [
        resource for resource in resources if resource.get("kind") == "Secret"
    ]
    assert not any(
        resource.get("metadata", {}).get("name") in application_secret_names
        for resource in secret_resources
    )
    chart_values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    assert chart_values["nats"]["natsBox"]["enabled"] is False
    assert not secret_resources
    backend_spec, backend_container = _deployment_pod_and_container(
        resources, "backend"
    )
    backend_env = {item["name"]: item for item in backend_container["env"]}
    for variable, secret_key in MFA_SECRET_KEYS.items():
        file_variable = f"{variable}_FILE"
        assert backend_env[file_variable]["value"] == (
            f"/run/secrets/{MFA_EXTERNAL_APPLICATION_SECRET}/{secret_key}"
        )
        assert "valueFrom" not in backend_env[file_variable]
        assert variable not in backend_env
    assert backend_env["MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID"]["value"] == (
        MFA_TOTP_ACTIVE_KEY_ID
    )
    assert "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE" not in backend_env

    connection_secret = "university-connections"
    assert _secret_volume_names(backend_spec) == {
        "secret-application",
        "secret-connections",
    }
    backend_application_items = _projected_secret_items(
        backend_spec,
        backend_container,
        volume_name="secret-application",
        secret_name=MFA_EXTERNAL_APPLICATION_SECRET,
    )
    assert set(MFA_SECRET_KEYS.values()) <= set(backend_application_items)
    _projected_secret_items(
        backend_spec,
        backend_container,
        volume_name="secret-connections",
        secret_name=connection_secret,
    )

    outbox_spec, outbox_container = _deployment_pod_and_container(
        resources, "outbox-worker"
    )
    outbox_env = {item["name"]: item for item in outbox_container["env"]}
    delivery_variable = "MFA_EMAIL_DELIVERY_KEKS"
    delivery_file_variable = f"{delivery_variable}_FILE"
    assert outbox_env[delivery_file_variable]["value"] == (
        f"/run/secrets/{MFA_EXTERNAL_APPLICATION_SECRET}/"
        f"{MFA_SECRET_KEYS[delivery_variable]}"
    )
    assert "valueFrom" not in outbox_env[delivery_file_variable]
    assert delivery_variable not in outbox_env
    for variable in set(MFA_SECRET_KEYS) - {delivery_variable}:
        assert variable not in outbox_env
        assert f"{variable}_FILE" not in outbox_env

    assert _secret_volume_names(outbox_spec) == {
        "secret-application",
        "secret-connections",
    }
    outbox_application_items = _projected_secret_items(
        outbox_spec,
        outbox_container,
        volume_name="secret-application",
        secret_name=MFA_EXTERNAL_APPLICATION_SECRET,
    )
    assert MFA_SECRET_KEYS[delivery_variable] in outbox_application_items
    assert (
        set(MFA_SECRET_KEYS.values()) - {MFA_SECRET_KEYS[delivery_variable]}
    ).isdisjoint(outbox_application_items)
    _projected_secret_items(
        outbox_spec,
        outbox_container,
        volume_name="secret-connections",
        secret_name=connection_secret,
    )

    migration = next(
        resource
        for resource in resources
        if resource.get("kind") == "Job"
        and resource["metadata"]["name"].endswith("-migrate")
    )
    migration_spec = migration["spec"]["template"]["spec"]
    migration_container = migration_spec["containers"][0]
    migration_env = {item["name"]: item for item in migration_container["env"]}
    assert migration_env["APP_PROCESS_ROLE"]["value"] == "api"
    assert migration_env["MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID"]["value"] == (
        MFA_TOTP_ACTIVE_KEY_ID
    )
    assert migration_env["MFA_TOTP_ENCRYPTION_KEYS_FILE"]["value"] == (
        f"/run/secrets/{MFA_EXTERNAL_APPLICATION_SECRET}/"
        f"{MFA_SECRET_KEYS['MFA_TOTP_ENCRYPTION_KEYS']}"
    )
    migration_application_items = _projected_secret_items(
        migration_spec,
        migration_container,
        volume_name="secret-application",
        secret_name=MFA_EXTERNAL_APPLICATION_SECRET,
    )
    assert MFA_SECRET_KEYS["MFA_TOTP_ENCRYPTION_KEYS"] in migration_application_items


def test_outbox_worker_rejects_totp_env_injection_from_values() -> None:
    overrides = [
        "--set",
        f"applicationSecrets.existingSecret={MFA_EXTERNAL_APPLICATION_SECRET}",
        "--set-string",
        f"backend.config.mfaTotpActiveEncryptionKeyId={MFA_TOTP_ACTIVE_KEY_ID}",
    ]
    for variable, value_key in MFA_VALUE_KEYS.items():
        overrides.extend(
            (
                "--set-string",
                f"applicationSecrets.keys.{value_key}={MFA_SECRET_KEYS[variable]}",
            )
        )
    for variable in (
        "MFA_TOTP_ENCRYPTION_KEYS",
        "MFA_TOTP_ENCRYPTION_KEYS_FILE",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE",
    ):
        overrides.extend(("--set-string", f"outboxWorker.env.{variable}=injected"))

    resources = _render(*overrides)
    worker_env = _deployment_env(resources, "outbox-worker")

    assert {
        "MFA_TOTP_ENCRYPTION_KEYS",
        "MFA_TOTP_ENCRYPTION_KEYS_FILE",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID",
        "MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID_FILE",
    }.isdisjoint(worker_env)


def test_mfa_values_schema_requires_valid_parameterized_secret_key_names() -> None:
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    key_schema = schema["properties"]["applicationSecrets"]["properties"]["keys"]

    assert set(MFA_VALUE_KEYS.values()) <= set(key_schema["required"])
    assert "mfaTotpActiveEncryptionKeyId" not in key_schema["required"]
    assert "mfaTotpActiveEncryptionKeyId" not in key_schema["properties"]
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
            f"backend.config.mfaTotpActiveEncryptionKeyId={MFA_TOTP_ACTIVE_KEY_ID}",
            "--set-string",
            f"global.environment={environment}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    normalized_error = result.stderr.lower().replace(".", "/")
    assert "global/environment" in normalized_error


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(
    "config_field",
    ["mfaEmailOtpHMACKeys", "mfaTotpEncryptionKeys"],
)
def test_non_development_render_rejects_inline_mfa_key_material(
    environment: str, config_field: str
) -> None:
    issuer_kind = "Issuer" if environment == "staging" else "ClusterIssuer"
    result = subprocess.run(  # noqa: S603 - fixed Helm contract command
        [
            *_base_args(),
            "--set",
            f"global.environment={environment}",
            "--set-string",
            f"ingress.issuer.kind={issuer_kind}",
            "--set",
            "applicationSecrets.existingSecret=eso-application-secret",
            "--set",
            "backend.config.minioSecure=true",
            "--set",
            "gateway.config.grpcUseTLS=true",
            "--set-string",
            f"backend.config.{config_field}=active:inline-material",
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
        "--set-string",
        f"backend.config.mfaTotpActiveEncryptionKeyId={MFA_TOTP_ACTIVE_KEY_ID}",
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
    assert "totp-active-custom" not in application_keys
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
        "totp": {
            "ring": MFA_SECRET_KEYS["MFA_TOTP_ENCRYPTION_KEYS"],
            "active": MFA_TOTP_ACTIVE_KEY_ID,
        },
    }

    workload_contracts = {
        "backend": set(json.loads(contract["data"]["backend-secret-keys.json"])),
        "outbox-worker": set(
            json.loads(contract["data"]["outbox-worker-secret-keys.json"])
        ),
    }
    chart_values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    connections = chart_values["connections"]
    connection_workload_contracts = {
        "backend": {
            connections["databaseURLKey"],
            connections["redisBackendURLKey"],
            connections["rateLimitStorageURIKey"],
            connections["redisRevocationURLKey"],
            connections["natsURLKey"],
            connections["natsAuthTokenKey"],
        },
        "outbox-worker": {
            connections["databaseURLKey"],
            connections["redisBackendURLKey"],
            connections["natsURLKey"],
            connections["natsAuthTokenKey"],
        },
    }
    application_secret = contract["data"]["application-secret-name"]
    connection_secret = contract["data"]["connection-secret-name"]
    for component, expected_application_keys in workload_contracts.items():
        pod_spec, container = _deployment_pod_and_container(resources, component)
        if component == "outbox-worker":
            assert not any(
                item["name"].startswith("RATE_LIMIT_STORAGE_")
                for item in container["env"]
            )
        assert _secret_volume_names(pod_spec) == {
            "secret-application",
            "secret-connections",
        }
        application_items = _projected_secret_items(
            pod_spec,
            container,
            volume_name="secret-application",
            secret_name=application_secret,
        )
        assert application_items == {key: key for key in expected_application_keys}

        expected_connection_keys = connection_workload_contracts[component]
        assert expected_connection_keys <= connection_keys
        connection_items = _projected_secret_items(
            pod_spec,
            container,
            volume_name="secret-connections",
            secret_name=connection_secret,
        )
        assert connection_items == {key: key for key in expected_connection_keys}

        expected_secret_paths = {
            f"/run/secrets/{application_secret}/{key}"
            for key in expected_application_keys
        } | {
            f"/run/secrets/{connection_secret}/{key}"
            for key in expected_connection_keys
        }
        _assert_file_secret_environment(container, expected_secret_paths)


def test_chart_patch_version_documents_the_mfa_secret_contract_upgrade() -> None:
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    # 0.2.1 introduced the parameterized MFA Secret contract; later patches retain it.
    assert tuple(int(part) for part in chart["version"].split(".")) >= (0, 2, 1)


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
    assert any(image.startswith("docker.io/redis@") for image in dependency_images)
    assert any(
        image.startswith("docker.io/oliver006/redis_exporter@")
        for image in dependency_images
    )
    assert any(image.startswith("docker.io/nats@") for image in dependency_images)
    assert not any(
        image.startswith("ghcr.io/example/university/") for image in dependency_images
    )


def test_deploy_renderer_executes_canonical_staging_without_required_markers(
    tmp_path: Path,
) -> None:
    bash = _bash()
    digest = f"sha256:{'a' * 64}"
    staging_values = yaml.safe_load(
        (CHART / "values-staging.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(staging_values, dict)
    staging_values["backend"]["config"]["mfaTotpActiveEncryptionKeyId"] = (
        MFA_TOTP_ACTIVE_KEY_ID
    )
    network_policy = staging_values.setdefault("networkPolicy", {})
    assert isinstance(network_policy, dict)
    gateway_jwks = network_policy.setdefault("gatewayJWKS", {})
    assert isinstance(gateway_jwks, dict)
    # Reserved TEST-NET only, provided through the existing values-file input.
    gateway_jwks["egressCIDRs"] = ["192.0.2.0/24"]
    # Reserved TEST-NET/documentation proxy peers are fixture-only.
    staging_values["gateway"]["config"]["trustedProxies"] = [
        "192.0.2.11/32",
        "2001:db8::11",
    ]
    staging_values["wsHub"]["config"]["trustedProxies"] = [
        "198.51.100.12/32",
        "2001:db8::12",
    ]
    staging_values_path = tmp_path / "values-staging-render-contract.yaml"
    staging_values_path.write_text(
        yaml.safe_dump(staging_values, sort_keys=False), encoding="utf-8"
    )
    environment = {
        **os.environ,
        "DEPLOY_ENVIRONMENT": "staging",
        "K8S_NAMESPACE": "university-ecosystem",
        "HELM_RELEASE_NAME": "staging-execution-contract",
        "HELM_VALUES_FILE": str(staging_values_path),
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
