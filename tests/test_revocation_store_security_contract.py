"""Fail-closed durability and metrics-boundary contracts for revocation Redis."""

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
CHART = ROOT / "charts" / "revocation-store"
VALUES = CHART / "values-staging.yaml"
DEPLOY_SCRIPT = ROOT / ".github" / "scripts" / "deploy-revocation-store.sh"
C2_BACKEND_DIGEST = (
    "sha256:38d6b346ff695004f8445e2ec92cfb0d80c044a1a0c776ca71a5b24e078c70f2"
)
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
    ("--set-string", "redis.fullnameOverride=attacker-redis"),
    (
        "--set-string",
        "redis.commonLabels.university-ecosystem\\.io/revocation-store-for=attacker",
    ),
    ("--set-string", "redis.commonLabels.app\\.kubernetes\\.io/instance=attacker"),
    ("--set-string", "redis.auth.existingSecret=redis-credentials"),
    ("--set-string", "redis.auth.existingSecretPasswordKey=redis-password"),
    ("--set-string", "redis.image.registry=attacker.invalid"),
    ("--set-string", "redis.image.repository=attacker/redis"),
    ("--set-string", "redis.image.tag=latest"),
    ("--set-string", "redis.image.digest=not-a-digest"),
    ("--set-string", "redis.image.pullPolicy=IfNotPresent"),
    ("--set", "redis.master.count=2"),
    ("--set", "redis.master.revisionHistoryLimit=0"),
    ("--set", "redis.master.terminationGracePeriodSeconds=0"),
    ("--set-string", "redis.master.updateStrategy.type=OnDelete"),
    ("--set-string", "redis.master.resources.requests.cpu=10m"),
    ("--set-string", "redis.master.resources.limits.memory=1Gi"),
    ("--set", "redis.master.persistence.enabled=false"),
    ("--set-string", "redis.master.persistence.size=1Gi"),
    ("--set", "redis.master.persistentVolumeClaimRetentionPolicy.enabled=false"),
    (
        "--set-string",
        "redis.master.persistentVolumeClaimRetentionPolicy.whenDeleted=Delete",
    ),
    (
        "--set-string",
        "redis.master.persistentVolumeClaimRetentionPolicy.whenScaled=Delete",
    ),
    ("--set", "redis.master.pdb.minAvailable=0"),
    ("--set-string", "redis.commonConfiguration=maxmemory 1mb"),
    (
        "--set-json",
        'redis.master.disableCommands=["ACL","CONFIG","FLUSHDB","FLUSHALL",'
        '"FUNCTION","MIGRATE","MODULE","MONITOR","REPLICAOF","SLAVEOF"]',
    ),
    ("--set", "redis.networkPolicy.enabled=false"),
    ("--set-string", "redis.networkPolicy.clientPodLabel=attacker-client"),
    ("--set-string", "redis.networkPolicy.monitoringNamespace=default"),
    ("--set", "redis.metrics.enabled=false"),
    ("--set-string", "redis.metrics.image.repository=attacker/exporter"),
    ("--set-string", "redis.metrics.image.tag=latest"),
    ("--set-string", "redis.metrics.image.digest=not-a-digest"),
    ("--set-string", "redis.metrics.image.pullPolicy=IfNotPresent"),
    ("--set", "redis.metrics.port=9122"),
    ("--set-string", "redis.metrics.resources.limits.cpu=10m"),
    (
        "--set-string",
        "redis.metrics.passwordFileInitImage.repository=attacker.invalid/owner/repo/backend",
    ),
    (
        "--set-string",
        "redis.metrics.passwordFileInitImage.digest=sha256:" + ("d" * 64),
    ),
    (
        "--set-string",
        "global.backendImageRepository=attacker.invalid/owner/repo/backend",
    ),
)


def _helm() -> str:
    executable = shutil.which("helm")
    if executable is None:
        pytest.skip("Helm is not installed")  # QUALITY-123 @egorribun
    return executable


