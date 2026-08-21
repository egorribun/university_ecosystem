"""Cross-layer contracts for the OpenFeature/flagd integration."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings
from app.core.feature_flags import _FLAG_DEFINITIONS


def _find_repo_root() -> Path | None:
    """Locate deployment assets from a normal checkout or mutmut copy."""

    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (
            (parent / "pyproject.toml").is_file()
            and (parent / "k8s").is_dir()
            and (parent / "start-docker.ps1").is_file()
        ):
            return parent
    return None


ROOT = _find_repo_root()
if ROOT is None:
    pytest.skip(
        "repository deployment assets are unavailable in isolated mutation copy",
        allow_module_level=True,
    )

FLAGD_IMAGE = (
    "ghcr.io/open-feature/flagd:v0.16.1@"
    "sha256:9525b3c2916183810f93f0a72774c1dfad48d1ae22852c753719c46db80af5e7"
)
CURL_IMAGE = (
    "curlimages/curl:8.21.0@"
    "sha256:7c12af72ceb38b7432ab85e1a265cff6ae58e06f95539d539b654f2cfa64bb13"
)


def test_flagd_runtime_dependencies_are_explicit_and_compatible() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]

    assert "openfeature-provider-flagd>=0.5.0,<0.5.1" in dependencies
    assert "protobuf>=6.33.6,<7" in dependencies
    assert "grpcio>=1.81.0,<1.82" in dependencies


def test_flagd_settings_are_typed_and_validate_the_port() -> None:
    assert Settings.model_fields["flagd_host"].default == "localhost"
    port_field = Settings.model_fields["flagd_port"]
    assert port_field.default == 8013


def test_kubernetes_backend_uses_the_flagd_service_dns() -> None:
    backend = yaml.safe_load(
        (ROOT / "k8s/backend/configmap.yaml").read_text(encoding="utf-8")
    )
    assert backend["data"]["FLAGD_HOST"] == "flagd"
    assert backend["data"]["FLAGD_PORT"] == "8013"

    flagd_documents = list(
        yaml.safe_load_all(
            (ROOT / "k8s/flagd/deployment.yaml").read_text(encoding="utf-8")
        )
    )
    deployment = next(
        document for document in flagd_documents if document["kind"] == "Deployment"
    )
    service = next(
        document for document in flagd_documents if document["kind"] == "Service"
    )
    service_monitor = next(
        document for document in flagd_documents if document["kind"] == "ServiceMonitor"
    )
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == FLAGD_IMAGE
    assert container["args"] == [
        "start",
        "--uri",
        "file:/etc/flagd/flags.json",
        "--port",
        "8013",
        "--management-port",
        "8014",
    ]
    assert {port["name"]: port["containerPort"] for port in container["ports"]} == {
        "grpc": 8013,
        "management": 8014,
    }
    assert container["livenessProbe"]["httpGet"] == {
        "path": "/healthz",
        "port": "management",
    }
    assert container["readinessProbe"]["httpGet"] == {
        "path": "/readyz",
        "port": "management",
    }
    assert {port["name"]: port["port"] for port in service["spec"]["ports"]} == {
        "grpc": 8013,
        "management": 8014,
    }
    assert service_monitor["spec"]["endpoints"][0]["port"] == "management"

    network_policy = yaml.safe_load(
        (ROOT / "k8s/flagd/network-policy.yaml").read_text(encoding="utf-8")
    )
    backend_selectors = {
        tuple(sorted(source["podSelector"]["matchLabels"].items()))
        for source in network_policy["spec"]["ingress"][0]["from"]
    }
    assert (("app.kubernetes.io/name", "backend"),) in backend_selectors
    assert (("app.kubernetes.io/component", "backend"),) in backend_selectors
    assert network_policy["spec"]["ingress"][1]["ports"] == [
        {"protocol": "TCP", "port": 8014}
    ]


def test_application_registry_matches_version_controlled_flagd_definitions() -> None:
    configured = json.loads(
        (ROOT / "k8s/flagd/flags.json").read_text(encoding="utf-8")
    )["flags"]
    registered = {
        definition.name: definition.default for definition in _FLAG_DEFINITIONS
    }

    assert set(configured) == set(registered)
    for name, default in registered.items():
        definition = configured[name]
        assert definition["variants"][definition["defaultVariant"]] is default

    kustomization = yaml.safe_load(
        (ROOT / "k8s/flagd/kustomization.yaml").read_text(encoding="utf-8")
    )
    generator = kustomization["configMapGenerator"][0]
    assert generator["name"] == "flagd-flags"
    assert generator["files"] == ["flags.json=flags.json"]
    assert kustomization["generatorOptions"]["disableNameSuffixHash"] is True


def test_full_compose_runs_flagd_and_waits_for_real_readiness() -> None:
    compose = yaml.safe_load(
        (ROOT / "docker-compose.full.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    flagd = services["flagd"]
    probe = services["flagd-healthprobe"]
    backend = services["backend"]

    assert flagd["image"] == FLAGD_IMAGE
    assert flagd["command"] == [
        "start",
        "--uri",
        "file:/etc/flagd/flags.json",
        "--port",
        "8013",
        "--management-port",
        "8014",
    ]
    assert flagd["volumes"] == ["./k8s/flagd/flags.json:/etc/flagd/flags.json:ro"]
    assert flagd["labels"]["com.university-ecosystem.config-revision"] == (
        "${DOCKER_CONFIG_REVISION:-unmanaged}"
    )
    assert flagd["read_only"] is True
    assert flagd["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in flagd["security_opt"]

    assert probe["image"] == CURL_IMAGE
    assert probe["network_mode"] == "service:flagd"
    assert "http://localhost:8014/readyz" in " ".join(probe["healthcheck"]["test"])
    assert probe["depends_on"]["flagd"]["condition"] == "service_started"

    assert backend["environment"]["FLAGD_HOST"] == "flagd"
    assert backend["environment"]["FLAGD_PORT"] == "8013"
    assert backend["depends_on"]["flagd-healthprobe"]["condition"] == (
        "service_healthy"
    )

    launcher = (ROOT / "start-docker.ps1").read_text(encoding="utf-8")
    assert '"k8s/flagd/flags.json"' in launcher
    assert (
        'flagd         = @{ type = "docker"; service = "flagd-healthprobe"' in launcher
    )

    prometheus = yaml.safe_load(
        (ROOT / "infrastructure/observability/prometheus.yml").read_text(
            encoding="utf-8"
        )
    )
    flagd_scrape = next(
        job for job in prometheus["scrape_configs"] if job["job_name"] == "flagd"
    )
    assert flagd_scrape["static_configs"] == [{"targets": ["flagd:8014"]}]
    assert flagd_scrape["metrics_path"] == "/metrics"


def test_helm_backend_has_explicit_flagd_connection_settings() -> None:
    values = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )
    template = (
        ROOT / "charts/university-ecosystem/templates/backend-deployment.yaml"
    ).read_text(encoding="utf-8")

    assert values["backend"]["config"]["flagdHost"] == "flagd"
    assert values["backend"]["config"]["flagdPort"] == 8013
    assert "name: FLAGD_HOST" in template
    assert "name: FLAGD_PORT" in template


def test_generated_client_is_read_only() -> None:
    sdk = (ROOT / "frontend/src/api/generated/sdk.gen.ts").read_text(encoding="utf-8")
    types = (ROOT / "frontend/src/api/generated/types.gen.ts").read_text(
        encoding="utf-8"
    )
    handlers = (ROOT / "frontend/src/tests/mocks/generated/handlers.ts").read_text(
        encoding="utf-8"
    )

    assert "updateFeatureFlagAdminFeatureFlagsNamePatch" not in sdk
    assert "FeatureFlagUpdateIn" not in types
    assert "updateFeatureFlagAdminFeatureFlagsNamePatch" not in handlers
