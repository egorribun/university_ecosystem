"""Fail-closed durability and metrics-boundary contracts for revocation Redis."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "revocation-store"
VALUES = CHART / "values-staging.yaml"
VENDORED_REDIS_ARCHIVE = CHART / "charts" / "redis-20.13.4.tgz"
VENDORED_REDIS_CHECKSUM = CHART / "redis-20.13.4.tgz.sha256"
VENDORED_REDIS_SHA256 = "4c83fd15af8cd755ef8984b8b089413b10dbed16da1a87859ea1a2b086e11e14"  # pragma: allowlist secret
DEPLOY_SCRIPT = ROOT / ".github" / "scripts" / "deploy-revocation-store.sh"
DISABLED_REDIS_COMMANDS = [
    "ACL",
    "CONFIG",
    "FLUSHDB",
    "FLUSHALL",
    "FUNCTION",
    "MIGRATE",
    "MODULE",
    "MONITOR",
    "REPLICAOF",
    "SLAVEOF",
    "SHUTDOWN",
]

# Every entry is deliberately exercised twice: Helm schema validation rejects
# ordinary user input, and the chart template rejects the same bypass when a
# caller uses --skip-schema-validation.  This protects the bootstrap contract
# from both accidental values drift and a hostile CI/CLI invocation.
SECURITY_BYPASSES = (
    ("--set-string", "redis.commonConfiguration=maxmemory 1mb"),
    ("--set", "redis.architecture=replication"),
    ("--set", "redis.enabled=false"),
    ("--set-string", "redis.nameOverride=attacker-redis"),
    ("--set-string", "redis.commonLabels.team=attacker"),
    (
        "--set-string",
        "redis.commonLabels.app\\.kubernetes\\.io/name=attacker",
    ),
    ("--set", "redis.networkPolicy.enabled=false"),
    ("--set", "redis.networkPolicy.allowExternal=true"),
    ("--set", "redis.networkPolicy.allowExternalEgress=true"),
    ("--set", "redis.networkPolicy.metrics.allowExternal=true"),
    (
        "--set-string",
        "redis.networkPolicy.metrics.ingressNSMatchLabels.team=attacker",
    ),
    ("--set", "redis.auth.enabled=false"),
    ("--set-string", "redis.auth.existingSecret="),
    ("--set-string", "redis.auth.existingSecret=redis-credentials"),
    ("--set-string", "redis.auth.existingSecretPasswordKey=redis-password"),
    ("--set", "redis.auth.usePasswordFiles=false"),
    ("--set", "redis.master.count=2"),
    ("--set-string", "redis.master.count=1"),
    ("--set", "redis.master.revisionHistoryLimit=0"),
    ("--set", "redis.master.minReadySeconds=30"),
    ("--set-string", "redis.master.updateStrategy.type=OnDelete"),
    ("--set", "redis.master.updateStrategy.rollingUpdate.partition=1"),
    ("--set", "redis.master.terminationGracePeriodSeconds=0"),
    ("--set-json", "redis.master.disableCommands=[]"),
    ("--set-json", 'redis.master.disableCommands=["FLUSHDB","FLUSHALL"]'),
    ("--set-string", "redis.master.resources.limits.cpu=10m"),
    ("--set", "redis.master.readinessProbe.enabled=false"),
    ("--set", "redis.master.livenessProbe.enabled=false"),
    ("--set", "redis.master.startupProbe.enabled=true"),
    ("--set", "redis.master.containerSecurityContext.privileged=true"),
    ("--set-string", "redis.master.containerSecurityContext.procMount=Unmasked"),
    (
        "--set-json",
        'redis.master.containerSecurityContext.capabilities.add=["SYS_ADMIN"]',
    ),
    (
        "--set-string",
        "redis.master.podSecurityContext.seccompProfile.type=Unconfined",
    ),
    ("--set-string", "redis.master.persistence.existingClaim=attacker-pvc"),
    ("--set-string", "redis.master.persistence.dataSource.kind=VolumeSnapshot"),
    ("--set-json", 'redis.master.persistence.accessModes=["ReadWriteMany"]'),
    ("--set-string", "redis.master.service.clusterIP=10.0.0.7"),
    ("--set", "redis.master.persistenceOverride=true"),
    ("--set", "redis.metrics.enabled=false"),
    ("--set-string", "redis.metrics.resources.limits.cpu=10m"),
    ("--set", "redis.metrics.readinessProbe.enabled=false"),
    ("--set", "redis.metrics.livenessProbe.enabled=false"),
    ("--set", "redis.metrics.startupProbe.enabled=true"),
    ("--set", "redis.metrics.containerSecurityContext.privileged=true"),
    ("--set-string", "redis.metrics.containerSecurityContext.procMount=Unmasked"),
    ("--set", "redis.metrics.serviceMonitor.enabled=true"),
    ("--set", "redis.metrics.podMonitor.enabled=true"),
    ("--set", "redis.metrics.prometheusRule.enabled=true"),
    ("--set", "redis.useExternalDNS.enabled=true"),
    ("--set-string", "redis.image.repository=attacker/redis"),
    ("--set-string", "redis.image.digest=not-a-digest"),
    ("--set-string", "redis.metrics.image.repository=attacker/exporter"),
    ("--set-string", "redis.global.storageClass=unreviewed"),
    ("--set-string", "redis.clusterDomain=attacker.local"),
    ("--set", "redis.useHostnames=false"),
    ("--set", "redis.configmapChecksumAnnotations=false"),
)


def _helm() -> str:
    executable = shutil.which("helm")
    if executable is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun
    return executable


def _resolved_args(release_name: str) -> list[str]:
    """Mirror only the immutable arguments passed by the deployment wrapper."""

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
    }
    args: list[str] = []
    for key, value in overrides.items():
        args.extend(("--set-string", f"{key}={value}"))
    return args


def _template_command(*extra: str, skip_schema_validation: bool = False) -> list[str]:
    command = [
        _helm(),
        "template",
        "revocation-security-contract",
        str(CHART),
        "--dependency-update=false",
    ]
    if skip_schema_validation:
        command.append("--skip-schema-validation")
    command.extend(
        [
            "--namespace",
            "university-ecosystem",
            "--values",
            str(VALUES),
            *_resolved_args("revocation-security-contract"),
            *extra,
        ]
    )
    return command


def _render() -> list[dict[str, Any]]:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _template_command(),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [resource for resource in yaml.safe_load_all(result.stdout) if resource]


def test_revocation_store_values_and_schema_lock_durability_and_metrics_ingress() -> (
    None
):
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    assert values["redis"]["master"]["disableCommands"] == DISABLED_REDIS_COMMANDS
    assert (
        values["redis"]["auth"]
        == {
            "enabled": True,
            "existingSecret": "revocation-redis-credentials",  # pragma: allowlist secret
            "existingSecretPasswordKey": "revocation-redis-password",  # pragma: allowlist secret
        }
    )
    assert values["redis"]["master"]["terminationGracePeriodSeconds"] == 30
    assert values["redis"]["networkPolicy"]["metrics"] == {
        "allowExternal": False,
        "ingressNSMatchLabels": {"kubernetes.io/metadata.name": "monitoring"},
        "ingressNSPodMatchLabels": {},
    }

    redis_schema = schema["properties"]["redis"]
    auth_schema = redis_schema["properties"]["auth"]
    master_schema = redis_schema["properties"]["master"]
    metrics_policy_schema = redis_schema["properties"]["networkPolicy"]["properties"][
        "metrics"
    ]
    assert master_schema["properties"]["disableCommands"] == {
        "const": DISABLED_REDIS_COMMANDS
    }
    assert master_schema["properties"]["terminationGracePeriodSeconds"] == {"const": 30}
    assert master_schema["properties"]["revisionHistoryLimit"] == {"const": 10}
    assert master_schema["properties"]["minReadySeconds"] == {"const": 0}
    assert metrics_policy_schema["properties"]["allowExternal"] == {"const": False}
    assert metrics_policy_schema["properties"]["ingressNSMatchLabels"]["properties"][
        "kubernetes.io/metadata.name"
    ] == {"const": "monitoring"}
    assert redis_schema["properties"]["commonLabels"]["additionalProperties"] is False
    assert master_schema["properties"]["updateStrategy"] == {
        "const": {"type": "RollingUpdate"}
    }
    assert auth_schema["properties"]["existingSecret"] == {
        "const": "revocation-redis-credentials"
    }
    assert auth_schema["properties"]["existingSecretPasswordKey"] == {
        "const": "revocation-redis-password"
    }


def test_revocation_store_uses_a_reviewed_offline_vendored_dependency() -> None:
    """A bootstrap deployment must not fetch a mutable chart over the network."""

    assert VENDORED_REDIS_ARCHIVE.is_file()
    assert not VENDORED_REDIS_ARCHIVE.is_symlink()
    assert not VENDORED_REDIS_CHECKSUM.is_symlink()
    assert hashlib.sha256(VENDORED_REDIS_ARCHIVE.read_bytes()).hexdigest() == (
        VENDORED_REDIS_SHA256
    )
    assert VENDORED_REDIS_CHECKSUM.read_text(encoding="utf-8") == (
        f"{VENDORED_REDIS_SHA256}  charts/redis-20.13.4.tgz\n"
    )

    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert 'vendor_archive="$chart/charts/redis-20.13.4.tgz"' in deploy_script
    assert "sha256sum --status --check" in deploy_script
    assert "helm dependency build" not in deploy_script
    assert "helm dependency update" not in deploy_script
    assert "curl " not in deploy_script
    assert "wget " not in deploy_script


def test_revocation_store_render_preserves_durability_and_monitoring_only_metrics() -> (
    None
):
    resources = _render()
    statefulset = next(
        resource for resource in resources if resource.get("kind") == "StatefulSet"
    )
    configuration = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"]
        == "revocation-security-contract-revocation-redis-configuration"
    )
    network_policy = next(
        resource for resource in resources if resource.get("kind") == "NetworkPolicy"
    )

    assert (
        statefulset["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 30
    )
    master_config = configuration["data"]["master.conf"]
    for command in DISABLED_REDIS_COMMANDS:
        assert f'rename-command {command} ""' in master_config

    metrics_rule = next(
        rule
        for rule in network_policy["spec"]["ingress"]
        if rule["ports"] == [{"port": 9121}]
    )
    assert metrics_rule["from"] == [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "monitoring"}
            }
        }
    ]


@pytest.mark.parametrize(("flag", "override"), SECURITY_BYPASSES)
def test_revocation_store_schema_rejects_durability_and_metrics_bypasses(
    flag: str, override: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _template_command(flag, override),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize(("flag", "override"), SECURITY_BYPASSES)
def test_revocation_store_template_defense_in_depth_rejects_schema_bypasses(
    flag: str, override: str
) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        _template_command(flag, override, skip_schema_validation=True),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert "revocation-store" in result.stderr