def _resolved_args(release_name: str) -> list[str]:
    """Mirror only the immutable arguments passed by the deployment wrapper."""

    digest = "sha256:" + ("b" * 64)
    backend_digest = C2_BACKEND_DIGEST
    overrides = {
        "applicationReleaseName": release_name,
        "redis.fullnameOverride": f"{release_name}-revocation-redis",
        "redis.commonLabels.university-ecosystem\\.io/revocation-store-for": (
            release_name
        ),
        "redis.commonLabels.app\\.kubernetes\\.io/instance": release_name,
        "redis.auth.existingSecret": ("revocation-redis-credentials"),
        "redis.auth.existingSecretPasswordKey": ("revocation-redis-password"),
        "redis.image.digest": digest,
        "redis.metrics.image.digest": digest,
        "global.backendImageRepository": (
            "ghcr.io/egorribun/university_ecosystem/backend"
        ),
        "global.backendImageDigest": backend_digest,
        "redis.metrics.passwordFileInitImage.repository": (
            "ghcr.io/egorribun/university_ecosystem/backend"
        ),
        "redis.metrics.passwordFileInitImage.digest": backend_digest,
        "redis.metrics.passwordFileInitImage.pullPolicy": "Always",
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


def test_values_and_schema_lock_durability_and_metrics_ingress() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    redis_values = values["redis"]
    assert redis_values["master"]["disableCommands"] == DISABLED_REDIS_COMMANDS
    assert redis_values["auth"] == {
        "existingSecret": "revocation-redis-credentials",
        "existingSecretPasswordKey": ("revocation-redis-password"),
    }
    assert redis_values["master"]["terminationGracePeriodSeconds"] == 30
    assert redis_values["master"]["persistence"] == {"enabled": True, "size": "2Gi"}
    assert redis_values["master"]["persistentVolumeClaimRetentionPolicy"] == {
        "enabled": True,
        "whenScaled": "Retain",
        "whenDeleted": "Retain",
    }
    assert redis_values["commonConfiguration"] == (
        "maxmemory 384mb\nmaxmemory-policy noeviction\nsave 60 1\n"
        "appendonly yes\nappendfsync everysec"
    )
    assert redis_values["networkPolicy"] == {
        "enabled": True,
        "monitoringNamespace": "monitoring",
    }

    redis_schema = schema["properties"]["redis"]
    auth_schema = redis_schema["properties"]["auth"]
    master_schema = redis_schema["properties"]["master"]
    policy_schema = redis_schema["properties"]["networkPolicy"]
    metrics_schema = redis_schema["properties"]["metrics"]
    password_file_image_schema = metrics_schema["properties"]["passwordFileInitImage"]
    assert master_schema["properties"]["disableCommands"] == {
        "const": DISABLED_REDIS_COMMANDS
    }
    assert master_schema["properties"]["terminationGracePeriodSeconds"] == {"const": 30}
    assert master_schema["properties"]["revisionHistoryLimit"] == {"const": 10}
    assert master_schema["properties"]["updateStrategy"]["properties"]["type"] == {
        "const": "RollingUpdate"
    }
    assert master_schema["properties"]["persistence"]["properties"]["size"] == {
        "const": "2Gi"
    }
    retention_properties = master_schema["properties"][
        "persistentVolumeClaimRetentionPolicy"
    ]["properties"]
    when_deleted = retention_properties["whenDeleted"]
    assert when_deleted == {"const": "Retain"}
    assert policy_schema["properties"]["enabled"] == {"const": True}
    assert "clientPodLabel" not in policy_schema["properties"]
    assert policy_schema["properties"]["monitoringNamespace"] == {"const": "monitoring"}
    assert metrics_schema["properties"]["enabled"] == {"const": True}
    assert metrics_schema["properties"]["port"] == {"const": 9121}
    assert password_file_image_schema["required"] == [
        "repository",
        "tag",
        "digest",
        "pullPolicy",
    ]
    assert password_file_image_schema["properties"]["digest"]["pattern"] == (
        "^(REQUIRED_SHA256_DIGEST|sha256:[0-9a-f]{64})$"
    )
    global_schema = schema["properties"]["global"]
    assert global_schema["required"] == ["backendImageRepository", "backendImageDigest"]
    assert "backendImageRepository" in global_schema["properties"]
    assert redis_schema["properties"]["commonLabels"]["additionalProperties"] is False
    assert auth_schema["properties"]["existingSecret"] == {
        "const": "revocation-redis-credentials"
    }
    assert auth_schema["properties"]["existingSecretPasswordKey"] == {
        "const": "revocation-redis-password"
    }


def test_revocation_store_uses_first_party_chart_without_remote_dependencies() -> None:
    """Bootstrap chart controls are source-owned and require no external chart fetch."""

    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart["type"] == "application"
    assert chart.get("dependencies", []) == []
    assert not (CHART / "Chart.lock").exists()
    chart_dependencies = CHART / "charts"
    assert not chart_dependencies.exists() or not any(chart_dependencies.iterdir())

    for relative in (
        "templates/_helpers.tpl",
        "templates/validate-config.yaml",
        "templates/redis-configmap.yaml",
        "templates/redis-networkpolicy.yaml",
        "templates/redis-pdb.yaml",
        "templates/redis-serviceaccount.yaml",
        "templates/redis-services.yaml",
        "templates/redis-statefulset.yaml",
        "templates/deployment-contract.yaml",
    ):
        template = CHART / relative
        assert template.is_file()
        assert not template.is_symlink()
        assert template.stat().st_size > 0

    deploy_script = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "verify_first_party_chart()" in deploy_script
    verify_mode = 'if [[ "$mode" == "verify-vendor" || "$mode" == "verify-chart" ]]'
    assert verify_mode in deploy_script
    assert "helm dependency list" in deploy_script
    assert "helm dependency build" not in deploy_script
    assert "helm dependency update" not in deploy_script
    assert "sha256sum --status --check" not in deploy_script
    assert "curl " not in deploy_script
    assert "wget " not in deploy_script
    assert "redis.image.repository=redis" in deploy_script
    assert "oliver006/redis_exporter" in deploy_script
    assert "preflight_existing_datastore_image()" in deploy_script
    assert "timeout --signal=TERM --kill-after=2s 10s" in deploy_script
    assert "--request-timeout=8s" in deploy_script
    assert '"${statefulset_name}-0"' in deploy_script
    assert "--container redis -- redis-server --version" in deploy_script
    assert "version_output" in deploy_script
    assert "kubectl get pvc" in deploy_script
    assert "retained revocation PVC exists without its StatefulSet" in deploy_script
    assert "recognized stable Redis 7.4 variant" in deploy_script
    assert "--ignore-not-found" in deploy_script
    assert (
        'jsonpath={.metadata.name}|{.spec.template.spec.containers[?(@.name=="redis")].image}'
        in deploy_script
    )
    assert "not from an identified Redis repository" in deploy_script
    assert deploy_script.index(
        "preflight_existing_datastore_image\n    helm upgrade --install"
    ) < deploy_script.index("helm upgrade --install")


def _msys_path(path: Path) -> str:
    if os.name != "nt":
        return path.resolve().as_posix()

    resolved = str(path.resolve())
    drive, tail = os.path.splitdrive(resolved)
    if len(drive) != 2 or drive[1] != ":":
        raise AssertionError(f"Git Bash path is not drive-qualified: {resolved}")
    return f"/{drive[0].lower()}{tail.replace(chr(92), '/')}"


def _git_bash_path(stub_bin: Path) -> str:
    if os.name != "nt":
        return os.pathsep.join((str(stub_bin), os.environ.get("PATH", "")))

    git_root = Path(r"C:\Program Files\Git")
    return ":".join(
        _msys_path(path)
        for path in (stub_bin, git_root / "usr" / "bin", git_root / "bin")
    )


def test_upgrade_preflight_allows_first_install_and_rejects_other_pvc_engines(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        assert Path(r"C:\Program Files\Git\bin\bash.exe").is_file()
    else:
        assert Path("/bin/bash").is_file()

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    kubectl = stub_bin / "kubectl"
    kubectl.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == get && "${2:-}" == statefulset ]]; then
  if [[ "${FAKE_KUBECTL_GET_ERROR:-}" == 1 ]]; then
    echo forbidden >&2
    exit 1
  fi
  printf '%s' "${FAKE_STATEFULSET:-}"
  exit 0
