"""Production-like staging contracts for the University Ecosystem Helm chart."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_gateway_api_helm_contract import _render_gateway_template_isolated

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"
REVOCATION_STORE_CHART = ROOT / "charts" / "revocation-store"
REVOCATION_STORE_VALUES = REVOCATION_STORE_CHART / "values-staging.yaml"
MFA_TOTP_ACTIVE_KEY_ID = "totp-active-staging-contract"


def _values(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _helm() -> str:
    executable = shutil.which("helm")
    if executable is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun
    return executable


def _resolved_staging_args(gateway_jwks_cidr: str | None = "192.0.2.0/24") -> list[str]:
    digest = "sha256:" + ("a" * 64)
    overrides = {
        "global.imageTag": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
        "global.jwtIssuer": "https://api.university.staging.example.org",
        "backend.image.repository": "ghcr.io/example/university/backend",
        "backend.image.digest": digest,
        "frontend.image.repository": "ghcr.io/example/university/frontend",
        "frontend.image.digest": digest,
        "gateway.image.repository": "ghcr.io/example/university/gateway",
        "gateway.image.digest": digest,
        "wsHub.image.repository": "ghcr.io/example/university/ws-hub",
        "wsHub.image.digest": digest,
        "fileProcessor.image.repository": ("ghcr.io/example/university/file-processor"),
        "fileProcessor.image.digest": digest,
        "outboxWorker.image.repository": "ghcr.io/example/university/backend",
        "outboxWorker.image.digest": digest,
        "redis.image.digest": digest,
        "redis.metrics.image.digest": digest,
        "global.backendImageDigest": digest,
        "redis.metrics.passwordFileInitImage.repository": "ghcr.io/example/university/backend",
        "redis.metrics.passwordFileInitImage.digest": digest,
        "nats.image.digest": digest,
        "nats.container.image.digest": digest,
        "backend.config.elasticsearchURL": "https://elasticsearch.staging.internal",
        "backend.config.flagdHost": "flagd.staging.internal",
        "backend.config.storageS3EndpointURL": ("https://minio.staging.internal:443"),
        "backend.config.mfaTotpActiveEncryptionKeyId": MFA_TOTP_ACTIVE_KEY_ID,
        "gateway.config.otelEndpoint": "otel-collector.staging.internal:4317",
        "fileProcessor.config.minioEndpoint": "minio.staging.internal:443",
        "fileProcessor.config.temporalHost": "temporal.staging.internal:7233",
        "fileProcessor.config.otlpEndpoint": "otel-collector.staging.internal:4317",
        "ingress.hosts[0].host": "university.staging.example.org",
        "ingress.hosts[1].host": "api.university.staging.example.org",
        "ingress.tls[0].hosts[0]": "university.staging.example.org",
        "ingress.tls[0].hosts[1]": "api.university.staging.example.org",
        "wsHub.config.allowedOrigins[0]": "https://university.staging.example.org",
        "wsHub.config.otelEndpoint": "otel-collector.staging.internal:4317",
        "cwv.releaseSHA": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
        "cwv.frontendImageDigest": digest,
        "cwv.deploymentURL": "https://university.staging.example.org",
        "cwv.deployedAt": "2026-08-26T00:00:00Z",
        "cwv.allowedOrigins[0]": "https://university.staging.example.org",
        "cwv.exportOIDC.repository": "example/university-ecosystem",
        "cwv.exportOIDC.workflowRef": "example/university-ecosystem/.github/workflows/cwv-field-certification.yml@refs/heads/main",
        "cwv.exportOIDC.subject": "repo:example/university-ecosystem:environment:staging",
    }
    overrides["redis.metrics.passwordFileInitImage.tag"] = overrides["global.imageTag"]
    if gateway_jwks_cidr is not None:
        # Reserved TEST-NET fixture only; never use as a deployment CIDR.
        overrides["networkPolicy.gatewayJWKS.egressCIDRs[0]"] = gateway_jwks_cidr
    args: list[str] = []
    for key, value in overrides.items():
        args.extend(("--set-string", f"{key}={value}"))
    # These reserved TEST-NET/documentation peers are complete synthetic lists,
    # not partial indexed overrides of deployment values.
    for key, peers in (
        ("gateway.config.trustedProxies", ["192.0.2.11/32", "2001:db8::11"]),
        ("wsHub.config.trustedProxies", ["198.51.100.12/32", "2001:db8::12"]),
    ):
        encoded_peers = json.dumps(peers, separators=(",", ":"))
        args.extend(("--set-json", f"{key}={encoded_peers}"))
    args.extend(("--set", "cwv.deploymentRunID=123"))
    args.extend(("--set", "cwv.deploymentRunAttempt=1"))
    return args


def _render_staging(
    *extra: str,
    release_name: str = "staging-contract",
    gateway_jwks_cidr: str | None = "192.0.2.0/24",
    chart_path: Path = CHART,
    values_path: Path = STAGING_VALUES,
) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            release_name,
            str(chart_path),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(values_path),
            *_resolved_staging_args(gateway_jwks_cidr),
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


def test_chart_requires_explicit_environment() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "environment-required-contract",
            str(CHART),
            "--dependency-update=false",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    error = result.stderr.lower()
    assert "global" in error
    assert "environment" in error
    assert "required" in error or "missing property" in error


def test_release_gateway_uses_tls_for_jwks_and_routes_discovery_to_backend() -> None:
    """Release gateways must never fetch signing keys over plaintext HTTP."""

    resources = _render_staging(release_name="jwks-transport-contract")
    gateway = next(
        resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource["metadata"]["name"].endswith("-gateway")
    )
    gateway_env = {
        item["name"]: item["value"]
        for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]
        if "value" in item
    }
    assert gateway_env["JWKS_ENDPOINT"] == (
        "https://api.university.staging.example.org/.well-known/jwks.json"
    )

    ingress = next(
        resource for resource in resources if resource.get("kind") == "Ingress"
    )
    api_rule = next(
        rule
        for rule in ingress["spec"]["rules"]
        if rule["host"] == "api.university.staging.example.org"
    )
    discovery_route = next(
        path for path in api_rule["http"]["paths"] if path["path"] == "/.well-known"
    )
    assert discovery_route["pathType"] == "Prefix"
    assert discovery_route["backend"]["service"]["name"].endswith("-backend")

    gateway_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == "jwks-transport-contract-gateway-policy"
    )
    jwks_egress = [
        rule
        for rule in gateway_policy["spec"]["egress"]
        if rule.get("ports") == [{"protocol": "TCP", "port": 443}]
    ]
    assert jwks_egress == [
        {
            "to": [{"ipBlock": {"cidr": "192.0.2.0/24"}}],
            "ports": [{"protocol": "TCP", "port": 443}],
        }
    ]
    assert any(
        rule.get("to")
        == [
            {
                "namespaceSelector": {
                    "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                },
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }
        ]
        and rule.get("ports")
        == [
            {"protocol": "UDP", "port": 53},
            {"protocol": "TCP", "port": 53},
        ]
        for rule in gateway_policy["spec"]["egress"]
    )
    assert any(
        rule.get("to")
        == [
            {"podSelector": {"matchLabels": {"app.kubernetes.io/component": "backend"}}}
        ]
        and rule.get("ports") == [{"protocol": "TCP", "port": 8000}]
        for rule in gateway_policy["spec"]["egress"]
    )

    backend_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == "jwks-transport-contract-backend-policy"
    )
    ingress_controller_rule = next(
        rule
        for rule in backend_policy["spec"]["ingress"]
        if any(
            source.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/name")
            == "ingress-nginx"
            for source in rule.get("from", [])
        )
    )
    assert ingress_controller_rule["ports"] == [{"protocol": "TCP", "port": 8000}]


def test_development_gateway_uses_internal_jwks_without_external_cidrs() -> None:
    resources = _render_staging(
        "--set-string",
        "global.environment=development",
        "--set-string",
        "global.jwtIssuer=university-ecosystem",
        release_name="jwks-internal-contract",
        gateway_jwks_cidr=None,
    )
    gateway = _component_resource(resources, "Deployment", "gateway")
    gateway_env = {
        item["name"]: item.get("value")
        for item in gateway["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert gateway_env["JWKS_ENDPOINT"] == (
        "http://university-ecosystem-backend:8000/.well-known/jwks.json"
    )
    policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"].endswith("-gateway-policy")
    )
    assert not any(
        port.get("port") == 443
        for rule in policy["spec"]["egress"]
        for port in rule.get("ports", [])
    )
    assert any(
        rule.get("to")
        == [
            {"podSelector": {"matchLabels": {"app.kubernetes.io/component": "backend"}}}
        ]
        and rule.get("ports") == [{"protocol": "TCP", "port": 8000}]
        for rule in policy["spec"]["egress"]
    )


def test_release_gateway_requires_explicit_jwks_cidrs() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(
            release_name="jwks-cidr-required-contract",
            gateway_jwks_cidr=None,
        )

    assert "networkpolicy.gatewayjwks.egresscidrs" in error.value.stderr.lower()
    assert "owner-verified" in error.value.stderr.lower()


@pytest.mark.parametrize(
    "cidr",
    [
        "::/128",
        "2001:db8::/32",
        "2001:db8:0:0:0:0:0:1/128",
    ],
)
def test_release_gateway_accepts_valid_ipv6_jwks_cidrs(cidr: str) -> None:
    release_name = "jwks-ipv6-cidr-valid-contract"
    resources = _render_staging(
        "--set-string",
        f"networkPolicy.gatewayJWKS.egressCIDRs[0]={cidr}",
        release_name=release_name,
    )
    policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-gateway-policy"
    )
    assert any(
        rule.get("to") == [{"ipBlock": {"cidr": cidr}}]
        and rule.get("ports") == [{"protocol": "TCP", "port": 443}]
        for rule in policy["spec"]["egress"]
    )


@pytest.mark.parametrize(
    "cidr",
    [
        "0.0.0.0/0",
        "::/0",
        "2001:db8::/129",
        "not-a-cidr",
        "::::/64",
        "1::2::3/64",
        "1:2:3:4:5:6:7:8:9/64",
        "10000::/64",
    ],
)
def test_release_gateway_rejects_open_or_malformed_jwks_cidrs(cidr: str) -> None:
    for validation_args in ((), ("--skip-schema-validation",)):
        helm_args = [
            "--set-string",
            f"networkPolicy.gatewayJWKS.egressCIDRs[0]={cidr}",
        ]
        helm_args[:0] = validation_args
        with pytest.raises(subprocess.CalledProcessError) as error:
            _render_staging(
                *helm_args,
                release_name="jwks-cidr-invalid-contract",
            )

        assert error.value.returncode == 1
        assert "networkpolicy.gatewayjwks.egresscidrs" in (
            error.value.stderr.lower().replace("/", ".")
        )


def _resolved_revocation_store_args(release_name: str) -> list[str]:
    """Return the exact immutable identity supplied by the bootstrap script."""

    digest = "sha256:" + ("b" * 64)
    overrides = {
        "applicationReleaseName": release_name,
        "redis.fullnameOverride": f"{release_name}-revocation-redis",
        "redis.commonLabels.university-ecosystem\\.io/revocation-store-for": release_name,
        "redis.commonLabels.app\\.kubernetes\\.io/instance": release_name,
        "redis.auth.existingSecret": "revocation-redis-credentials",  # pragma: allowlist secret
        "redis.auth.existingSecretPasswordKey": "revocation-redis-password",  # pragma: allowlist secret
        "redis.image.digest": digest,
        "redis.metrics.image.digest": digest,
        "global.backendImageRepository": "ghcr.io/example/university-ecosystem/backend",
        "global.backendImageDigest": digest,
        "redis.metrics.passwordFileInitImage.repository": "ghcr.io/example/university-ecosystem/backend",
        "redis.metrics.passwordFileInitImage.digest": digest,
        "redis.metrics.passwordFileInitImage.tag": "",
        "redis.metrics.passwordFileInitImage.pullPolicy": "Always",
    }
    args: list[str] = []
    for key, value in overrides.items():
        args.extend(("--set-string", f"{key}={value}"))
    return args


def _render_revocation_store(
    *extra: str, release_name: str = "staging-contract"
) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            f"{release_name}-revocation-store",
            str(REVOCATION_STORE_CHART),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(REVOCATION_STORE_VALUES),
            *_resolved_revocation_store_args(release_name),
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


def _assert_projected_secret_file(
    container: dict[str, Any],
    pod_spec: dict[str, Any],
    *,
    variable: str,
    secret_name: str,
    key: str,
    volume_name: str,
    expected_keys: set[str] | None = None,
) -> None:
    """Assert a secret is consumed through one least-privilege read-only file mount."""

    assert variable.endswith("_FILE")
    env_entries = {item["name"]: item for item in container["env"]}
    assert variable[:-5] not in env_entries
    entry = env_entries[variable]
    assert entry == {
        "name": variable,
        "value": f"/run/secrets/{secret_name}/{key}",
    }

    mounts = [
        mount
        for mount in container.get("volumeMounts", [])
        if mount.get("name") == volume_name
    ]
    assert len(mounts) == 1
    assert mounts[0] == {
        "name": volume_name,
        "mountPath": f"/run/secrets/{secret_name}",
        "readOnly": True,
    }

    volumes = [
        volume
        for volume in pod_spec.get("volumes", [])
        if volume.get("name") == volume_name
    ]
    assert len(volumes) == 1
    projected = volumes[0]["secret"]
    assert projected["secretName"] == secret_name
    assert type(projected["defaultMode"]) is int
    assert projected["defaultMode"] == 0o440
    items = projected["items"]
    assert isinstance(items, list) and items
    assert all(set(item) == {"key", "path"} for item in items)
    assert all(item["path"] == item["key"] for item in items)
    keys = [item["key"] for item in items]
    assert len(keys) == len(set(keys))
    assert key in keys
    if expected_keys is not None:
        assert set(keys) == expected_keys


def _existing_secret_command(environment: str, *extra: str) -> list[str]:
    environment_overrides: list[str] = []
    if environment == "production":
        environment_overrides = [
            "--set-string",
            "ingress.issuer.kind=ClusterIssuer",
            "--set-string",
            "ingress.issuer.name=letsencrypt-prod",
        ]
    return [
        _helm(),
        "template",
        f"{environment}-contract",
        str(CHART),
        "--dependency-update=false",
        "--values",
        str(STAGING_VALUES),
        *_resolved_staging_args(),
        "--set-string",
        f"global.environment={environment}",
        *environment_overrides,
        *extra,
    ]


def test_default_nats_values_use_official_chart_jetstream_and_persistence_tree() -> (
    None
):
    values = _values(CHART / "values.yaml")
    nats = values["nats"]

    assert "nats" not in nats
    assert nats["config"]["jetstream"]["enabled"] is True
    assert nats["config"]["jetstream"]["fileStore"]["enabled"] is True
    assert nats["config"]["jetstream"]["fileStore"]["pvc"] == {
        "enabled": True,
        "name": "data",
        "size": "10Gi",
    }
    assert nats["container"]["image"]["repository"] == "nats"
    assert nats["container"]["image"]["pullPolicy"] == "Always"
    assert nats["auth"]["enabled"] is False
    assert nats["cluster"]["auth"]["enabled"] is False
    assert nats["existingSecret"] == ""


def test_default_redis_password_init_tracks_default_backend_reference() -> None:
    values = _values(CHART / "values.yaml")
    backend = values["backend"]["image"]
    helper = values["redis"]["metrics"]["passwordFileInitImage"]
    app_version = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))[
        "appVersion"
    ]
    assert backend["repository"] == helper["repository"] == "university-backend"
    assert backend["digest"] == helper["digest"] == ""
    assert backend["tag"] == ""
    assert app_version == "1.0.0"
    assert helper["tag"] == ""
    assert helper["pullPolicy"] == "Always"


def test_canonical_staging_values_are_secure_and_fail_closed() -> None:
    values = _values(STAGING_VALUES)

    assert values["backend"]["config"]["eventFileScannerEnabled"] is True

    assert values["global"] == {
        "environment": "staging",
        "imageRegistry": "",
        "imageTag": "REQUIRED_GIT_SHA",
        "imagePullSecrets": ["ghcr-pull"],
        "jwtIssuer": "https://REQUIRED_API_HOST",
        "security": {"allowInsecureImages": False},
    }
    assert values["fullnameOverride"] == "university-ecosystem"
    assert values["applicationSecrets"]["existingSecret"] == (
        "university-application"
    )  # pragma: allowlist secret
    expected_connections_secret = "university-connections"  # pragma: allowlist secret
    assert values["connections"]["existingSecret"] == expected_connections_secret

    repositories = {
        "backend": "backend",
        "frontend": "frontend",
        "gateway": "gateway",
        "fileProcessor": "file-processor",
        "outboxWorker": "backend",
    }
    for component, repository in repositories.items():
        assert values[component]["image"] == {
            "repository": f"ghcr.io/REQUIRED_REPOSITORY/{repository}",
            "digest": "REQUIRED_SHA256_DIGEST",
            "pullPolicy": "Always",
        }

    nats = values["nats"]
    expected_nats_secret = "university-nats-config"  # pragma: allowlist secret
    assert nats["existingSecret"] == expected_nats_secret
    assert nats["auth"]["enabled"] is False
    assert nats["replicaCount"] == 3
    assert nats["config"]["cluster"] == {"enabled": True, "replicas": 3}
    jetstream = nats["config"]["jetstream"]
    assert jetstream["enabled"] is True
    assert jetstream["fileStore"]["enabled"] is True
    assert jetstream["fileStore"]["dir"] == "/data"
    assert jetstream["merge"]["store_dir"] == "/data/jetstream"
    assert jetstream["fileStore"]["pvc"] == {
        "enabled": True,
        "name": "data",
        "size": "10Gi",
    }
    assert jetstream["memoryStore"] == {"enabled": True, "maxSize": "512Mi"}
    assert nats["container"]["image"] == {
        "registry": "docker.io",
        "repository": "nats",
        "tag": "2.15.0-alpine",
        "digest": "REQUIRED_SHA256_DIGEST",
        "pullPolicy": "Always",
    }
    assert nats["statefulSet"]["merge"]["spec"]["podManagementPolicy"] == "OrderedReady"
    assert nats["statefulSet"]["merge"]["spec"][
        "persistentVolumeClaimRetentionPolicy"
    ] == {
        "whenDeleted": "Retain",
        "whenScaled": "Retain",
    }

    redis = values["redis"]
    assert redis["image"]["registry"] == "docker.io"
    assert redis["image"]["repository"] == "redis"
    assert redis["image"]["pullPolicy"] == "Always"
    assert redis["metrics"]["image"]["registry"] == "docker.io"
    assert redis["metrics"]["image"]["repository"] == "oliver006/redis_exporter"
    assert redis["metrics"]["image"]["pullPolicy"] == "Always"
    assert redis["metrics"]["passwordFileInitImage"] == {
        "repository": "ghcr.io/REQUIRED_REPOSITORY/backend",
        "tag": "REQUIRED_GIT_SHA",
        "digest": "REQUIRED_SHA256_DIGEST",
        "pullPolicy": "Always",
    }
    assert redis["networkPolicy"] == {
        "enabled": True,
        "allowExternal": False,
        "allowExternalEgress": False,
    }
    assert values["nats"]["networkPolicy"] == {
        "enabled": True,
        "allowExternal": False,
        "allowExternalEgress": False,
    }
    assert values["nats"]["image"]["registry"] == "docker.io"
    assert values["nats"]["image"]["repository"] == "nats"
    assert values["nats"]["container"]["image"]["repository"] == "nats"

    assert values["backend"]["autoscaling"]["enabled"] is True
    assert values["ingress"]["enabled"] is True
    assert values["ingress"]["tls"]
    assert values["backend"]["config"]["minioSecure"] is True
    assert values["backend"]["config"]["storageBackend"] == "s3"
    assert values["backend"]["config"]["storageS3Bucket"] == "uploads"
    assert values["backend"]["config"]["storageS3EndpointURL"] == (
        "https://REQUIRED_MINIO_ENDPOINT"
    )
    assert values["backend"]["config"]["storageS3BaseURL"] == "/api/v1/img"
    assert values["gateway"]["config"]["grpcUseTLS"] is True
    assert (
        values["internalGrpcMTLS"]
        == {
            "enabled": True,
            "serverName": "university-ecosystem-file-processor.university-ecosystem.svc",
            "gatewayIdentityURI": "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
            "allowedClientURIs": [
                "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway",
            ],
            "gatewayClient": {
                "existingSecret": "university-internal-grpc-gateway-client",  # pragma: allowlist secret
                "certKey": "tls.crt",
                "privateKeyKey": "tls.key",  # pragma: allowlist secret
                "caKey": "ca.crt",
            },
            "fileProcessorServer": {
                "existingSecret": "university-internal-grpc-file-processor-server",  # pragma: allowlist secret
                "certKey": "tls.crt",
                "privateKeyKey": "tls.key",  # pragma: allowlist secret
                "clientCAKey": "ca.crt",
            },
        }
    )
    assert values["fileProcessor"]["config"]["temporalTLSDisabled"] is False
    assert values["fileProcessor"]["config"]["jwksRefreshInterval"] == 300
    assert values["fileProcessor"]["config"]["jwtActiveKID"] == "primary"
    assert values["fileProcessor"]["config"]["otlpInsecure"] is False


def test_chart_documents_staging_secret_and_release_contracts() -> None:
    documentation = (CHART / "README.md").read_text(encoding="utf-8")

    for required_text in (
        "values-staging.yaml",
        "university-application",
        "university-connections",
        "university-nats-config",
        "nats-server.conf",
        "--config /etc/nats-auth/nats-server.conf",
        "chart-generated ConfigMap is not the runtime configuration",
        "REQUIRED_SHA256_DIGEST",
        "helm upgrade --install",
        "helm rollback",
    ):
        assert required_text in documentation

    assert "signature, SBOM, and provenance" not in documentation
    assert "docker.io/redis:7.4.11-alpine" in documentation
    assert "docker.io/oliver006/redis_exporter" in documentation
    assert "docker.io/nats" in documentation


def test_chart_lock_pins_the_reviewed_dependency_set() -> None:
    lock = _values(CHART / "Chart.lock")
    assert lock["dependencies"] == [
        {
            "name": "redis",
            "repository": "file://../redis-compat",
            "version": "0.1.0",
        },
        {
            "name": "nats",
            "repository": "https://nats-io.github.io/k8s/helm/charts/",
            "version": "2.15.0",
        },
    ]
    assert lock["digest"].startswith("sha256:")
    assert len(lock["digest"]) == 71
    assert (CHART / "charts" / "redis-0.1.0.tgz").is_file()
    assert (CHART / "charts" / "nats-2.15.0.tgz").is_file()


def test_values_schema_closes_staging_sensitive_configuration_trees() -> None:
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    def resolved(node: dict[str, Any]) -> dict[str, Any]:
        reference = node.get("$ref")
        if reference is None:
            return node
        prefix = "#/definitions/"
        assert reference.startswith(prefix)
        return schema["definitions"][reference.removeprefix(prefix)]

    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert properties["global"]["additionalProperties"] is False
    assert (
        properties["global"]["properties"]["security"]["additionalProperties"] is False
    )

    for component in (
        "backend",
        "frontend",
        "gateway",
        "fileProcessor",
        "outboxWorker",
    ):
        component_schema = properties[component]
        assert component_schema["additionalProperties"] is False
        assert (
            resolved(component_schema["properties"]["image"])["additionalProperties"]
            is False
        )
        assert (
            resolved(component_schema["properties"]["resources"])[
                "additionalProperties"
            ]
            is False
        )

    assert (
        properties["backend"]["properties"]["autoscaling"]["additionalProperties"]
        is False
    )
    assert properties["ingress"]["additionalProperties"] is False
    assert resolved(properties["redis"])["additionalProperties"] is False
    assert "revocationRedis" not in properties
    assert properties["nats"]["additionalProperties"] is False

    backend_config = properties["backend"]["properties"]["config"]
    assert backend_config["additionalProperties"] is False
    assert backend_config["properties"]["storageBackend"]["enum"] == [
        "static",
        "s3",
        "minio",
    ]
    for field in (
        "storageS3Bucket",
        "storageS3Region",
        "storageS3EndpointURL",
        "storageS3BaseURL",
    ):
        assert backend_config["properties"][field]["type"] == "string"


def test_staging_backend_uses_external_s3_storage_with_secret_credentials() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    backend = _component_resource(resources, "Deployment", "backend")
    pod_spec = backend["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    env = {entry["name"]: entry for entry in container["env"]}

    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert env["STORAGE_BACKEND"]["value"] == "s3"
    assert env["STORAGE_S3_BUCKET"]["value"] == "uploads"
    assert env["STORAGE_S3_ENDPOINT_URL"]["value"] == (
        "https://minio.staging.internal:443"
    )
    assert env["STORAGE_S3_BASE_URL"]["value"] == "/api/v1/img"
    _assert_projected_secret_file(
        container,
        pod_spec,
        variable="STORAGE_S3_ACCESS_KEY_ID_FILE",
        secret_name="university-application",
        key="minio-access-key",
        volume_name="secret-application",
    )
    _assert_projected_secret_file(
        container,
        pod_spec,
        variable="STORAGE_S3_SECRET_ACCESS_KEY_FILE",
        secret_name="university-application",
        key="minio-secret-key",
        volume_name="secret-application",
    )
    assert env["JWT_AUDIENCE"]["value"] == "university-ecosystem-api"
    assert env["JWT_ISSUER"]["value"] == "https://api.university.staging.example.org"
    assert not any(
        mount["mountPath"].startswith("/app/static")
        for mount in container.get("volumeMounts", [])
    )


def test_deploy_helm_pins_new_dependency_images_and_backend_s3_endpoint() -> None:
    script = (ROOT / ".github/scripts/deploy-helm.sh").read_text(encoding="utf-8")

    assert "MINIO_ENDPOINT" in script
    assert (
        '--set-string "backend.config.storageS3EndpointURL=https://$MINIO_ENDPOINT"'
        in script
    )
    for backend_bound_arg in (
        '--set-string "redis.metrics.passwordFileInitImage.repository=$REGISTRY/$GITHUB_REPOSITORY/backend"',
        '--set-string "redis.metrics.passwordFileInitImage.tag=$DEPLOY_VERSION"',
        '--set-string "redis.metrics.passwordFileInitImage.digest=$BACKEND_IMAGE_DIGEST"',
        '--set-string "redis.metrics.passwordFileInitImage.pullPolicy=Always"',
    ):
        assert backend_bound_arg in script
    for reviewed_arg in (
        '--set-string "redis.image.repository=redis"',
        '--set-string "redis.metrics.image.repository=oliver006/redis_exporter"',
        '--set-string "nats.image.repository=nats"',
        '--set-string "nats.container.image.repository=nats"',
        '--set-string "nats.image.digest=$NATS_IMAGE_DIGEST"',
        '--set-string "nats.container.image.digest=$NATS_IMAGE_DIGEST"',
    ):
        assert reviewed_arg in script


def test_deploy_preflight_binds_nats_secret_to_the_existing_jetstream_path() -> None:
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert (
        "NATS authentication config must set the existing JetStream store path to /data/jetstream"
        in workflow
    )
    assert "config.splitlines()" in workflow
    assert '"/data/jetstream"' in workflow
    assert "docker.io/redis@$REDIS_IMAGE_DIGEST" in workflow
    assert 'test -s "$chart/charts/redis-0.1.0.tgz"' in workflow
    assert 'test -s "$chart/charts/nats-2.15.0.tgz"' in workflow


def test_backend_s3_credentials_remain_in_preflight_when_file_processor_is_off() -> (
    None
):
    resources = _render_staging(
        "--set",
        "fileProcessor.enabled=false",
        "--set",
        "deploymentContract.enabled=true",
    )
    contract = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"].endswith("-deployment-contract")
    )

    required_keys = json.loads(contract["data"]["application-secret-keys.json"])
    assert "minio-access-key" in required_keys
    assert "minio-secret-key" in required_keys


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(
    ("flag", "override", "message"),
    [
        (
            "--set-string",
            "backend.config.storageBackend=static",
            "backend.config.storageBackend",
        ),
        (
            "--set-string",
            "backend.config.storageS3Bucket=",
            "backend.config.storageS3Bucket",
        ),
        (
            "--set-string",
            "backend.config.storageS3EndpointURL=http://minio.internal:9000",
            "backend.config.storageS3EndpointURL",
        ),
        (
            "--set-string",
            "backend.config.storageS3BaseURL=",
            "backend.config.storageS3BaseURL",
        ),
        (
            "--set-string",
            "backend.config.storageS3BaseURL=https://minio.staging.internal/uploads",
            "backend.config.storageS3BaseURL",
        ),
        (
            "--set-string",
            "backend.config.storageS3BaseURL=http://public.example.org/images",
            "backend.config.storageS3BaseURL",
        ),
        (
            "--set-string",
            "backend.config.storageS3BaseURL=/storage/uploads",
            "backend.config.storageS3BaseURL",
        ),
    ],
)
def test_release_rejects_non_s3_backend_storage_contract(
    environment: str, flag: str, override: str, message: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(environment, flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize(
    "invalid_override",
    [
        "nats.nats.jetstream.enabled=true",
        "ingress.tlsz[0].secretName=invalid",
        "backend.image.pullPolcy=Always",
        "backend.autoscaling.maxReplica=4",
        "global.security.allowInsecureImage=true",
    ],
)
def test_values_schema_rejects_unknown_staging_sensitive_keys(
    invalid_override: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "schema-contract",
            str(CHART),
            "--dependency-update=false",
            "--set-string",
            "global.environment=development",
            "--set",
            invalid_override,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    # Helm versions vary between singular and plural forms of this
    # fail-closed JSON-Schema diagnostic.
    assert "additional propert" in result.stderr.lower()


def test_canonical_staging_values_reject_unresolved_required_markers() -> None:
    # The MFA active key ID is checked before the marker scan; supply it so the
    # render reaches the unresolved-marker rejection this test asserts.
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "staging-contract",
            str(CHART),
            "--dependency-update=false",
            "--values",
            str(STAGING_VALUES),
            "--set",
            f"backend.config.mfaTotpActiveEncryptionKeyId={MFA_TOTP_ACTIVE_KEY_ID}",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "unresolved REQUIRED_ marker" in result.stderr


def test_validate_config_requires_file_scanning_in_release_environments() -> None:
    template = (CHART / "templates" / "validate-config.yaml").read_text(
        encoding="utf-8"
    )
    assert "backend.config.eventFileScannerEnabled" in template


def test_backend_receives_public_frontend_origin_from_ingress() -> None:
    resources = _render_staging(release_name="frontend-origin-contract")
    backend = _component_resource(resources, "Deployment", "backend")
    env = {
        item["name"]: item.get("value")
        for item in backend["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    origin = "https://university.staging.example.org"
    assert env["APP_BASE_URL"] == origin
    assert env["FRONTEND_ORIGIN"] == origin
    assert env["FRONTEND_ORIGINS"] == origin


def test_validate_config_pins_frontend_origin_to_the_ingress_host() -> None:
    template = (CHART / "templates" / "validate-config.yaml").read_text(
        encoding="utf-8"
    )
    assert 'include "university-ecosystem.frontendOrigin"' in template
    assert "backend.config.frontendOrigin" in template


def test_outbox_worker_receives_release_file_scanner_guard() -> None:
    resources = _render_staging(release_name="outbox-scanner-contract")
    outbox = _component_resource(resources, "Deployment", "outbox-worker")
    scanner_values = [
        item.get("value")
        for item in outbox["spec"]["template"]["spec"]["containers"][0]["env"]
        if item.get("name") == "EVENT_FILE_SCANNER_ENABLED"
    ]
    assert scanner_values == ["true"]

    template = (CHART / "templates" / "outbox-worker-deployment.yaml").read_text(
        encoding="utf-8"
    )
    assert "EVENT_FILE_SCANNER_ENABLED" in template
    assert "backend.config.eventFileScannerEnabled" in template


def test_staging_render_rejects_a_missing_first_party_digest() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "staging-contract",
            str(CHART),
            "--dependency-update=false",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            "--set-string",
            "backend.image.digest=",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "backend.image.digest requires an immutable sha256 digest" in result.stderr


@pytest.mark.parametrize(
    ("image_key", "mutable_image"),
    [
        ("backup.postgresImage", "postgres:latest"),
        ("backup.s3ClientImage", "rclone/rclone:latest"),
    ],
)
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_backup_images_are_immutable_in_release_environments(
    image_key: str, mutable_image: str, environment: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            *_existing_secret_command(
                environment,
                "--set-string",
                f"{image_key}={mutable_image}",
            ),
            "--set",
            "backup.enabled=true",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert f"{image_key} requires an immutable @sha256 digest" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "backend.env.AWS_SECRET_ACCESS_KEY=exposed-inline-value",
        "outboxWorker.env.SMTP_PASSWORD=exposed-worker-value",
    ],
)
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_release_environments_reject_all_inline_workload_env(
    override: str, environment: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(environment, "--set-string", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "must be empty in staging/production" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "applicationSecrets.existingSecret=INVALID_NAME",
        "connections.existingSecret=INVALID_CONNECTION",
        "nats.existingSecret=INVALID_NATS",
        "redis.auth.existingSecret=INVALID_REDIS",
        "ingress.tls[0].secretName=INVALID_TLS_SECRET",
    ],
)
def test_staging_schema_rejects_invalid_kubernetes_secret_resource_names(
    override: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", "--set-string", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    # Helm's gojsonschema renderer changed from "does not match pattern" to
    # "does not match" for oneOf-backed string schemas in 3.17.
    assert "does not match" in result.stderr.lower()


@pytest.mark.parametrize(
    "override",
    [
        "redis.master.extraEnvVars[0].name=AWS_SECRET_ACCESS_KEY",
        "redis.replica.sidecars[0].image=busybox:1.36",
        "nats.extraEnvVars[0].name=SMTP_PASSWORD",
        "nats.sidecars[0].image=busybox:1.36",
    ],
)
def test_release_environments_reject_arbitrary_subchart_extensions(
    override: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", "--set-string", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "arbitrary subchart" in result.stderr or (
        "values don't meet the specifications" in result.stderr
        and "additional propert" in result.stderr.lower()
    )


@pytest.mark.parametrize(
    "override",
    [
        "redis.volumePermissions.enabled=true",
        "redis.sysctl.enabled=true",
        "nats.metrics.enabled=true",
    ],
)
def test_release_environments_reject_unreviewed_helper_containers(
    override: str,
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", "--set", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "unreviewed subchart helper containers" in result.stderr or (
        "values don't meet the specifications" in result.stderr
        and "additional propert" in result.stderr.lower()
    )


@pytest.mark.parametrize(
    "override",
    [
        "nats.auth.token=inline-token",
        "nats.auth.password=inline-password",
        "nats.cluster.auth.password=inline-cluster-password",
    ],
)
def test_staging_render_rejects_inline_nats_auth_material(override: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "staging-contract",
            str(CHART),
            "--dependency-update=false",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            "--set-string",
            override,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "NATS auth material must not be stored in Helm values" in result.stderr or (
        "values don't meet the specifications" in result.stderr
        and "additional propert" in result.stderr.lower()
    )


@pytest.mark.parametrize(
    ("flag", "override", "expected"),
    [
        (
            "--set-string",
            "global.imageTag=mutable-tag",
            "global.imageTag must be the exact 40-character lowercase Git SHA",
        ),
        (
            "--set-string",
            "backend.image.digest=",
            "backend.image.digest requires an immutable sha256 digest",
        ),
        (
            "--set",
            "redis.image.pullPolicy=IfNotPresent",
            "redis.image.pullPolicy=Always is required",
        ),
        (
            "--set",
            "nats.config.jetstream.enabled=false",
            "official NATS chart config must preserve the staged 3-node JetStream storage at /data/jetstream on the existing /data PVC mount, rollout ordering, PVC retention, and pod-token contract",
        ),
        (
            "--set",
            "backend.autoscaling.minReplicas=7",
            "backend.autoscaling.maxReplicas must be greater than or equal to minReplicas",
        ),
        (
            "--set",
            "ingress.enabled=false",
            "ingress.enabled, ingress.className, and ingress.tls are required",
        ),
    ],
)
def test_production_is_fail_closed_like_staging(
    flag: str, override: str, expected: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("production", flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert expected in result.stderr or (
        "values don't meet the specifications" in result.stderr
    )


INLINE_SECRET_OVERRIDES = (
    "gateway.config.jwtSecret=inline",
    "backend.config.jwtPrivateKeyPEM=inline",
    "backend.config.internalHMACSecret=inline",
    "backend.config.wsHubInternalSecret=inline",
    "backend.config.csrfHMACSecret=inline",
    "backend.config.spotifyTokenSecret=inline",
    "backend.config.elasticsearchPassword=inline",
    "backend.config.spicedbPresharedKey=inline",
    "backend.config.auditLogSecret=inline",
    "backend.config.tokenHMACSecret=inline",
    "backend.config.idempotencyHMACSecret=inline",
    "backend.config.mfaEmailOtpHMACKeys=inline",
    "backend.config.mfaEmailOtpActiveHMACKeyId=inline",
    "backend.config.mfaEmailDeliveryKEKs=inline",
    "backend.config.mfaEmailDeliveryActiveKEKId=inline",
    "backend.config.mfaTrustedDeviceHMACKeys=inline",
    "backend.config.mfaTrustedDeviceActiveHMACKeyId=inline",
    "fileProcessor.config.rsaPublicKeyPEM=inline",
    "fileProcessor.config.minioAccessKey=inline",
    "fileProcessor.config.minioSecretKey=inline",
    "fileProcessor.config.temporalAPIKey=inline",
    "redis.auth.password=inline",
    "redis.auth.acl.users[0].password=inline",
    "redis.global.redis.password=inline",
    "nats.auth.token=inline",
    "nats.auth.password=inline",
    "nats.auth.usersCredentials[0].password=inline",
    "nats.cluster.auth.password=inline",
)


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("override", INLINE_SECRET_OVERRIDES)
def test_non_development_render_rejects_every_inline_secret_value(
    environment: str, override: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(environment, "--set-string", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "secret material must not be stored in Helm values" in result.stderr or (
        "values don't meet the specifications" in result.stderr
        and "additional propert" in result.stderr.lower()
    )


def test_cache_redis_exporter_password_file_and_high_uid_contract() -> None:
    resources = _render_staging(release_name="cache-security-contract")
    redis_resources = [
        resource
        for resource in resources
        if resource.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/name")
        == "redis"
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/instance")
        == "cache-security-contract"
    ]
    assert redis_resources
    assert {resource["metadata"]["namespace"] for resource in redis_resources} == {
        "university-ecosystem"
    }

    statefulset = next(
        resource
        for resource in redis_resources
        if resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == "cache-security-contract-redis-master"
    )
    pod_spec = statefulset["spec"]["template"]["spec"]
    assert pod_spec["securityContext"]["fsGroup"] == 1001
    assert pod_spec["securityContext"]["fsGroupChangePolicy"] == "Always"
    assert statefulset["spec"]["persistentVolumeClaimRetentionPolicy"] == {
        "whenDeleted": "Retain",
        "whenScaled": "Retain",
    }
    assert (
        statefulset["spec"]["volumeClaimTemplates"][0]["metadata"]["name"]
        == "redis-data"
    )
    assert any(
        mount["mountPath"] == "/data"
        for container in pod_spec["containers"]
        if container["name"] == "redis"
        for mount in container["volumeMounts"]
    )

    all_containers = pod_spec["initContainers"] + pod_spec["containers"]
    assert {
        container["securityContext"]["runAsUser"] for container in all_containers
    } == {10001}
    assert {
        container["securityContext"]["runAsGroup"] for container in all_containers
    } == {1001}
    password_init = next(
        container
        for container in pod_spec["initContainers"]
        if container["name"] == "redis-exporter-password-file"
    )
    backend_deployment = _component_resource(resources, "Deployment", "backend")
    backend_image = backend_deployment["spec"]["template"]["spec"]["containers"][0][
        "image"
    ]
    assert password_init["image"] == backend_image
    assert password_init["image"] == "ghcr.io/example/university/backend@sha256:" + (
        "a" * 64
    )
    assert password_init["imagePullPolicy"] == "Always"
    assert password_init["securityContext"]["readOnlyRootFilesystem"] is True
    assert password_init["securityContext"]["allowPrivilegeEscalation"] is False
    assert password_init["securityContext"]["capabilities"]["drop"] == ["ALL"]
    init_code = password_init["args"][-1]
    assert '"redis://127.0.0.1:6379"' in init_code
    assert "def read_password(path):" in init_code
    assert (
        'path.read_bytes().rstrip(b"\\n").decode("utf-8", errors="strict")' in init_code
    )
    assert "tempfile.mkstemp" in init_code
    assert "json.dump" in init_code and "os.replace" in init_code
    assert "os.fsync(output.fileno())" in init_code
    assert "os.chmod(temporary_path, 0o440)" in init_code
    assert "target_path.unlink(missing_ok=True)" in init_code
    assert "file=sys.stderr" in init_code
    assert all(
        name not in init_code for name in ("redis-password-value", "REDIS_PASSWORD=")
    )
    source_mount = next(
        mount
        for mount in password_init["volumeMounts"]
        if mount["name"] == "redis-password"
    )
    assert source_mount["readOnly"] is True
    assert source_mount["mountPath"] == "/run/redis-auth-source"

    exporter = next(
        container
        for container in pod_spec["containers"]
        if container["name"] == "metrics"
    )
    env = {item["name"]: item.get("value") for item in exporter["env"]}
    assert env["REDIS_PASSWORD_FILE"] == "/run/redis-exporter-auth/passwords.json"
    assert "REDIS_PASSWORD" not in env
    output_mount = next(
        mount
        for mount in exporter["volumeMounts"]
        if mount["mountPath"] == "/run/redis-exporter-auth"
    )
    assert output_mount["readOnly"] is True
    output_volume = next(
        volume
        for volume in pod_spec["volumes"]
        if volume["name"] == "redis-exporter-auth"
    )
    assert output_volume["emptyDir"] == {"medium": "Memory", "sizeLimit": "8Mi"}


def test_redis_exporter_serializer_preserves_acl_trailing_cr_bytes(
    tmp_path: Path,
) -> None:
    template = (ROOT / "charts/redis-compat/templates/redis.yaml").read_text(
        encoding="utf-8"
    )
    lines = template.splitlines()
    command_index = next(
        index for index, line in enumerate(lines) if 'command: ["python"]' in line
    )
    block_index = next(
        index
        for index in range(command_index, len(lines))
        if lines[index].strip() == "- |"
    )
    code_lines: list[str] = []
    for line in lines[block_index + 1 :]:
        if not line.strip():
            code_lines.append("")
        elif line.startswith("              "):
            code_lines.append(line[14:])
        else:
            break
    code = "\n".join(code_lines) + "\n"
    source = tmp_path / "source-password"
    target = tmp_path / "passwords.json"
    code = code.replace(
        '"/run/redis-auth-source/password"', json.dumps(str(source))
    ).replace('"/run/redis-exporter-auth/passwords.json"', json.dumps(str(target)))

    source.write_bytes(b"synthetic-password\r\n")
    completed = subprocess.run(  # noqa: S603 - current Python and repository-owned serializer; no shell.
        [sys.executable, "-I", "-S", "-c", code],
        check=False,
        capture_output=True,
        text=False,
    )
    assert completed.returncode == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "redis://127.0.0.1:6379": "synthetic-password\r"
    }
    assert b"synthetic-password" not in completed.stdout + completed.stderr
    assert list(tmp_path.glob(".passwords.*.tmp")) == []

    for invalid_bytes in (b"", b"\xff"):
        if target.exists():
            target.chmod(0o600)
            target.unlink()
        source.write_bytes(invalid_bytes)
        failed = subprocess.run(  # noqa: S603 - current Python and repository-owned serializer; no shell.
            [sys.executable, "-I", "-S", "-c", code],
            check=False,
            capture_output=True,
            text=False,
        )
        assert failed.returncode == 1
        assert b"failed to materialize Redis exporter credential file" in failed.stderr
        assert b"synthetic-password" not in failed.stdout + failed.stderr
        assert not target.exists()
        assert list(tmp_path.glob(".passwords.*.tmp")) == []


def test_redis_exporter_password_init_rejects_backend_image_identity_drift() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(
            "--set-string",
            "redis.metrics.passwordFileInitImage.digest=sha256:" + ("b" * 64),
            release_name="redis-helper-image-drift-contract",
        )

    assert (
        "redis.metrics.passwordfileinitimage must resolve exactly to backend.image"
        in error.value.stderr.lower()
    )


def test_checkov_namespace_workflow_uses_validated_fallback_and_no_skip() -> None:
    workflow = (ROOT / ".github/workflows/checkov.yml").read_text(encoding="utf-8")
    assert "vars.K8S_NAMESPACE || 'university-ecosystem'" in workflow
    assert '"$K8S_NAMESPACE" == "default"' in workflow
    assert (
        "HELM_NAMESPACE: ${{ vars.K8S_NAMESPACE || 'university-ecosystem' }}"
        in workflow
    )
    assert "--skip-check" not in workflow


def test_resolved_staging_render_is_immutable_and_kyverno_compatible() -> None:
    resources = _render_staging("--set", "deploymentContract.enabled=true")

    assert not any(resource.get("kind") == "Secret" for resource in resources)
    contract = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"].endswith("-deployment-contract")
    )
    assert contract["data"]["nats-config-secret-name"] == "university-nats-config"
    assert json.loads(contract["data"]["nats-config-secret-keys.json"]) == [
        "nats-server.conf"
    ]
    assert contract["data"]["redis-secret-name"] == "redis-credentials"
    assert json.loads(contract["data"]["redis-secret-keys.json"]) == ["redis-password"]
    assert contract["data"]["revocation-redis-url-key"] == "redis-revocation-url"
    assert contract["data"]["revocation-redis-service-host"] == (
        "staging-contract-revocation-redis-master"
    )
    assert json.loads(contract["data"]["dependency-images.json"]) == {
        "nats": "docker.io/nats@sha256:" + ("a" * 64),
        "redis": "docker.io/redis@sha256:" + ("a" * 64),
        "redis.metrics": ("docker.io/oliver006/redis_exporter@sha256:" + ("a" * 64)),
    }
    assert json.loads(contract["data"]["dependency-chart-versions.json"]) == {
        "nats": "2.15.0",
        "redis": "0.1.0",
    }

    pod_specs = []
    for resource in resources:
        kind = resource.get("kind")
        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            pod_specs.append(resource["spec"]["template"]["spec"])
        elif kind == "Job":
            pod_specs.append(resource["spec"]["template"]["spec"])
        elif kind == "CronJob":
            pod_specs.append(
                resource["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            )

    containers = [
        container
        for spec in pod_specs
        for container in (
            spec.get("initContainers", [])
            + spec.get("containers", [])
            + spec.get("ephemeralContainers", [])
        )
    ]
    assert containers
    assert all(container["imagePullPolicy"] == "Always" for container in containers)
    assert all("@sha256:" in container["image"] for container in containers)
    assert all(
        container["image"].startswith(
            (
                "ghcr.io/example/university/",
                "docker.io/redis@",
                "docker.io/oliver006/redis_exporter@",
                "docker.io/nats@",
            )
        )
        for container in containers
    )
    assert all(container.get("resources", {}).get("limits") for container in containers)
    for spec in pod_specs:
        assert spec["securityContext"]["runAsNonRoot"] is True
        assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    for container in containers:
        security = container["securityContext"]
        assert security["allowPrivilegeEscalation"] is False
        assert security["readOnlyRootFilesystem"] is True
        assert "ALL" in security["capabilities"]["drop"]

    nats = next(
        resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == "staging-contract-nats"
    )
    assert nats["spec"]["replicas"] == 3
    assert (
        nats["spec"]["volumeClaimTemplates"][0]["spec"]["resources"]["requests"][
            "storage"
        ]
        == "10Gi"
    )
    config_volume = next(
        volume
        for volume in nats["spec"]["template"]["spec"]["volumes"]
        if volume["name"] == "nats-auth-config"
    )
    expected_nats_config_secret = "university-nats-config"  # pragma: allowlist secret
    assert config_volume["secret"]["secretName"] == expected_nats_config_secret
    assert any(
        resource.get("kind") == "HorizontalPodAutoscaler" for resource in resources
    )
    assert any(resource.get("kind") == "Ingress" for resource in resources)


@pytest.mark.parametrize(
    "override",
    [
        "internalGrpcMTLS.enabled=false",
        "internalGrpcMTLS.serverName=",
        "internalGrpcMTLS.gatewayIdentityURI=",
        "internalGrpcMTLS.gatewayClient.existingSecret=",
        "internalGrpcMTLS.fileProcessorServer.existingSecret=",
    ],
)
def test_release_grpc_tls_rejects_incomplete_mtls_contract(override: str) -> None:
    flag = "--set" if override.endswith("false") else "--set-string"
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "internalGrpcMTLS" in result.stderr


def test_release_grpc_tls_rejects_empty_client_identity_allowlist() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(
            "staging", "--set-json", "internalGrpcMTLS.allowedClientURIs=[]"
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "internalGrpcMTLS.allowedClientURIs" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "internalGrpcMTLS.allowedClientURIs={spiffe://university.ecosystem/ns/university-ecosystem/sa/other}",
        "internalGrpcMTLS.gatewayIdentityURI=spiffe://university.ecosystem/ns/university-ecosystem/sa/other",
        "internalGrpcMTLS.gatewayClient.existingSecret=university-internal-grpc-file-processor-server",
        "internalGrpcMTLS.fileProcessorServer.existingSecret=university-internal-grpc-gateway-client",
    ],
)
def test_release_grpc_tls_rejects_identity_or_secret_aliases(override: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", "--set-string", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "internalGrpcMTLS" in result.stderr


def test_staging_mounts_conventional_mtls_secrets_read_only() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployments = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "Deployment"
    }
    gateway = next(
        value for key, value in deployments.items() if key.endswith("-gateway")
    )
    processor = next(
        value for key, value in deployments.items() if key.endswith("-file-processor")
    )
    processor_service = next(
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"].endswith("-file-processor")
    )

    gateway_spec = gateway["spec"]["template"]["spec"]
    processor_spec = processor["spec"]["template"]["spec"]
    gateway_container = gateway_spec["containers"][0]
    processor_container = processor_spec["containers"][0]
    gateway_env = {item["name"]: item.get("value") for item in gateway_container["env"]}
    processor_env = {
        item["name"]: item.get("value") for item in processor_container["env"]
    }

    assert gateway_env["GRPC_SERVER_NAME"] == (
        "university-ecosystem-file-processor.university-ecosystem.svc"
    )
    assert gateway_env["GRPC_CLIENT_IDENTITY_URI"] == (
        "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
    )
    assert gateway_env["GRPC_SERVER_NAME"] == (
        f"{processor_service['metadata']['name']}."
        f"{processor_service['metadata']['namespace']}.svc"
    )
    assert gateway_env["GRPC_CA_FILE"] == "/run/secrets/internal-grpc-mtls/ca.crt"
    assert gateway_env["GRPC_CLIENT_CERT_FILE"] == (
        "/run/secrets/internal-grpc-mtls/tls.crt"
    )
    assert gateway_env["GRPC_CLIENT_KEY_FILE"] == (
        "/run/secrets/internal-grpc-mtls/tls.key"
    )
    _assert_projected_secret_file(
        gateway_container,
        gateway_spec,
        variable="FILE_PROCESSING_CAPABILITY_SECRET_FILE",
        secret_name="university-application",
        key="internal-hmac-secret",
        volume_name="secret-application",
        expected_keys={"jwt-secret", "internal-hmac-secret"},
    )
    assert processor_env["FP_GRPC_TLS_CERT_FILE"] == (
        "/run/secrets/internal-grpc-mtls-server/tls.crt"
    )
    assert processor_env["FP_GRPC_TLS_KEY_FILE"] == (
        "/run/secrets/internal-grpc-mtls-server/tls.key"
    )
    assert processor_env["FP_GRPC_CLIENT_CA_FILE"] == (
        "/run/secrets/internal-grpc-mtls-server/ca.crt"
    )
    _assert_projected_secret_file(
        processor_container,
        processor_spec,
        variable="FP_PROCESSING_CAPABILITY_SECRET_FILE",
        secret_name="university-application",
        key="internal-hmac-secret",
        volume_name="secret-application",
        expected_keys={
            "minio-access-key",
            "minio-secret-key",
            "internal-hmac-secret",
            "jwt-rsa-public-key",
            "temporal-api-key",
        },
    )
    assert processor_env["FP_GRPC_ALLOWED_CLIENT_URIS"] == (
        "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
    )
    assert processor_env["FP_JWKS_URL"].endswith("-backend:8000/.well-known/jwks.json")
    assert processor_env["FP_JWKS_REFRESH_INTERVAL"] == "300"
    assert processor_env["FP_JWT_ACTIVE_KID"] == "primary"
    assert all(mount["readOnly"] is True for mount in gateway_container["volumeMounts"])
    assert all(
        mount["readOnly"] is True for mount in processor_container["volumeMounts"]
    )
    assert gateway["spec"]["template"]["spec"]["securityContext"]["fsGroup"] == 65532
    assert gateway_container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert gateway_container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert gateway_container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    for probe_name in ("startupProbe", "livenessProbe", "readinessProbe"):
        probe = processor_container[probe_name]
        assert "grpc" not in probe
        assert "exec" not in probe
        assert probe["tcpSocket"]["port"] == "grpc"

    gateway_volumes = {
        volume["name"]: volume["secret"]
        for volume in gateway_spec["volumes"]
        if "secret" in volume
    }
    processor_volumes = {
        volume["name"]: volume["secret"]
        for volume in processor_spec["volumes"]
        if "secret" in volume
    }
    gateway_tls = gateway_volumes["internal-grpc-mtls"]
    assert gateway_tls["secretName"] == "university-internal-grpc-gateway-client"
    assert gateway_tls["defaultMode"] == 0o440
    assert {(item["key"], item["path"]) for item in gateway_tls["items"]} == {
        ("tls.crt", "tls.crt"),
        ("tls.key", "tls.key"),
        ("ca.crt", "ca.crt"),
    }
    processor_tls = processor_volumes["internal-grpc-mtls-server"]
    assert processor_tls["secretName"] == (
        "university-internal-grpc-file-processor-server"
    )
    assert processor_tls["defaultMode"] == 0o440
    assert {(item["key"], item["path"]) for item in processor_tls["items"]} == {
        ("tls.crt", "tls.crt"),
        ("tls.key", "tls.key"),
        ("ca.crt", "ca.crt"),
    }
    assert "internal-grpc-mtls-probe" not in processor_volumes
    assert not any(
        mount["name"] == "internal-grpc-mtls-probe"
        for mount in processor_container["volumeMounts"]
    )


def _component_resource(
    resources: list[dict[str, Any]], kind: str, component: str
) -> dict[str, Any]:
    return next(
        resource
        for resource in resources
        if resource.get("kind") == kind
        and resource.get("metadata", {})
        .get("labels", {})
        .get("app.kubernetes.io/component")
        == component
    )


def test_auth_token_hmac_secret_is_wired_from_application_secret() -> None:
    resources = _render_staging(release_name="university-ecosystem")

    for component in ("backend", "outbox-worker"):
        deployment = _component_resource(resources, "Deployment", component)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(
            item for item in pod_spec["containers"] if item["name"] == component
        )
        _assert_projected_secret_file(
            container,
            pod_spec,
            variable="TOKEN_HMAC_SECRET_FILE",
            secret_name="university-application",
            key="token-hmac-secret",
            volume_name="secret-application",
        )


def test_internal_chat_auth_token_is_shared_by_backend_and_ws_hub() -> None:
    resources = _render_staging(release_name="university-ecosystem")

    for component in ("backend", "ws-hub"):
        deployment = _component_resource(resources, "Deployment", component)
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(
            item for item in pod_spec["containers"] if item["name"] == component
        )
        expected_keys = (
            {"jwt-secret", "ws-hub-internal-secret"} if component == "ws-hub" else None
        )
        for variable in ("INTERNAL_AUTH_TOKEN_FILE", "WS_HUB_INTERNAL_SECRET_FILE"):
            _assert_projected_secret_file(
                container,
                pod_spec,
                variable=variable,
                secret_name="university-application",
                key="ws-hub-internal-secret",
                volume_name="secret-application",
                expected_keys=expected_keys,
            )


def test_ws_hub_is_a_restricted_helm_managed_atomic_workload() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployment = _component_resource(resources, "Deployment", "ws-hub")
    service = _component_resource(resources, "Service", "ws-hub")
    hpa = _component_resource(resources, "HorizontalPodAutoscaler", "ws-hub")
    pdb = _component_resource(resources, "PodDisruptionBudget", "ws-hub")
    service_account = _component_resource(resources, "ServiceAccount", "ws-hub")

    assert deployment["spec"]["replicas"] >= 2
    pod = deployment["spec"]["template"]
    spec = pod["spec"]
    security = spec["securityContext"]
    assert security["runAsNonRoot"] is True
    assert security["runAsUser"] == 65532
    assert security["runAsGroup"] == 65532
    assert security["fsGroup"] == 65532
    assert security["seccompProfile"]["type"] == "RuntimeDefault"
    assert spec["automountServiceAccountToken"] is False
    assert service_account["automountServiceAccountToken"] is False
    container = next(item for item in spec["containers"] if item["name"] == "ws-hub")
    assert container["image"].endswith("@sha256:" + ("a" * 64))
    assert container["imagePullPolicy"] == "Always"
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert container["resources"]["requests"]
    assert container["resources"]["limits"]
    assert container["ports"] == [
        {"name": "http", "containerPort": 8081, "protocol": "TCP"}
    ]
    assert container["startupProbe"]["httpGet"] == {
        "path": "/health/live",
        "port": "http",
    }
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert pod["metadata"]["annotations"]["university-ecosystem.io/source-sha"] == (
        "9d08136558b95d1182f889574f67b1b1d21abc9f"  # pragma: allowlist secret
    )
    assert service["spec"]["ports"][0]["port"] == 8081
    assert hpa["spec"]["scaleTargetRef"]["name"].endswith("-ws-hub")
    assert hpa["spec"]["minReplicas"] >= 2
    assert pdb["spec"]["maxUnavailable"] == 1


def test_first_party_deployments_are_bound_to_exact_source_sha() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployments = [
        resource for resource in resources if resource.get("kind") == "Deployment"
    ]
    assert deployments
    for deployment in deployments:
        assert (
            deployment["spec"]["template"]["metadata"]["annotations"][
                "university-ecosystem.io/source-sha"
            ]
            == "9d08136558b95d1182f889574f67b1b1d21abc9f"  # pragma: allowlist secret
        )


def test_ws_hub_env_uses_only_explicit_values_and_secret_files() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployment = _component_resource(resources, "Deployment", "ws-hub")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    env = {item["name"]: item for item in container["env"]}

    application_secret = "university-application"  # pragma: allowlist secret
    connection_secret = "university-connections"  # pragma: allowlist secret
    application_keys = {"jwt-secret", "ws-hub-internal-secret"}
    for variable, key in {
        "JWT_SECRET_FILE": "jwt-secret",
        "WS_HUB_INTERNAL_SECRET_FILE": "ws-hub-internal-secret",
        "INTERNAL_AUTH_TOKEN_FILE": "ws-hub-internal-secret",
    }.items():
        _assert_projected_secret_file(
            container,
            pod_spec,
            variable=variable,
            secret_name=application_secret,
            key=key,
            volume_name="secret-application",
            expected_keys=application_keys,
        )

    connection_keys = {
        "nats-url",
        "nats-auth-token",
        "redis-backend-url",
        "redis-revocation-url",
    }
    for variable, key in {
        "NATS_URL_FILE": "nats-url",
        "NATS_AUTH_TOKEN_FILE": "nats-auth-token",
        "REDIS_URL_FILE": "redis-backend-url",
        "REVOCATION_REDIS_URL_FILE": "redis-revocation-url",
    }.items():
        _assert_projected_secret_file(
            container,
            pod_spec,
            variable=variable,
            secret_name=connection_secret,
            key=key,
            volume_name="secret-connections",
            expected_keys=connection_keys,
        )
    assert env["BACKEND_INTERNAL_URL"]["value"].endswith("-backend:8000")
    assert env["JWKS_URL"]["value"].endswith("-backend:8000/.well-known/jwks.json")
    for required in (
        "ALLOWED_ORIGINS",
        "TRUSTED_PROXIES",
        "WS_SEND_BUFFER_SIZE",
        "WS_BROADCAST_BUFFER_SIZE",
        "WS_BROADCAST_WORKERS",
        "WS_HUB_MAX_CLIENTS",
        "WS_CLIENT_MSG_RATE_LIMIT",
        "WS_CLIENT_MSG_BURST",
        "WS_TICKET_TTL_SECONDS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_INSECURE",
        "ENABLE_JETSTREAM",
        "NATS_STREAM_CHAT",
        "NATS_STREAM_NOTIFICATIONS",
        "NATS_DURABLE_CHAT",
        "NATS_DURABLE_NOTIFICATIONS",
    ):
        assert required in env
        assert "value" in env[required]


def test_ingress_routes_ws_ticket_to_gateway_and_chat_to_ws_hub() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    ingress = next(
        resource for resource in resources if resource.get("kind") == "Ingress"
    )
    paths = {
        path["path"]: path
        for rule in ingress["spec"]["rules"]
        for path in rule["http"]["paths"]
    }
    assert paths["/ws/ticket"]["pathType"] == "Exact"
    assert paths["/ws/ticket"]["backend"]["service"]["name"].endswith("-gateway")
    assert paths["/ws/chat"]["pathType"] == "Exact"
    assert paths["/ws/chat"]["backend"]["service"]["name"].endswith("-ws-hub")
    assert paths["/ws/chat"]["backend"]["service"]["port"]["number"] == 8081


def test_ws_hub_network_policy_is_least_privilege() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    policy = _component_resource(resources, "NetworkPolicy", "ws-hub")
    ports = {
        port["port"]
        for rule in policy["spec"]["egress"]
        for port in rule.get("ports", [])
    }
    assert {53, 4222, 4317, 6379, 8000} <= ports
    ingress_ports = {
        port["port"]
        for rule in policy["spec"]["ingress"]
        for port in rule.get("ports", [])
    }
    assert ingress_ports == {8081, 9108}
    # Prometheus may reach only the scrape-only metrics port (AUD-438); the
    # public WebSocket port is never admitted from the monitoring namespace.
    monitoring_ports = {
        port["port"]
        for rule in policy["spec"]["ingress"]
        for source in rule.get("from", [])
        if source.get("namespaceSelector", {}).get("matchLabels")
        == {"kubernetes.io/metadata.name": "monitoring"}
        for port in rule.get("ports", [])
    }
    assert monitoring_ports == {9108}
    backend_policy = _component_resource(resources, "NetworkPolicy", "backend")
    backend_sources = [
        source.get("podSelector", {}).get("matchLabels", {})
        for rule in backend_policy["spec"]["ingress"]
        for source in rule.get("from", [])
    ]
    assert {"app.kubernetes.io/component": "ws-hub"} in backend_sources


def test_migration_hook_can_reach_only_its_dedicated_revocation_store() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    migration_job = next(
        resource
        for resource in resources
        if resource.get("kind") == "Job"
        and resource["metadata"]["name"] == "university-ecosystem-migrate"
    )
    migration_labels = migration_job["spec"]["template"]["metadata"]["labels"]
    assert migration_labels["university-ecosystem-revocation-redis-client"] == "true"

    policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == "university-ecosystem-migration-policy"
    )
    assert policy["metadata"]["annotations"] == {
        "helm.sh/hook": "pre-install,pre-upgrade",
        "helm.sh/hook-weight": "-20",
        "helm.sh/hook-delete-policy": "before-hook-creation",
    }
    assert migration_job["metadata"]["annotations"] == {
        "helm.sh/hook": "pre-install,pre-upgrade",
        "helm.sh/hook-weight": "-10",
        "helm.sh/hook-delete-policy": "before-hook-creation",
    }
    egress = policy["spec"]["egress"]
    assert {port["port"] for rule in egress for port in rule.get("ports", [])} == {
        53,
        5432,
        6379,
    }
    revocation_redis_rule = next(
        rule
        for rule in egress
        if any(port["port"] == 6379 for port in rule.get("ports", []))
    )
    assert revocation_redis_rule["to"] == [
        {
            "podSelector": {
                "matchLabels": {
                    "app.kubernetes.io/name": "revocation-redis",
                    "app.kubernetes.io/component": "master",
                    "university-ecosystem.io/revocation-store-for": "university-ecosystem",
                }
            }
        }
    ]


def test_app_chart_renders_only_cache_redis_and_uses_bootstrap_store_identity() -> None:
    """The pre-hook application release must never own the revocation StatefulSet."""

    release_name = "arbitrary-release"
    resources = _render_staging(release_name=release_name)
    statefulsets = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
    }
    services = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "Service"
    }

    cache_master = f"{release_name}-redis-master"
    revocation_master = f"{release_name}-revocation-redis-master"
    assert cache_master in statefulsets
    assert cache_master in services
    assert revocation_master not in statefulsets
    assert revocation_master not in services
    assert (
        statefulsets[cache_master]["spec"]["template"]["metadata"]["labels"][
            "app.kubernetes.io/name"
        ]
        == "redis"
    )
    assert all(
        "revocation-redis" not in resource["metadata"]["name"] for resource in resources
    )


def test_revocation_store_bootstrap_render_is_durable_isolated_and_bound() -> None:
    """The separate release owns one immutable, bound, persistent master."""

    release_name = "arbitrary-release"
    resources = _render_revocation_store(release_name=release_name)
    service_name = f"{release_name}-revocation-redis-master"
    binding = {"university-ecosystem.io/revocation-store-for": release_name}
    statefulset = next(
        resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == service_name
    )
    service = next(
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"] == service_name
    )
    pdb = next(
        resource
        for resource in resources
        if resource.get("kind") == "PodDisruptionBudget"
        and resource["metadata"]["name"] == service_name
    )
    network_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-revocation-redis"
    )
    configuration = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"]
        == f"{release_name}-revocation-redis-master-configuration"
    )
    contract = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"]
        == f"{release_name}-revocation-store-deployment-contract"
    )

    for resource in (statefulset, service, pdb):
        assert resource["metadata"]["labels"].items() >= binding.items()
    labels = statefulset["spec"]["template"]["metadata"]["labels"]
    assert labels.items() >= binding.items()
    assert labels["app.kubernetes.io/name"] == "revocation-redis"
    assert labels["app.kubernetes.io/component"] == "master"
    assert labels["app.kubernetes.io/instance"] == release_name
    assert statefulset["spec"]["replicas"] == 1
    assert (
        statefulset["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 30
    )
    assert statefulset["spec"]["persistentVolumeClaimRetentionPolicy"] == {
        "whenDeleted": "Retain",
        "whenScaled": "Retain",
    }
    assert pdb["spec"]["minAvailable"] == 1
    assert statefulset["spec"]["volumeClaimTemplates"]
    redis_container = next(
        container
        for container in statefulset["spec"]["template"]["spec"]["containers"]
        if container["name"] == "redis"
    )
    assert redis_container["image"].startswith("docker.io/redis:7.4.11-alpine@sha256:")
    assert redis_container["imagePullPolicy"] == "Always"
    assert 'rename-command FLUSHDB ""' in configuration["data"]["master.conf"]
    assert 'rename-command FLUSHALL ""' in configuration["data"]["master.conf"]
    assert 'rename-command CONFIG ""' in configuration["data"]["master.conf"]
    assert 'rename-command ACL ""' in configuration["data"]["master.conf"]
    assert 'rename-command FUNCTION ""' in configuration["data"]["master.conf"]
    assert 'rename-command MIGRATE ""' in configuration["data"]["master.conf"]
    assert 'rename-command MODULE ""' in configuration["data"]["master.conf"]
    assert 'rename-command MONITOR ""' in configuration["data"]["master.conf"]
    assert 'rename-command REPLICAOF ""' in configuration["data"]["master.conf"]
    assert 'rename-command SLAVEOF ""' in configuration["data"]["master.conf"]
    assert 'rename-command SHUTDOWN ""' in configuration["data"]["master.conf"]
    ingress_selectors = [
        source["podSelector"]["matchLabels"]
        for rule in network_policy["spec"]["ingress"]
        for source in rule.get("from", [])
        if "podSelector" in source
    ]
    assert {f"{release_name}-revocation-redis-client": "true"} in ingress_selectors
    metrics_rule = next(
        rule
        for rule in network_policy["spec"]["ingress"]
        if rule["ports"] == [{"port": 9121, "protocol": "TCP"}]
    )
    assert metrics_rule["from"] == [
        {
            "namespaceSelector": {
                "matchLabels": {
                    "kubernetes.io/metadata.name": "monitoring",
                }
            }
        }
    ]
    assert contract["data"] == {
        "application-release-name": release_name,
        "master-service-host": service_name,
        "master-statefulset-name": service_name,
        "binding-label": "university-ecosystem.io/revocation-store-for",
        "binding-value": release_name,
    }


@pytest.mark.parametrize(
    ("flag", "override"),
    [
        ("--set-string", "redis.auth.password=inline"),
        ("--set-string", "redis.auth.existingSecretPasswordKey=wrong-key"),
        ("--set", "redis.auth.usePasswordFiles=false"),
        ("--set-string", "redis.existingConfigmap=attacker-config"),
        ("--set-string", "redis.master.extraEnvVars[0].name=AWS_SECRET_ACCESS_KEY"),
        ("--set-string", "redis.master.sidecars[0].image=busybox:1.36"),
        ("--set-string", "redis.master.initContainers[0].image=busybox:1.36"),
        ("--set-string", "redis.master.command[0]=sh"),
        ("--set-string", "redis.master.configuration=maxmemory-policy allkeys-lru"),
        ("--set-string", "redis.master.lifecycleHooks.postStart.exec.command[0]=sh"),
        ("--set-string", "redis.master.customReadinessProbe.exec.command[0]=sh"),
        ("--set-string", "redis.master.podLabels.injected=true"),
        ("--set", "redis.master.containerSecurityContext.runAsUser=0"),
        (
            "--set",
            "redis.master.containerSecurityContext.allowPrivilegeEscalation=true",
        ),
        ("--set-json", "redis.master.disableCommands=[]"),
        ("--set", "redis.master.terminationGracePeriodSeconds=0"),
        ("--set-string", "redis.master.kind=Deployment"),
        ("--set-string", "redis.namespaceOverride=other-namespace"),
        ("--set-string", "redis.metrics.extraEnvVars[0].name=AWS_SECRET_ACCESS_KEY"),
        ("--set-string", "redis.metrics.command[0]=sh"),
        ("--set", "redis.metrics.containerSecurityContext.runAsUser=0"),
        ("--set-string", "redis.metrics.redisTargetHost=attacker.invalid"),
        ("--set", "redis.volumePermissions.enabled=true"),
        ("--set", "redis.sysctl.enabled=true"),
        ("--set", "redis.diagnosticMode.enabled=true"),
        ("--set-string", "redis.serviceAccount.name=attacker"),
        ("--set", "redis.master.service.type=LoadBalancer"),
        ("--set-string", "redis.image.repository=attacker/redis"),
        ("--set", "redis.networkPolicy.allowExternal=true"),
        ("--set-string", "redis.networkPolicy.ingressNSMatchLabels.team=attacker"),
        ("--set", "redis.networkPolicy.metrics.allowExternal=true"),
        (
            "--set-string",
            "redis.networkPolicy.metrics.ingressNSMatchLabels.team=attacker",
        ),
        ("--set", "redis.rbac.create=true"),
    ],
)
def test_revocation_store_rejects_unreviewed_injection_surfaces(
    flag: str, override: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "staging-contract-revocation-store",
            str(REVOCATION_STORE_CHART),
            "--dependency-update=false",
            "--values",
            str(REVOCATION_STORE_VALUES),
            *_resolved_revocation_store_args("staging-contract"),
            flag,
            override,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "revocation-store" in result.stderr or "specifications" in result.stderr


def test_dependency_network_policies_require_explicit_client_labels() -> None:
    release_name = "dependency-label-contract"
    resources = _render_staging(
        "--set", "migrations.enabled=true", release_name=release_name
    )
    deployments = {
        resource["metadata"]["labels"]["app.kubernetes.io/component"]: resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and "app.kubernetes.io/component"
        in resource.get("metadata", {}).get("labels", {})
    }
    expected = {
        "backend": {"redis", "revocation-redis", "nats"},
        "gateway": {"redis", "revocation-redis"},
        "ws-hub": {"redis", "revocation-redis", "nats"},
        "file-processor": {"nats"},
        "outbox-worker": {"redis", "nats"},
    }
    workloads = [
        resource
        for resource in resources
        if resource.get("kind") in {"Deployment", "StatefulSet", "DaemonSet", "Job"}
    ]
    for component, dependencies in expected.items():
        labels = deployments[component]["spec"]["template"]["metadata"]["labels"]
        for dependency in dependencies:
            label_key = f"{release_name}-{dependency}-client"
            assert labels[label_key] == "true"
            assert f"university-ecosystem-{dependency}-client" not in labels
    migration_jobs = [
        resource
        for resource in workloads
        if resource.get("kind") == "Job"
        and resource["metadata"]["name"].endswith("-migrate")
    ]
    assert len(migration_jobs) == 1
    migration_labels = migration_jobs[0]["spec"]["template"]["metadata"]["labels"]
    assert migration_labels[f"{release_name}-revocation-redis-client"] == "true"

    policies = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
    }
    redis_policy = policies[f"{release_name}-redis"]
    nats_policy = policies[f"{release_name}-nats"]
    redis_ingress_selectors = [
        source["podSelector"]["matchLabels"]
        for rule in redis_policy["spec"]["ingress"]
        for source in rule.get("from", [])
        if "podSelector" in source
    ]
    nats_ingress_selectors = [
        source["podSelector"]["matchLabels"]
        for rule in nats_policy["spec"]["ingress"]
        for source in rule.get("from", [])
        if "podSelector" in source
    ]
    assert {f"{release_name}-redis-client": "true"} in redis_ingress_selectors
    assert {f"{release_name}-nats-client": "true"} in nats_ingress_selectors
    assert not any(
        "university-ecosystem-redis-client" in selector
        for selector in redis_ingress_selectors
    )
    assert not any(
        "university-ecosystem-nats-client" in selector
        for selector in nats_ingress_selectors
    )

    matching_clients = {
        dependency: {
            resource["metadata"]["labels"].get("app.kubernetes.io/component")
            or resource["metadata"]["name"]
            for resource in workloads
            if resource["spec"]["template"]["metadata"]["labels"].get(
                f"{release_name}-{dependency}-client"
            )
            == "true"
        }
        for dependency in ("redis", "nats")
    }
    assert matching_clients["redis"] >= {"backend", "ws-hub", "outbox-worker"}
    assert matching_clients["nats"] >= {
        "backend",
        "ws-hub",
        "file-processor",
        "outbox-worker",
    }

    nats = next(
        resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
        and resource["metadata"]["name"] == f"{release_name}-nats"
    )
    legacy_nats_selector = {
        "app.kubernetes.io/name": "nats",
        "app.kubernetes.io/instance": release_name,
    }
    assert nats["spec"]["selector"]["matchLabels"] == legacy_nats_selector
    nats_services = [
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"]
        in {f"{release_name}-nats", f"{release_name}-nats-headless"}
    ]
    assert {resource["metadata"]["name"] for resource in nats_services} == {
        f"{release_name}-nats",
        f"{release_name}-nats-headless",
    }
    assert all(
        resource["spec"]["selector"] == legacy_nats_selector
        for resource in nats_services
    )
    nats_pdb = next(
        resource
        for resource in resources
        if resource.get("kind") == "PodDisruptionBudget"
        and resource["metadata"]["name"] == f"{release_name}-nats"
    )
    assert nats_pdb["spec"]["selector"]["matchLabels"] == legacy_nats_selector

    redis = next(
        resource
        for resource in resources
        if resource.get("kind") == "StatefulSet"
        and resource.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/name")
        == "redis"
        and resource["metadata"]["labels"].get("app.kubernetes.io/component")
        == "master"
    )
    redis_container = next(
        container
        for container in redis["spec"]["template"]["spec"]["containers"]
        if container["name"] == "redis"
    )
    redis_config_mount = next(
        mount for mount in redis_container["volumeMounts"] if mount["name"] == "config"
    )
    assert redis_config_mount["mountPath"] == "/etc/redis"
    assert redis_container["args"] == ["exec redis-server /etc/redis/redis.conf"]
    # These are the exact legacy Bitnami PVC-template labels; changing them makes the VCT immutable field drift.
    assert redis["spec"]["volumeClaimTemplates"][0]["apiVersion"] == "v1"
    assert redis["spec"]["volumeClaimTemplates"][0]["kind"] == "PersistentVolumeClaim"
    assert redis["spec"]["volumeClaimTemplates"][0]["metadata"]["labels"] == {
        "app.kubernetes.io/component": "master",
        "app.kubernetes.io/instance": release_name,
        "app.kubernetes.io/name": "redis",
    }
    data_mounts = [
        mount
        for container in nats["spec"]["template"]["spec"]["containers"]
        for mount in container.get("volumeMounts", [])
        if mount.get("name") == "data"
    ]
    assert any(mount["mountPath"] == "/data" for mount in data_mounts)
    assert nats["spec"]["volumeClaimTemplates"][0]["metadata"]["name"] == "data"
    nats_container = next(
        container
        for container in nats["spec"]["template"]["spec"]["containers"]
        if container["name"] == "nats"
    )
    assert nats_container["args"] == [
        "--config",
        "/etc/nats-auth/nats-server.conf",
    ]
    nats_secret_mount = next(
        mount
        for mount in nats_container["volumeMounts"]
        if mount["name"] == "nats-auth-config"
    )
    assert nats_secret_mount["mountPath"] == "/etc/nats-auth"
    assert nats_secret_mount["readOnly"] is True
    nats_secret_volume = next(
        volume
        for volume in nats["spec"]["template"]["spec"]["volumes"]
        if volume["name"] == "nats-auth-config"
    )
    assert nats_secret_volume["secret"]["secretName"] == "university-nats-config"
    assert nats_secret_volume["secret"]["items"] == [
        {"key": "nats-server.conf", "path": "nats-server.conf"}
    ]

    revocation_selector = {
        "app.kubernetes.io/name": "revocation-redis",
        "app.kubernetes.io/component": "master",
        "university-ecosystem.io/revocation-store-for": release_name,
    }
    for component in ("backend", "gateway", "ws-hub"):
        policy = policies[f"{release_name}-{component}-policy"]
        egress_selectors = [
            destination["podSelector"]["matchLabels"]
            for rule in policy["spec"]["egress"]
            for destination in rule.get("to", [])
            if "podSelector" in destination
        ]
        assert revocation_selector in egress_selectors

    outbox = deployments["outbox-worker"]
    outbox_labels = outbox["spec"]["template"]["metadata"]["labels"]
    assert f"{release_name}-revocation-redis-client" not in outbox_labels
    outbox_env = {
        entry["name"]: entry
        for entry in outbox["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert outbox_env["APP_PROCESS_ROLE"]["value"] == "outbox-worker"
    assert outbox_env["REVOCATION_REDIS_ACCESS_ENABLED"]["value"] == "false"
    assert "REVOCATION_REDIS_URL" not in outbox_env
    outbox_policy = policies[f"{release_name}-outbox-worker-policy"]
    outbox_egress_selectors = [
        destination["podSelector"]["matchLabels"]
        for rule in outbox_policy["spec"]["egress"]
        for destination in rule.get("to", [])
        if "podSelector" in destination
    ]
    assert revocation_selector not in outbox_egress_selectors


def test_outbox_revocation_capability_cannot_be_overridden_by_chart_values() -> None:
    """The non-auth worker role is a deployment invariant, not a user override."""

    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(
            "staging",
            "--set-string",
            "outboxWorker.env.APP_PROCESS_ROLE=api",
            "--set-string",
            "outboxWorker.env.REVOCATION_REDIS_ACCESS_ENABLED=true",
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "outboxWorker.env" in result.stderr


def test_ws_hub_origin_is_bound_to_frontend_ingress_host() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(
            "staging",
            "--set-string",
            "wsHub.config.allowedOrigins[0]=https://different.example.org",
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "frontend ingress origin" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "redis.networkPolicy.allowExternal=true",
        "redis.networkPolicy.allowExternalEgress=true",
        "nats.networkPolicy.allowExternalEgress=true",
    ],
)
def test_release_rejects_permissive_dependency_network_policy(override: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", "--set", override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "networkPolicy" in result.stderr


@pytest.mark.parametrize(
    "flag, override",
    [
        ("--set", "global.security.allowInsecureImages=true"),
        ("--set-string", "global.imageRegistry=mirror.invalid"),
        ("--set-string", "redis.image.registry=mirror.invalid"),
        ("--set-string", "redis.image.repository=attacker/redis"),
        ("--set-string", "redis.metrics.image.repository=attacker/exporter"),
        (
            "--set-string",
            "redis.metrics.passwordFileInitImage.repository=attacker/python",
        ),
        ("--set-string", "redis.metrics.passwordFileInitImage.digest=not-a-digest"),
        ("--set-string", "redis.metrics.passwordFileInitImage.pullPolicy=IfNotPresent"),
        ("--set-string", "nats.image.repository=attacker/nats"),
        ("--set-string", "nats.container.image.repository=attacker/nats"),
        ("--set-string", "nats.image.registry=ghcr.io"),
        ("--set-string", "nats.image.tag=2.14.0-alpine"),
        ("--set-string", "nats.image.digest=sha256:" + "c" * 64),
        ("--set-string", "nats.image.pullPolicy=IfNotPresent"),
        ("--set-string", "nats.container.image.registry=ghcr.io"),
        ("--set-string", "nats.container.image.tag=2.14.0-alpine"),
        ("--set-string", "nats.container.image.digest=sha256:" + "d" * 64),
        ("--set-string", "nats.container.image.pullPolicy=IfNotPresent"),
    ],
)
def test_release_rejects_dependency_repository_substitution_or_bypass(
    flag: str, override: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert any(
        marker in result.stderr
        for marker in (
            "dependency image repository",
            "redis.metrics.passwordFileInitImage must resolve exactly to backend.image",
            "allowInsecureImages",
            "metadata must exactly match",
            "values don't meet the specifications",
        )
    )


def test_release_rejects_mutable_password_init_image_without_backend_binding() -> None:
    # The schema requires a valid global digest. Use a distinct repository so
    # the backend-only digest fallback cannot make this latest tag immutable.
    immutable_digest = "sha256:" + "a" * 64
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(
            "development",
            "--set-string",
            "backend.image.repository=university-backend",
            "--set-string",
            f"backend.image.digest={immutable_digest}",
            "--set-string",
            "backend.image.tag=contract-sha",
            "--set-string",
            "redis.metrics.passwordFileInitImage.repository=university-backend-mutable",
            "--set-string",
            "redis.metrics.passwordFileInitImage.digest=",
            "--set-string",
            "redis.metrics.passwordFileInitImage.tag=latest",
            "--set-string",
            "global.imageTag=contract-sha",
            "--set-string",
            f"global.backendImageDigest={immutable_digest}",
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert (
        "redis.metrics.passwordFileInitImage must resolve exactly to backend.image"
        in result.stderr
    )


@pytest.mark.parametrize(
    "override, message",
    [
        ("wsHub.enabled=false", "wsHub.enabled=true"),
        ("wsHub.replicaCount=1", "wsHub.replicaCount"),
        ("wsHub.image.digest=", "wsHub.image.digest"),
        ("wsHub.image.pullPolicy=IfNotPresent", "wsHub.image.pullPolicy=Always"),
        ("wsHub.autoscaling.minReplicas=1", "wsHub.autoscaling.minReplicas"),
        ("wsHub.autoscaling.enabled=false", "wsHub.autoscaling.enabled=true"),
        ("wsHub.service.port=8082", "wsHub.service.port"),
        ("wsHub.config.allowedOrigins={}", "allowedOrigins"),
        ("wsHub.config.allowedOrigins={http://insecure.example}", "https://"),
    ],
)
def test_release_rejects_incomplete_ws_hub_contract(
    override: str, message: str
) -> None:
    flag = "--set" if override.endswith(("false", "=1", "=8082")) else "--set-string"
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command("staging", flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert message in result.stderr


def test_staging_uses_namespaced_issuer_and_production_cluster_issuer() -> None:
    staging = _render_staging(release_name="university-ecosystem")
    ingress = next(
        resource for resource in staging if resource.get("kind") == "Ingress"
    )
    annotations = ingress["metadata"]["annotations"]
    assert annotations["cert-manager.io/issuer"] == "university-staging-issuer"
    assert "cert-manager.io/cluster-issuer" not in annotations

    production = _render_staging(
        "--set-string",
        "global.environment=production",
        "--set-string",
        "ingress.issuer.kind=ClusterIssuer",
        "--set-string",
        "ingress.issuer.name=letsencrypt-prod",
        release_name="university-ecosystem",
    )
    production_ingress = next(
        resource for resource in production if resource.get("kind") == "Ingress"
    )
    production_annotations = production_ingress["metadata"]["annotations"]
    assert production_annotations["cert-manager.io/cluster-issuer"] == (
        "letsencrypt-prod"
    )
    assert "cert-manager.io/issuer" not in production_annotations


@pytest.mark.parametrize(
    "environment, kind",
    [("staging", "ClusterIssuer"), ("production", "Issuer")],
)
def test_release_rejects_wrong_typed_certificate_issuer(
    environment: str, kind: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _existing_secret_command(
            environment, "--set-string", f"ingress.issuer.kind={kind}"
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    normalized_error = result.stderr.lower().replace(".", "/")
    assert "ingress/issuer/kind" in normalized_error


def test_backend_cwv_environment_is_typed_and_not_in_backend_env_values() -> None:
    values = _values(CHART / "values.yaml")
    assert "cwv" in values
    assert not any(key.startswith("CWV_") for key in values["backend"]["env"])
    resources = _render_staging(release_name="university-ecosystem")
    backend = _component_resource(resources, "Deployment", "backend")
    env = {
        item["name"]: item
        for item in backend["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    for name in (
        "CWV_RUM_ENABLED",
        "CWV_RELEASE_SHA",
        "CWV_FRONTEND_IMAGE_DIGEST",
        "CWV_DEPLOYMENT_RUN_ID",
        "CWV_DEPLOYMENT_RUN_ATTEMPT",
        "CWV_DEPLOYMENT_URL",
        "CWV_DEPLOYED_AT",
        "CWV_ALLOWED_ORIGINS",
        "CWV_EXPORT_OIDC_ENABLED",
        "CWV_EXPORT_OIDC_REPOSITORY",
        "CWV_EXPORT_OIDC_WORKFLOW_REF",
        "CWV_EXPORT_OIDC_SUBJECT",
    ):
        assert name in env


@pytest.mark.parametrize("profile", [CHART / "values.yaml", STAGING_VALUES])
def test_frontend_ingress_routes_browser_requests_to_their_owners(
    profile: Path,
) -> None:
    hosts = _values(profile)["ingress"]["hosts"]
    frontend = next(
        host
        for host in hosts
        if any(path["service"] == "frontend" for path in host["paths"])
    )

    def destination(url: str) -> str:
        matching = [
            path
            for path in frontend["paths"]
            if (
                url == path["path"]
                if path["pathType"] == "Exact"
                else url == path["path"]
                or url.startswith(path["path"].rstrip("/") + "/")
            )
        ]
        return max(matching, key=lambda path: len(path["path"]))["service"]

    for path in (
        "/api/v1/auth/csrf-cookie",
        "/api/v1/auth/login",
        "/api/v1/img/avatar",
        "/api/admin/users",
        "/ws/ticket",
    ):
        assert destination(path) == "gateway", path
    assert destination("/graphql") == "frontend"
    assert destination("/ws/chat") == "ws-hub"
    assert destination("/static/uploads/avatar.png") == "backend"
    assert destination("/.well-known/jwks.json") == "backend"
    assert destination("/events") == "frontend"


def test_gateway_accepts_only_its_declared_browser_origin() -> None:
    resources = _render_staging(release_name="browser-origin-contract")
    gateway = _component_resource(resources, "Deployment", "gateway")
    env = {
        entry["name"]: entry.get("value")
        for entry in gateway["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env["ALLOWED_ORIGINS"] == "https://university.staging.example.org"


def test_documented_go_overlay_pairs_local_grpc_transports() -> None:
    overlay = _values(ROOT / "docker-compose.go.yml")["services"]
    assert overlay["gateway"]["environment"]["GRPC_USE_TLS"] == "false"
    assert (
        overlay["gateway"]["environment"]["VITE_ENVIRONMENT"]
        == "${ENVIRONMENT:-development}"
    )
    processor = overlay["file-processor"]["environment"]
    assert not processor.get("FP_GRPC_TLS_CERT_FILE")
    assert not processor.get("SPIFFE_SOCKET_PATH")
    assert processor["FP_ENVIRONMENT"] == "${ENVIRONMENT:-development}"


def test_staging_ws_hub_trust_does_not_use_a_broad_private_range() -> None:
    """The committed staging values do not invent deployment proxy peers."""
    staging = _values(STAGING_VALUES)
    trusted_proxies = (
        staging.get("wsHub", {}).get("config", {}).get("trustedProxies", [])
    )
    assert "10.0.0.0/8" not in trusted_proxies

    resources = _render_staging(release_name="staging-ws-hub-proxy-trust")
    deployment = _component_resource(resources, "Deployment", "ws-hub")
    env = {
        item["name"]: item.get("value")
        for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    # Render fixtures supply only reserved documentation peers; the committed
    # staging defaults remain loopback-only until operators provide real peers.
    assert env["TRUSTED_PROXIES"] == "198.51.100.12/32,2001:db8::12"


def test_file_processor_default_jwks_uses_release_backend_port_and_preserves_dependencies() -> (
    None
):
    release_name = "jwks-egress-contract"
    backend_port = 8181
    resources = _render_staging(
        "--set",
        f"backend.service.port={backend_port}",
        release_name=release_name,
    )
    backend = _component_resource(resources, "Deployment", "backend")
    processor = _component_resource(resources, "Deployment", "file-processor")
    backend_service_name = backend["metadata"]["name"]
    backend_service = next(
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"] == backend_service_name
    )
    backend_container = backend["spec"]["template"]["spec"]["containers"][0]
    backend_http_port = next(
        port["containerPort"]
        for port in backend_container["ports"]
        if port["name"] == "http"
    )
    assert backend_http_port == backend_port
    assert backend_service["spec"]["ports"][0]["port"] == backend_port
    assert backend_service["spec"]["ports"][0]["targetPort"] == "http"

    backend_labels = backend["spec"]["template"]["metadata"]["labels"]
    processor_labels = processor["spec"]["template"]["metadata"]["labels"]
    release_selector = {
        key: backend_labels[key]
        for key in ("app.kubernetes.io/name", "app.kubernetes.io/instance")
    }
    assert all(
        processor_labels[key] == value for key, value in release_selector.items()
    )
    backend_peer = {**release_selector, "app.kubernetes.io/component": "backend"}
    processor_peer = {
        **release_selector,
        "app.kubernetes.io/component": "file-processor",
    }
    backend_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-backend-policy"
    )
    processor_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-file-processor-policy"
    )
    assert backend_policy["spec"]["podSelector"]["matchLabels"] == {
        **release_selector,
        "app.kubernetes.io/component": "backend",
    }
    assert processor_policy["spec"]["podSelector"]["matchLabels"] == {
        **release_selector,
        "app.kubernetes.io/component": "file-processor",
    }

    backend_egress = [
        rule
        for rule in processor_policy["spec"]["egress"]
        if rule.get("to") == [{"podSelector": {"matchLabels": backend_peer}}]
    ]
    backend_ingress = [
        rule
        for rule in backend_policy["spec"]["ingress"]
        if rule.get("from") == [{"podSelector": {"matchLabels": processor_peer}}]
    ]
    expected_port = [{"protocol": "TCP", "port": backend_port}]
    assert len(backend_egress) == 1 and backend_egress[0]["ports"] == expected_port
    assert len(backend_ingress) == 1 and backend_ingress[0]["ports"] == expected_port

    processor_env = {
        entry["name"]: entry.get("value")
        for entry in processor["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert processor_env["FP_JWKS_URL"] == (
        f"http://{backend_service_name}:{backend_port}/.well-known/jwks.json"
    )

    expected_dependencies = {
        "nats": 4222,
        "temporal": 7233,
        "minio": 9000,
        "otel-collector": 4317,
    }
    for dependency, port in expected_dependencies.items():
        assert any(
            rule.get("to")
            == [
                {"podSelector": {"matchLabels": {"app.kubernetes.io/name": dependency}}}
            ]
            and rule.get("ports") == [{"protocol": "TCP", "port": port}]
            for rule in processor_policy["spec"]["egress"]
        )
    revocation_selector = {
        "app.kubernetes.io/name": "revocation-redis",
        "app.kubernetes.io/component": "master",
        "university-ecosystem.io/revocation-store-for": release_name,
    }
    assert any(
        rule.get("to") == [{"podSelector": {"matchLabels": revocation_selector}}]
        and rule.get("ports") == [{"protocol": "TCP", "port": 6379}]
        for rule in processor_policy["spec"]["egress"]
    )
    assert any(
        rule.get("ports") == [{"protocol": "TCP", "port": 443}]
        for rule in processor_policy["spec"]["egress"]
    )
    assert any(
        {("UDP", 53), ("TCP", 53)}
        == {(port["protocol"], port["port"]) for port in rule.get("ports", [])}
        for rule in processor_policy["spec"]["egress"]
    )


def test_file_processor_jwks_policies_are_scoped_to_each_release() -> None:
    policy_selectors: list[tuple[dict[str, str], dict[str, str]]] = []
    for release_name in ("jwks-egress-first", "jwks-egress-second"):
        resources = _render_staging(release_name=release_name)
        backend = _component_resource(resources, "Deployment", "backend")
        processor = _component_resource(resources, "Deployment", "file-processor")
        release_selector = {
            key: backend["spec"]["template"]["metadata"]["labels"][key]
            for key in ("app.kubernetes.io/name", "app.kubernetes.io/instance")
        }
        assert {
            key: processor["spec"]["template"]["metadata"]["labels"][key]
            for key in release_selector
        } == release_selector
        backend_peer = {**release_selector, "app.kubernetes.io/component": "backend"}
        processor_peer = {
            **release_selector,
            "app.kubernetes.io/component": "file-processor",
        }
        backend_policy = next(
            resource
            for resource in resources
            if resource.get("kind") == "NetworkPolicy"
            and resource["metadata"]["name"] == f"{release_name}-backend-policy"
        )
        processor_policy = next(
            resource
            for resource in resources
            if resource.get("kind") == "NetworkPolicy"
            and resource["metadata"]["name"] == f"{release_name}-file-processor-policy"
        )
        assert backend_policy["spec"]["podSelector"]["matchLabels"] == backend_peer
        assert processor_policy["spec"]["podSelector"]["matchLabels"] == processor_peer
        assert any(
            rule.get("to") == [{"podSelector": {"matchLabels": backend_peer}}]
            and rule.get("ports") == [{"protocol": "TCP", "port": 8000}]
            for rule in processor_policy["spec"]["egress"]
        )
        assert any(
            rule.get("from") == [{"podSelector": {"matchLabels": processor_peer}}]
            and rule.get("ports") == [{"protocol": "TCP", "port": 8000}]
            for rule in backend_policy["spec"]["ingress"]
        )
        policy_selectors.append((backend_peer, processor_peer))
    assert policy_selectors[0][0] != policy_selectors[1][0]
    assert policy_selectors[0][1] != policy_selectors[1][1]


def test_external_https_jwks_override_keeps_existing_443_egress_only() -> None:
    release_name = "jwks-external-contract"
    jwks_url = "https://issuer.example.invalid/.well-known/jwks.json"
    resources = _render_staging(
        "--set-string",
        f"fileProcessor.config.jwksURL={jwks_url}",
        release_name=release_name,
    )
    processor = _component_resource(resources, "Deployment", "file-processor")
    processor_env = {
        entry["name"]: entry.get("value")
        for entry in processor["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert processor_env["FP_JWKS_URL"] == jwks_url
    processor_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-file-processor-policy"
    )
    backend_policy = next(
        resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
        and resource["metadata"]["name"] == f"{release_name}-backend-policy"
    )
    assert not any(
        any(
            target.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "backend"
            for target in rule.get("to", [])
        )
        for rule in processor_policy["spec"]["egress"]
    )
    assert not any(
        any(
            source.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "file-processor"
            for source in rule.get("from", [])
        )
        for rule in backend_policy["spec"]["ingress"]
    )
    assert any(
        rule.get("ports") == [{"protocol": "TCP", "port": 443}]
        for rule in processor_policy["spec"]["egress"]
    )


_SERVICE_COMPONENTS = (
    "backend",
    "frontend",
    "gateway",
    "ws-hub",
    "file-processor",
)


@pytest.mark.parametrize("environment", ["development", "staging"])
@pytest.mark.parametrize(
    ("release", "full_override", "base"),
    [
        ("short", "", "short-university-ecosystem"),
        ("short", "campus", "campus"),
        ("short", "b" * 48, "b" * 48),
        ("r" * 53, "", "r" * 53 + "-universit"),
        ("short", "f" * 63, "f" * 63),
    ],
    ids=[
        "short-default",
        "short-full-override",
        "file-processor-exact-limit",
        "long-release",
        "long-full-override",
    ],
)
def test_first_party_service_names_and_references_fit_dns_labels(
    environment: str,
    release: str,
    full_override: str,
    base: str,
) -> None:
    assert shutil.which("helm") is not None, "Actual Helm rendering is required"
    overrides = (
        "--set-string",
        f"global.environment={environment}",
        "--set-string",
        f"fullnameOverride={full_override}",
    )
    resources = _render_staging(*overrides, release_name=release)
    services = {
        resource["metadata"]["labels"]["app.kubernetes.io/component"]: resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"].get("labels", {}).get("app.kubernetes.io/component")
        in _SERVICE_COMPONENTS
    }
    assert set(services) == set(_SERVICE_COMPONENTS)
    expected = {
        component: f"{base[: 62 - len(component)].rstrip('-')}-{component}"
        for component in _SERVICE_COMPONENTS
    }
    names = {
        component: resource["metadata"]["name"]
        for component, resource in services.items()
    }
    assert names == expected
    assert len(set(names.values())) == len(_SERVICE_COMPONENTS)
    assert all(
        len(name) <= 63 and re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", name)
        for name in names.values()
    )
    service_ports = {
        resource["metadata"]["name"]: {
            port["port"] for port in resource["spec"]["ports"]
        }
        for resource in services.values()
    }
    deployments = {
        resource["metadata"]["labels"]["app.kubernetes.io/component"]: resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and resource["metadata"].get("labels", {}).get("app.kubernetes.io/component")
        in _SERVICE_COMPONENTS
    }
    for component, service in services.items():
        labels = deployments[component]["spec"]["template"]["metadata"]["labels"]
        assert all(
            labels[key] == value for key, value in service["spec"]["selector"].items()
        )
    env = {
        component: {
            entry["name"]: entry["value"]
            for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
            if "value" in entry
        }
        for component, deployment in deployments.items()
    }
    backend = f"http://{names['backend']}:8000"
    jwks = f"{backend}/.well-known/jwks.json"
    assert env["frontend"]["BACKEND_ORIGIN"] == backend
    assert env["gateway"]["BACKEND_URL"] == backend
    assert env["gateway"]["FILE_PROCESSOR_ADDR"] == f"{names['file-processor']}:50051"
    assert env["file-processor"]["FP_JWKS_URL"] == jwks
    assert env["ws-hub"]["BACKEND_INTERNAL_URL"] == backend
    assert env["ws-hub"]["JWKS_URL"] == jwks
    if environment == "development":
        assert env["gateway"]["JWKS_ENDPOINT"] == jwks
    else:
        assert env["gateway"]["JWKS_ENDPOINT"] == (
            "https://api.university.staging.example.org/.well-known/jwks.json"
        )

    ingress_refs = [
        path["backend"]["service"]
        for resource in resources
        if resource.get("kind") == "Ingress"
        for rule in resource["spec"]["rules"]
        for path in rule["http"]["paths"]
    ]
    assert ingress_refs
    for reference in ingress_refs:
        assert reference["port"]["number"] in service_ports[reference["name"]]

    gateway_result = _render_gateway_template_isolated(
        "--set-string",
        f"fullnameOverride={full_override}",
        release_name=release,
    )
    assert gateway_result.returncode == 0, gateway_result.stderr
    gateway_resources = [
        resource
        for resource in yaml.safe_load_all(gateway_result.stdout)
        if isinstance(resource, dict)
    ]
    gateway_refs = [
        reference
        for resource in gateway_resources
        if resource.get("kind") == "HTTPRoute"
        for rule in resource["spec"]["rules"]
        for reference in rule.get("backendRefs", [])
    ]
    assert gateway_refs
    for reference in gateway_refs:
        assert reference["kind"] == "Service"
        assert reference["port"] in service_ports[reference["name"]]


@pytest.mark.parametrize("port", [3000, 3100], ids=["default", "override"])
def test_frontend_service_port_matches_node_listener(port: int) -> None:
    assert shutil.which("helm") is not None, "Actual Helm rendering is required"
    resources = _render_staging(
        "--set",
        f"frontend.service.port={port}",
        release_name="frontend-listener-contract",
    )
    deployment = _component_resource(resources, "Deployment", "frontend")
    service = _component_resource(resources, "Service", "frontend")
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert container["name"] == "frontend"
    assert "command" not in container
    assert "args" not in container
    runtime = (ROOT / "frontend.Dockerfile").read_text(encoding="utf-8")
    defaults = re.findall(r"^ENV PORT=([0-9]+)$", runtime, re.MULTILINE)
    assert defaults == ["3000"]
    assert 'CMD ["node", "scripts/server-prod.mjs"]' in runtime

    port_entries = [entry for entry in container["env"] if entry["name"] == "PORT"]
    assert len(port_entries) <= 1
    listener_port = defaults[0]
    if port_entries:
        assert "valueFrom" not in port_entries[0]
        listener_port = port_entries[0]["value"]
        assert isinstance(listener_port, str)
    assert listener_port == str(port)

    http_ports = [entry for entry in container["ports"] if entry["name"] == "http"]
    assert http_ports == [{"name": "http", "containerPort": port, "protocol": "TCP"}]
    assert service["spec"]["ports"] == [
        {
            "port": port,
            "targetPort": "http",
            "protocol": "TCP",
            "name": "http",
        }
    ]
    for probe in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert container[probe]["httpGet"] == {
            "path": "/healthz",
            "port": "http",
        }

    labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert all(
        labels[key] == value for key, value in service["spec"]["selector"].items()
    )
