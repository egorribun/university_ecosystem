"""Helm contracts for the backend's dedicated Redis rate-limit store."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import (
    _helm,
    _render_staging,
    _resolved_staging_args,
)
from tests.test_mfa_helm_contract import MFA_EXTERNAL_APPLICATION_SECRET, _render

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"


def _render_development(*extra: str) -> list[dict[str, Any]]:
    return _render(
        "--set",
        f"applicationSecrets.existingSecret={MFA_EXTERNAL_APPLICATION_SECRET}",
        *extra,
    )


def _backend(resources: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    deployment = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == "backend"
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    env = [item["name"] for item in container["env"]]
    assert len(env) == len(set(env)), "backend env contains duplicate names"
    return pod_spec, container


def test_backend_uses_dedicated_rate_limit_connection_secret_file() -> None:
    key_name = "python-rate-limit-uri"
    resources = _render_staging(
        "--set",
        "deploymentContract.enabled=true",
        "--set-string",
        f"connections.rateLimitStorageURIKey={key_name}",
        release_name="rate-limit-contract",
    )

    pod_spec, container = _backend(resources)
    env = {item["name"]: item for item in container["env"]}
    assert env["RATE_LIMIT_STORAGE_BACKEND"]["value"] == "redis"
    assert env["RATE_LIMIT_STORAGE_URI_FILE"]["value"] == (
        f"/run/secrets/university-connections/{key_name}"
    )
    assert "RATE_LIMIT_STORAGE_URI" not in env

    connection_volume = next(
        volume
        for volume in pod_spec["volumes"]
        if volume.get("secret", {}).get("secretName") == "university-connections"
    )
    projected_keys = {
        item["key"] for item in connection_volume["secret"].get("items", [])
    }
    assert key_name in projected_keys

    contract = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == "deployment-contract"
    )
    connection_keys = json.loads(contract["data"]["connection-secret-keys.json"])
    assert key_name in connection_keys
    assert "redis-gateway-url" in connection_keys
    assert key_name != "redis-gateway-url"


def test_development_env_cannot_override_rate_limit_store_contract() -> None:
    resources = _render_development(
        "--set-string",
        "backend.env.RATE_LIMIT_STORAGE_BACKEND=memory",
        "--set-string",
        "backend.env.RATE_LIMIT_STORAGE_URI=memory://override",
        "--set-string",
        "backend.env.RATE_LIMIT_STORAGE_URI_FILE=/run/secrets/untrusted-rate-limit-uri",
    )

    _, container = _backend(resources)
    env = {item["name"]: item for item in container["env"]}
    assert env["RATE_LIMIT_STORAGE_BACKEND"]["value"] == "redis"
    assert env["RATE_LIMIT_STORAGE_URI_FILE"]["value"] == (
        "/run/secrets/university-connections/rate-limit-storage-uri"
    )
    assert "RATE_LIMIT_STORAGE_URI" not in env


@pytest.mark.parametrize(
    ("override_name", "override_value"),
    [
        ("rate_limit_storage_backend", "memory"),
        ("rAtE_LiMiT_sToRaGe_BaCkEnD", "memory"),
        ("rate_limit_storage_uri", "memory://override"),
        ("rAtE_LiMiT_sToRaGe_uRi", "memory://override"),
        ("rate_limit_storage_uri_file", "/run/secrets/untrusted-rate-limit-uri"),
        ("rAtE_LiMiT_sToRaGe_uRi_fIlE", "/run/secrets/untrusted-rate-limit-uri"),
    ],
)
def test_rate_limit_env_case_variants_are_dropped_but_other_env_is_kept(
    override_name: str, override_value: str
) -> None:
    resources = _render_development(
        "--set-string",
        f"backend.env.{override_name}={override_value}",
        "--set-string",
        "backend.env.ENVIRONMENT=production",
        "--set-string",
        "backend.env.CUSTOM_FEATURE_FLAG=retained",
    )

    _, container = _backend(resources)
    env = {item["name"]: item for item in container["env"]}

    assert override_name not in env
    assert env["RATE_LIMIT_STORAGE_BACKEND"]["value"] == "redis"
    assert env["RATE_LIMIT_STORAGE_URI_FILE"]["value"] == (
        "/run/secrets/university-connections/rate-limit-storage-uri"
    )
    assert "RATE_LIMIT_STORAGE_URI" not in env
    assert env["ENVIRONMENT"]["value"] == "development"
    assert env["CUSTOM_FEATURE_FLAG"]["value"] == "retained"


@pytest.mark.parametrize(
    "existing_key",
    [
        "database-url",
        "redis-backend-url",
        "redis-gateway-url",
        "redis-revocation-url",
        "nats-url",
        "nats-auth-token",
        "keda-postgresql-url",
        "backup-database-url",
    ],
)
def test_rate_limit_connection_key_cannot_reuse_existing_connection_secret_key(
    existing_key: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "rate-limit-key-collision-contract",
            str(CHART),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            "--set-string",
            f"connections.rateLimitStorageURIKey={existing_key}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "connections.rateLimitStorageURIKey must use a dedicated" in result.stderr


def test_rate_limit_connection_key_must_be_nonempty() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "rate-limit-empty-key-contract",
            str(CHART),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            "--set-string",
            "connections.rateLimitStorageURIKey=",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    # The values schema rejects the empty key before any template runs, and
    # Helm reports schema violations by JSON pointer path.
    assert result.returncode != 0
    assert "/connections/rateLimitStorageURIKey" in result.stderr


def _shared_settings_workload(
    resources: list[dict[str, Any]], workload: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    resource = next(
        item
        for item in resources
        if item.get("kind") == ("Job" if workload == "migration" else "Deployment")
        and item.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == workload
    )
    pod_spec = resource["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    names = [item["name"] for item in container["env"]]
    assert len(names) == len(set(names)), f"{workload} env contains duplicate names"
    return pod_spec, container


@pytest.mark.parametrize("workload", ["migration", "outbox-worker"])
@pytest.mark.parametrize(
    "key_name", ["rate-limit-storage-uri", "python-rate-limit-uri"]
)
def test_shared_settings_workloads_project_dedicated_rate_limit_secret(
    workload: str, key_name: str
) -> None:
    overrides = (
        ("--set-string", f"connections.rateLimitStorageURIKey={key_name}")
        if key_name != "rate-limit-storage-uri"
        else ()
    )
    resources = _render_staging(
        *overrides,
        release_name="shared-settings-rate-limit-contract",
    )
    pod_spec, container = _shared_settings_workload(resources, workload)
    env = {item["name"]: item for item in container["env"]}

    assert env["ENVIRONMENT"]["value"] == "staging"
    assert env["RATE_LIMIT_STORAGE_BACKEND"] == {
        "name": "RATE_LIMIT_STORAGE_BACKEND",
        "value": "redis",
    }
    assert env["RATE_LIMIT_STORAGE_URI_FILE"] == {
        "name": "RATE_LIMIT_STORAGE_URI_FILE",
        "value": f"/run/secrets/university-connections/{key_name}",
    }
    assert "RATE_LIMIT_STORAGE_URI" not in env
    connection_volume = next(
        volume
        for volume in pod_spec["volumes"]
        if volume.get("secret", {}).get("secretName") == "university-connections"
    )
    projected_keys = {item["key"] for item in connection_volume["secret"]["items"]}
    expected_keys = {
        "database-url",
        "redis-backend-url",
        "nats-auth-token",
        key_name,
        "redis-revocation-url" if workload == "migration" else "nats-url",
    }
    assert projected_keys == expected_keys
    assert pod_spec["automountServiceAccountToken"] is False
    if workload == "migration":
        assert env["APP_PROCESS_ROLE"]["value"] == "api"
        assert env["REVOCATION_REDIS_ACCESS_ENABLED"]["value"] == "true"
        assert "redis-revocation-url" in projected_keys
        assert "REVOCATION_REDIS_URL_FILE" in env
        assert "serviceAccountName" not in pod_spec
    else:
        assert env["APP_PROCESS_ROLE"]["value"] == "outbox-worker"
        assert env["REVOCATION_REDIS_ACCESS_ENABLED"]["value"] == "false"
        assert "redis-revocation-url" not in projected_keys
        assert "REVOCATION_REDIS_URL_FILE" not in env
        assert "REVOCATION_REDIS_URL" not in env
        assert pod_spec["serviceAccountName"] == (
            "shared-settings-rate-limit-contract-outbox-worker"
        )


def test_outbox_env_cannot_override_shared_rate_limit_store_contract() -> None:
    overrides: list[str] = []
    names = (
        "RATE_LIMIT_STORAGE_BACKEND",
        "RATE_LIMIT_STORAGE_URI",
        "RATE_LIMIT_STORAGE_URI_FILE",
        "rate_limit_storage_backend",
        "rate_limit_storage_uri",
        "rate_limit_storage_uri_file",
        "rAtE_LiMiT_sToRaGe_BaCkEnD",
        "rAtE_LiMiT_sToRaGe_uRi",
        "rAtE_LiMiT_sToRaGe_uRi_fIlE",
    )
    for name in names:
        overrides.extend(("--set-string", f"outboxWorker.env.{name}=untrusted"))
    overrides.extend(
        ("--set-string", "outboxWorker.env.CUSTOM_FEATURE_FLAG=retained")
    )
    resources = _render_development(*overrides)
    _, container = _shared_settings_workload(resources, "outbox-worker")
    env = {item["name"]: item for item in container["env"]}

    assert env["RATE_LIMIT_STORAGE_BACKEND"]["value"] == "redis"
    assert env["RATE_LIMIT_STORAGE_URI_FILE"]["value"] == (
        "/run/secrets/university-connections/rate-limit-storage-uri"
    )
    assert "RATE_LIMIT_STORAGE_URI" not in env
    assert not any(name in env for name in names[3:])
    assert env["CUSTOM_FEATURE_FLAG"]["value"] == "retained"
