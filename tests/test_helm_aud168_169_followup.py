from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import (
    _render_staging,
    _values,
)

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"


@pytest.fixture(scope="module")
def release_resources() -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    release_name = "aud168-169-contract"
    values = _values(STAGING_VALUES)
    values["connections"] = {
        **_values(CHART / "values.yaml")["connections"],
        **values["connections"],
    }
    elasticsearch_url = "https://aud168-169.elasticsearch.staging.internal"
    values["backend"]["config"]["elasticsearchURL"] = elasticsearch_url
    return (
        release_name,
        values,
        _render_staging(
            "--set-string",
            f"backend.config.elasticsearchURL={elasticsearch_url}",
            release_name=release_name,
        ),
    )


def _migration_pod_and_container(
    resources: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = next(
        resource
        for resource in resources
        if resource.get("kind") == "Job"
        and resource["metadata"]["name"].endswith("-migrate")
    )
    pod_spec = job["spec"]["template"]["spec"]
    container = next(
        item for item in pod_spec["containers"] if item["name"] == "migrate"
    )
    return pod_spec, container


def _job_environment(resources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    _, container = _migration_pod_and_container(resources)
    return {item["name"]: item for item in container["env"]}


def _assert_projected_secret(
    pod_spec: dict[str, Any],
    container: dict[str, Any],
    *,
    volume_name: str,
    secret_name: str,
    expected_keys: set[str],
) -> None:
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
    assert len(items) == len(expected_keys)
    assert {item["key"]: item["path"] for item in items} == {
        key: key for key in expected_keys
    }

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


def test_migration_settings_use_release_environment_and_required_secrets(
    release_resources: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> None:
    release_name, values, resources = release_resources
    pod_spec, container = _migration_pod_and_container(resources)
    environment = {item["name"]: item for item in container["env"]}
    application_secret = values["applicationSecrets"]["existingSecret"] or (
        f"{release_name}-secrets"
    )
    connection_secret = values["connections"]["existingSecret"]

    assert environment["ENVIRONMENT"]["value"] == values["global"]["environment"]
    assert environment["APP_PROCESS_ROLE"]["value"] == "api"
    assert environment["REVOCATION_REDIS_ACCESS_ENABLED"]["value"] == "true"
    assert environment["AUTO_CREATE_SCHEMA"]["value"] == "false"
    assert "CI" not in environment
    assert "GITHUB_ACTIONS" not in environment
    assert (
        environment["EVENT_FILE_SCANNER_ENABLED"]["value"]
        == str(values["backend"]["config"]["eventFileScannerEnabled"]).lower()
    )
    assert (
        environment["MINIO_SECURE"]["value"]
        == str(values["backend"]["config"]["minioSecure"]).lower()
    )
    assert (
        environment["ELASTICSEARCH_URL"]["value"]
        == values["backend"]["config"]["elasticsearchURL"]
    )

    application_key_references = (
        ("SECRET_KEY", "jwt-secret"),
        ("AUDIT_LOG_SECRET", "audit-log-secret"),
        ("ELASTICSEARCH_PASSWORD", "elasticsearch-password"),
        ("INTERNAL_AUTH_TOKEN", "ws-hub-internal-secret"),
        ("INTERNAL_HMAC_SECRET", "internal-hmac-secret"),
        ("SPICEDB_PRESHARED_KEY", "spicedb-preshared-key"),
        ("SPOTIFY_TOKEN_SECRET", "spotify-token-secret"),
        ("TOKEN_HMAC_SECRET", "token-hmac-secret"),
        ("WS_HUB_INTERNAL_SECRET", "ws-hub-internal-secret"),
    )
    expected_application_keys = {key for _, key in application_key_references}
    for environment_name, expected_key in application_key_references:
        file_env = environment[f"{environment_name}_FILE"]
        assert file_env["value"] == f"/run/secrets/{application_secret}/{expected_key}"
        assert "valueFrom" not in file_env
        assert environment_name not in environment

    connection_secret_keys = {
        "DATABASE_URL": values["connections"]["databaseURLKey"],
        "CACHE_REDIS_URL": values["connections"]["redisBackendURLKey"],
        "REVOCATION_REDIS_URL": values["connections"]["redisRevocationURLKey"],
        "NATS_AUTH_TOKEN": values["connections"]["natsAuthTokenKey"],
    }
    for environment_name, secret_key in connection_secret_keys.items():
        file_env = environment[f"{environment_name}_FILE"]
        assert file_env["value"] == f"/run/secrets/{connection_secret}/{secret_key}"
        assert "valueFrom" not in file_env
        assert environment_name not in environment

    expected_secret_volumes = {"secret-application", "secret-connections"}
    assert {
        volume["name"] for volume in pod_spec.get("volumes", []) if "secret" in volume
    } == expected_secret_volumes
    assert {
        mount["name"]
        for mount in container.get("volumeMounts", [])
        if mount["name"] in expected_secret_volumes
    } == expected_secret_volumes
    _assert_projected_secret(
        pod_spec,
        container,
        volume_name="secret-application",
        secret_name=application_secret,
        expected_keys=expected_application_keys,
    )
    _assert_projected_secret(
        pod_spec,
        container,
        volume_name="secret-connections",
        secret_name=connection_secret,
        expected_keys=set(connection_secret_keys.values()),
    )
    assert not any(
        "secretKeyRef" in item.get("valueFrom", {}) for item in container["env"]
    )
    expected_file_paths = {
        f"/run/secrets/{application_secret}/{key}" for key in expected_application_keys
    } | {
        f"/run/secrets/{connection_secret}/{key}"
        for key in connection_secret_keys.values()
    }
    actual_file_paths = {
        item.get("value")
        for item in container["env"]
        if item["name"].endswith("_FILE") or item["name"] == "JWT_PRIVATE_KEY_PATH"
    }
    assert actual_file_paths == expected_file_paths


def _egress_signature(rule: dict[str, Any]) -> tuple[Any, ...]:
    destinations = tuple(
        sorted(
            tuple(sorted(destination["podSelector"]["matchLabels"].items()))
            for destination in rule.get("to", [])
            if "podSelector" in destination
        )
    )
    ip_blocks = tuple(
        sorted(
            destination["ipBlock"]["cidr"]
            for destination in rule.get("to", [])
            if "ipBlock" in destination
        )
    )
    ports = tuple(
        sorted((port["protocol"], int(port["port"])) for port in rule["ports"])
    )
    return destinations, ip_blocks, ports


def test_file_processor_revocation_egress_is_release_scoped(
    release_resources: tuple[str, dict[str, Any], list[dict[str, Any]]],
) -> None:
    release_name, _, resources = release_resources
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == "file-processor"
    )
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert pod_labels[f"{release_name}-nats-client"] == "true"
    assert pod_labels[f"{release_name}-revocation-redis-client"] == "true"

    policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-file-processor-policy"
    )
    revocation_selector = (
        ("app.kubernetes.io/component", "master"),
        ("app.kubernetes.io/name", "revocation-redis"),
        ("university-ecosystem.io/revocation-store-for", release_name),
    )
    backend_selector = tuple(
        sorted(
            {
                "app.kubernetes.io/component": "backend",
                "app.kubernetes.io/name": pod_labels["app.kubernetes.io/name"],
                "app.kubernetes.io/instance": pod_labels["app.kubernetes.io/instance"],
            }.items()
        )
    )
    signatures = {_egress_signature(rule) for rule in policy["spec"]["egress"]}
    assert len(signatures) == len(policy["spec"]["egress"])
    assert signatures == {
        (((("app.kubernetes.io/name", "nats"),),), (), (("TCP", 4222),)),
        (((("app.kubernetes.io/name", "temporal"),),), (), (("TCP", 7233),)),
        (((("app.kubernetes.io/name", "minio"),),), (), (("TCP", 9000),)),
        ((revocation_selector,), (), (("TCP", 6379),)),
        ((backend_selector,), (), (("TCP", 8000),)),
        (((("app.kubernetes.io/name", "otel-collector"),),), (), (("TCP", 4317),)),
        ((), (), (("TCP", 443),)),
        ((), (), (("TCP", 53), ("UDP", 53))),
    }