fi
if [[ "${1:-}" == get && "${2:-}" == pvc ]]; then
  if [[ "${FAKE_KUBECTL_PVC_ERROR:-}" == 1 ]]; then
    echo forbidden >&2
    exit 1
  fi
  printf '%s' "${FAKE_PVC_STATE:-}"
  exit 0
fi
if [[ "${1:-}" == exec ]]; then
  printf 'called\\n' > "$FAKE_EXEC_MARKER"
  if [[ "${FAKE_KUBECTL_EXEC_ERROR:-}" == 1 ]]; then
    echo forbidden >&2
    exit 1
  fi
  printf '%s' "${FAKE_REDIS_VERSION:-}"
  exit 0
fi
echo unexpected kubectl invocation >&2
exit 2
""",
        encoding="utf-8",
    )
    kubectl.chmod(0o755)
    helm = stub_bin / "helm"
    helm.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == dependency && "${2:-}" == list ]]; then
  printf 'NAME VERSION REPOSITORY STATUS\\n'
  exit 0
fi
if [[ "${1:-}" == upgrade && "${2:-}" == --install ]]; then
  printf 'called\\n' > "$FAKE_HELM_MARKER"
  exit 0
fi
echo unexpected helm invocation >&2
exit 2
""",
        encoding="utf-8",
    )
    helm.chmod(0o755)

    marker = tmp_path / "helm-upgrade-called"
    exec_marker = tmp_path / "kubectl-exec-called"
    env = os.environ.copy()
    env.update(
        {
            "PATH": _git_bash_path(stub_bin),
            "DEPLOY_ENVIRONMENT": "development",
            "K8S_NAMESPACE": "university-ecosystem",
            "HELM_RELEASE_NAME": "university-ecosystem",
            "REVOCATION_REDIS_IMAGE_DIGEST": "sha256:" + ("a" * 64),
            "REVOCATION_REDIS_METRICS_IMAGE_DIGEST": "sha256:" + ("b" * 64),
            "REGISTRY": "ghcr.io",
            "GITHUB_REPOSITORY": "egorribun/university_ecosystem",
            "BACKEND_IMAGE_DIGEST": C2_BACKEND_DIGEST,
            "FAKE_HELM_MARKER": _msys_path(marker),
            "FAKE_EXEC_MARKER": _msys_path(exec_marker),
        }
    )
    statefulset_name = "university-ecosystem-revocation-redis-master"
    digest = "sha256:" + ("c" * 64)
    expected_pvc = f"redis-data-{statefulset_name}-0"
    cases = (
        ("", True, "", False, False, False, "", False),
        ("", False, "", False, False, True, expected_pvc, False),
        ("", False, "", False, False, True, "", False),
        (
            f"{statefulset_name}|docker.io/bitnami/redis@{digest}",
            True,
            "Redis server v=7.4.3 sha=fixture bits=64",
            True,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis@{digest}",
            True,
            "Redis server v=7.4.11 sha=fixture bits=64",
            True,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis:7.4.11-alpine@{digest}",
            True,
            "Redis server v=7.4.11 sha=fixture bits=64",
            True,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/bitnami/redis@{digest}",
            False,
            "Redis server v=8.0.0 sha=fixture bits=64",
            True,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/bitnami/redis@{digest}",
            False,
            "",
            True,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/bitnami/redis@{digest}",
            False,
            "",
            True,
            False,
            False,
            "",
            True,
        ),
        (
            f"{statefulset_name}|docker.io/bitnami/redis:7.4.3-debian-12-r2",
            True,
            "",
            False,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis:7.4.11-alpine",
            True,
            "",
            False,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis:8.10.2-alpine",
            False,
            "",
            False,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis:8.10.2-alpine@{digest}",
            False,
            "Redis server v=7.4.11 sha=fixture bits=64",
            False,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/redis:7.4.11-rc1",
            False,
            "",
            False,
            False,
            False,
            "",
            False,
        ),
        (
            f"{statefulset_name}|docker.io/valkey/valkey:9.1.2-alpine@{digest}",
            False,
            "",
            False,
            False,
            False,
            "",
            False,
        ),
        ("", False, "", False, True, False, "", False),
    )
    for (
        statefulset_state,
        allowed,
        version,
        expect_exec,
        get_error,
        pvc_error,
        pvc_state,
        exec_error,
    ) in cases:
        marker.unlink(missing_ok=True)
        exec_marker.unlink(missing_ok=True)
        env["FAKE_STATEFULSET"] = statefulset_state
        env["FAKE_REDIS_VERSION"] = version
        env["FAKE_KUBECTL_GET_ERROR"] = "1" if get_error else ""
        env["FAKE_KUBECTL_PVC_ERROR"] = "1" if pvc_error else ""
        env["FAKE_PVC_STATE"] = pvc_state
        env["FAKE_KUBECTL_EXEC_ERROR"] = "1" if exec_error else ""
        if os.name == "nt":
            result = subprocess.run(
                [
                    r"C:\Program Files\Git\bin\bash.exe",
                    ".github/scripts/deploy-revocation-store.sh",
                    "upgrade",
                ],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        else:
            result = subprocess.run(
                ["/bin/bash", ".github/scripts/deploy-revocation-store.sh", "upgrade"],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        assert (result.returncode == 0) is allowed, result.stderr
        assert marker.exists() is allowed
        assert exec_marker.exists() is expect_exec
        if not allowed:
            assert "refusing" in result.stderr
        if expect_exec:
            assert "Redis server v=" not in result.stderr
            assert "Redis server v=" not in result.stdout


def test_revocation_store_render_preserves_durability_and_monitoring_only_metrics() -> (
    None
):
    resources = _render()
    statefulset = next(
        resource for resource in resources if resource.get("kind") == "StatefulSet"
    )
    pod_spec = statefulset["spec"]["template"]["spec"]
    init_containers = {
        container["name"]: container for container in pod_spec["initContainers"]
    }
    init_container = init_containers["redis-auth-acl"]
    assert init_container["resources"] == {
        "requests": {"cpu": "50m", "memory": "32Mi"},
        "limits": {"cpu": "250m", "memory": "128Mi"},
    }
    password_init = init_containers["redis-exporter-password-file"]
    assert password_init["image"] == (
        "ghcr.io/egorribun/university_ecosystem/backend@" + C2_BACKEND_DIGEST
    )
    assert password_init["securityContext"]["runAsUser"] == 10001
    assert password_init["securityContext"]["runAsGroup"] == 10001
    password_script = password_init["args"][password_init["args"].index("-c") + 1]
    compile(password_script, "<redis-exporter-password-file-init>", "exec")
    assert pod_spec["securityContext"]["fsGroup"] == 10001
    exporter = next(
        container
        for container in pod_spec["containers"]
        if container["name"] == "metrics"
    )
    assert exporter["env"] == [
        {"name": "REDIS_ADDR", "value": "redis://127.0.0.1:6379"},
        {"name": "REDIS_USER", "value": "default"},
        {
            "name": "REDIS_PASSWORD_FILE",
            "value": "/run/redis-exporter-auth/passwords.json",
        },
    ]
    assert not any(item.get("name") == "REDIS_PASSWORD" for item in exporter["env"])
    volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
    assert volumes["redis-exporter-auth"]["emptyDir"] == {
        "medium": "Memory",
        "sizeLimit": "8Mi",
    }
    assert {
        "name": "redis-exporter-auth",
        "mountPath": "/run/redis-exporter-auth",
        "readOnly": True,
    } in exporter["volumeMounts"]
    configuration = next(
        resource
        for resource in resources
        if resource.get("kind") == "ConfigMap"
        and resource["metadata"]["name"]
        == "revocation-security-contract-revocation-redis-master-configuration"
    )
    network_policy = next(
        resource for resource in resources if resource.get("kind") == "NetworkPolicy"
    )

    assert (
        statefulset["metadata"]["name"]
        == "revocation-security-contract-revocation-redis-master"
    )
    legacy_selector = {
        "app.kubernetes.io/instance": "revocation-security-contract",
        "app.kubernetes.io/name": "revocation-redis",
        "app.kubernetes.io/component": "master",
    }
    assert statefulset["spec"]["selector"]["matchLabels"] == legacy_selector
    assert statefulset["spec"]["serviceName"] == (
        "revocation-security-contract-revocation-redis-headless"
    )
    assert statefulset["spec"]["persistentVolumeClaimRetentionPolicy"] == {
        "whenDeleted": "Retain",
        "whenScaled": "Retain",
    }
    client_selectors = [
        source["podSelector"]["matchLabels"]
        for rule in network_policy["spec"]["ingress"]
        if {port["port"] for port in rule.get("ports", [])} == {6379}
        for source in rule.get("from", [])
        if "podSelector" in source
    ]
    assert {
        "revocation-security-contract-revocation-redis-client": "true"
    } in client_selectors
    claim_template = statefulset["spec"]["volumeClaimTemplates"][0]
    assert claim_template["apiVersion"] == "v1"
    assert claim_template["kind"] == "PersistentVolumeClaim"
    assert claim_template["metadata"]["name"] == "redis-data"
    # Match published Bitnami VCT labels exactly; Helm cannot mutate these on upgrade.
    assert claim_template["metadata"]["labels"] == legacy_selector
    assert claim_template["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert claim_template["spec"]["resources"]["requests"]["storage"] == "2Gi"
    assert "storageClassName" not in claim_template["spec"]
    assert "volumeMode" not in claim_template["spec"]
    master_service = next(
        resource
        for resource in resources
        if resource.get("kind") == "Service"
        and resource["metadata"]["name"]
        == "revocation-security-contract-revocation-redis-master"
    )
    assert master_service["spec"]["selector"] == legacy_selector
    pdb = next(
        resource
        for resource in resources
        if resource.get("kind") == "PodDisruptionBudget"
        and resource["metadata"]["name"]
        == "revocation-security-contract-revocation-redis-master"
    )
    assert pdb["spec"]["selector"]["matchLabels"] == legacy_selector
    assert (
        statefulset["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 30
    )
    master_config = configuration["data"]["master.conf"]
    for command in DISABLED_REDIS_COMMANDS:
        assert f'rename-command {command} ""' in master_config

    metrics_rule = next(
        rule
        for rule in network_policy["spec"]["ingress"]
        if rule["ports"] == [{"port": 9121, "protocol": "TCP"}]
    )
    assert metrics_rule["from"] == [
        {
            "namespaceSelector": {
                "matchLabels": {"kubernetes.io/metadata.name": "monitoring"}
            }
        }
    ]


@pytest.mark.parametrize(("flag", "override"), SECURITY_BYPASSES)
def test_revocation_store_rejects_durability_and_metrics_bypasses(
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
    if override.startswith(("redis.fullnameOverride=", "redis.commonLabels.")):
        assert (
            "revocation-store release identity and labels are immutable"
            in result.stderr
        )
    elif override.startswith(
        ("redis.metrics.passwordFileInitImage.", "global.backendImageRepository=")
    ):
        assert (
            "revocation exporter password-file init image must be the exact source-pinned backend image"
            in result.stderr
        )
    else:
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
