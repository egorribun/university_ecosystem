"""Production-like staging contracts for the University Ecosystem Helm chart."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
STAGING_VALUES = CHART / "values-staging.yaml"


def _values(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _helm() -> str:
    executable = shutil.which("helm")
    if executable is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun
    return executable


def _resolved_staging_args() -> list[str]:
    digest = "sha256:" + ("a" * 64)
    overrides = {
        "global.imageTag": "9d08136558b95d1182f889574f67b1b1d21abc9f",  # pragma: allowlist secret
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
        "revocationRedis.image.digest": digest,
        "revocationRedis.metrics.image.digest": digest,
        "nats.image.digest": digest,
        "backend.config.elasticsearchURL": "https://elasticsearch.staging.internal",
        "backend.config.flagdHost": "flagd.staging.internal",
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
    args: list[str] = []
    for key, value in overrides.items():
        args.extend(("--set-string", f"{key}={value}"))
    args.extend(("--set", "cwv.deploymentRunID=123"))
    args.extend(("--set", "cwv.deploymentRunAttempt=1"))
    return args


def _render_staging(
    *extra: str, release_name: str = "staging-contract"
) -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            release_name,
            str(CHART),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


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


def test_default_nats_values_use_upstream_jetstream_and_persistence_tree() -> None:
    values = _values(CHART / "values.yaml")
    nats = values["nats"]

    assert "nats" not in nats
    assert nats["jetstream"]["enabled"] is True
    assert nats["persistence"]["enabled"] is True
    assert nats["persistence"]["size"] == "10Gi"
    assert nats["image"]["pullPolicy"] == "Always"
    assert nats["auth"]["enabled"] is False
    assert nats["cluster"]["auth"]["enabled"] is False
    assert nats["existingSecret"] == ""


def test_canonical_staging_values_are_secure_and_fail_closed() -> None:
    values = _values(STAGING_VALUES)

    assert values["global"] == {
        "environment": "staging",
        "imageRegistry": "",
        "imageTag": "REQUIRED_GIT_SHA",
        "imagePullSecrets": ["ghcr-pull"],
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
    assert nats["jetstream"]["enabled"] is True
    assert nats["persistence"] == {"enabled": True, "size": "10Gi"}
    assert nats["replicaCount"] == 3

    for dependency in ("redis", "revocationRedis"):
        assert values[dependency]["image"]["registry"] == "docker.io"
        assert values[dependency]["image"]["repository"] == "bitnami/redis"
        assert values[dependency]["image"]["pullPolicy"] == "Always"
        assert values[dependency]["metrics"]["image"]["registry"] == "docker.io"
        assert values[dependency]["metrics"]["image"]["repository"] == (
            "bitnami/redis-exporter"
        )
        assert values[dependency]["metrics"]["image"]["pullPolicy"] == "Always"
        assert values[dependency]["networkPolicy"] == {
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
    assert values["nats"]["image"]["repository"] == "bitnami/nats"

    assert values["backend"]["autoscaling"]["enabled"] is True
    assert values["ingress"]["enabled"] is True
    assert values["ingress"]["tls"]
    assert values["backend"]["config"]["minioSecure"] is True
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
    assert values["fileProcessor"]["config"]["otlpInsecure"] is False


def test_chart_documents_staging_secret_and_release_contracts() -> None:
    documentation = (CHART / "README.md").read_text(encoding="utf-8")

    for required_text in (
        "values-staging.yaml",
        "university-application",
        "university-connections",
        "university-nats-config",
        "nats-server.conf",
        "REQUIRED_SHA256_DIGEST",
        "helm upgrade --install",
        "helm rollback",
    ):
        assert required_text in documentation

    assert "signature, SBOM, and provenance" not in documentation
    assert "docker.io/bitnami/redis" in documentation
    assert "docker.io/bitnami/redis-exporter" in documentation
    assert "docker.io/bitnami/nats" in documentation


def test_chart_lock_pins_the_reviewed_dependency_set() -> None:
    lock = _values(CHART / "Chart.lock")
    assert lock["dependencies"] == [
        {
            "name": "redis",
            "repository": "oci://registry-1.docker.io/bitnamicharts",
            "version": "20.13.4",
        },
        {
            "name": "redis",
            "repository": "oci://registry-1.docker.io/bitnamicharts",
            "version": "20.13.4",
        },
        {
            "name": "nats",
            "repository": "oci://registry-1.docker.io/bitnamicharts",
            "version": "8.5.4",
        },
    ]
    assert lock["digest"].startswith("sha256:")
    assert len(lock["digest"]) == 71
    assert (CHART / "charts" / "redis-20.13.4.tgz").is_file()
    assert (CHART / "charts" / "nats-8.5.4.tgz").is_file()


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
    assert resolved(properties["revocationRedis"])["additionalProperties"] is False
    assert properties["nats"]["additionalProperties"] is False


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
            "--set",
            invalid_override,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "additional properties" in result.stderr


def test_canonical_staging_values_reject_unresolved_required_markers() -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "staging-contract",
            str(CHART),
            "--dependency-update=false",
            "--values",
            str(STAGING_VALUES),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "unresolved REQUIRED_ marker" in result.stderr


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
        ("backup.minioClientImage", "minio/mc:latest"),
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
        "revocationRedis.auth.existingSecret=INVALID_REVOCATION_REDIS",
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
    assert "does not match pattern" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "redis.master.extraEnvVars[0].name=AWS_SECRET_ACCESS_KEY",
        "redis.replica.sidecars[0].image=busybox:1.36",
        "revocationRedis.master.initContainers[0].image=busybox:1.36",
        "revocationRedis.extraDeploy[0].kind=Secret",
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
    assert "arbitrary subchart" in result.stderr


@pytest.mark.parametrize(
    "override",
    [
        "redis.volumePermissions.enabled=true",
        "redis.sysctl.enabled=true",
        "revocationRedis.volumePermissions.enabled=true",
        "revocationRedis.sysctl.enabled=true",
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
    assert "unreviewed subchart helper containers" in result.stderr


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
    assert "NATS auth material must not be stored in Helm values" in result.stderr


@pytest.mark.parametrize(
    ("flag", "override", "expected"),
    [
        (
            "--set-string",
            "global.imageTag=mutable-tag",
            "global.imageTag must be the exact 40- or 64-character lowercase Git SHA",
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
            "nats.jetstream.enabled=false",
            "nats.jetstream.enabled=true and nats.persistence.enabled=true are required",
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
    assert expected in result.stderr


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
    "revocationRedis.auth.password=inline",
    "revocationRedis.auth.acl.users[0].password=inline",
    "revocationRedis.global.redis.password=inline",
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
    assert "secret material must not be stored in Helm values" in result.stderr


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
    assert contract["data"]["revocation-redis-secret-name"] == ("redis-credentials")
    assert json.loads(contract["data"]["revocation-redis-secret-keys.json"]) == [
        "redis-password"
    ]
    assert json.loads(contract["data"]["dependency-images.json"]) == {
        "nats": "docker.io/bitnami/nats@sha256:" + ("a" * 64),
        "redis": "docker.io/bitnami/redis@sha256:" + ("a" * 64),
        "redis.metrics": ("docker.io/bitnami/redis-exporter@sha256:" + ("a" * 64)),
        "revocationRedis": "docker.io/bitnami/redis@sha256:" + ("a" * 64),
        "revocationRedis.metrics": (
            "docker.io/bitnami/redis-exporter@sha256:" + ("a" * 64)
        ),
    }
    assert json.loads(contract["data"]["dependency-chart-versions.json"]) == {
        "nats": "8.5.4",
        "redis": "20.13.4",
        "revocationRedis": "20.13.4",
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
                "docker.io/bitnami/redis@",
                "docker.io/bitnami/redis-exporter@",
                "docker.io/bitnami/nats@",
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
        if volume["name"] == "config"
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

    gateway_container = gateway["spec"]["template"]["spec"]["containers"][0]
    processor_container = processor["spec"]["template"]["spec"]["containers"][0]
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
    assert gateway_env["GRPC_CA_FILE"].endswith("/ca.crt")
    assert gateway_env["GRPC_CLIENT_CERT_FILE"].endswith("/tls.crt")
    assert gateway_env["GRPC_CLIENT_KEY_FILE"].endswith("/tls.key")
    assert processor_env["FP_GRPC_TLS_CERT_FILE"].endswith("/tls.crt")
    assert processor_env["FP_GRPC_TLS_KEY_FILE"].endswith("/tls.key")
    assert processor_env["FP_GRPC_CLIENT_CA_FILE"].endswith("/ca.crt")
    assert processor_env["FP_GRPC_ALLOWED_CLIENT_URIS"] == (
        "spiffe://university.ecosystem/ns/university-ecosystem/sa/gateway"
    )
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

    volumes = {
        volume["name"]: volume["secret"]
        for volume in processor["spec"]["template"]["spec"]["volumes"]
        if "secret" in volume
    }
    assert volumes["internal-grpc-mtls-server"]["secretName"] == (
        "university-internal-grpc-file-processor-server"
    )
    assert "internal-grpc-mtls-probe" not in volumes
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


def test_ws_hub_env_uses_only_explicit_values_and_secret_refs() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployment = _component_resource(resources, "Deployment", "ws-hub")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}

    application_secret = "university-application"  # pragma: allowlist secret
    connection_secret = "university-connections"  # pragma: allowlist secret
    assert env["JWT_SECRET"]["valueFrom"]["secretKeyRef"] == {
        "name": application_secret,
        "key": "jwt-secret",
    }
    assert env["WS_HUB_INTERNAL_SECRET"]["valueFrom"]["secretKeyRef"] == {
        "name": application_secret,
        "key": "ws-hub-internal-secret",
    }
    for variable, key in {
        "NATS_URL": "nats-url",
        "NATS_AUTH_TOKEN": "nats-auth-token",
        "REDIS_URL": "redis-backend-url",
        "REVOCATION_REDIS_URL": "redis-revocation-url",
    }.items():
        assert env[variable]["valueFrom"]["secretKeyRef"] == {
            "name": connection_secret,
            "key": key,
        }
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
    assert ingress_ports == {8081}
    backend_policy = _component_resource(resources, "NetworkPolicy", "backend")
    backend_sources = [
        source.get("podSelector", {}).get("matchLabels", {})
        for rule in backend_policy["spec"]["ingress"]
        for source in rule.get("from", [])
    ]
    assert {"app.kubernetes.io/component": "ws-hub"} in backend_sources


def test_dependency_network_policies_require_explicit_client_labels() -> None:
    resources = _render_staging(release_name="university-ecosystem")
    deployments = {
        resource["metadata"]["labels"]["app.kubernetes.io/component"]: resource
        for resource in resources
        if resource.get("kind") == "Deployment"
        and "app.kubernetes.io/component"
        in resource.get("metadata", {}).get("labels", {})
    }
    expected = {
        "backend": {"redis", "revocationRedis", "nats"},
        "gateway": {"redis", "revocationRedis"},
        "ws-hub": {"redis", "revocationRedis", "nats"},
        "file-processor": {"nats"},
        "outbox-worker": {"redis", "revocationRedis", "nats"},
    }
    for component, dependencies in expected.items():
        labels = deployments[component]["spec"]["template"]["metadata"]["labels"]
        for dependency in dependencies:
            assert labels[f"university-ecosystem-{dependency}-client"] == "true"

    policy_names = {
        resource["metadata"]["name"]
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
    }
    assert {
        "university-ecosystem-redis",
        "university-ecosystem-revocationRedis",
        "university-ecosystem-nats",
    } <= policy_names


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
        "revocationRedis.networkPolicy.allowExternal=true",
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
        ("--set-string", "revocationRedis.image.repository=attacker/redis"),
        (
            "--set-string",
            "revocationRedis.metrics.image.repository=attacker/exporter",
        ),
        ("--set-string", "nats.image.repository=attacker/nats"),
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
        for marker in ("dependency image repository", "allowInsecureImages")
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
    assert "/ingress/issuer/kind" in result.stderr


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
