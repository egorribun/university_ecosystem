"""Regression contracts for the independently audited infrastructure fixes."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/university-ecosystem"


def test_helm_frontend_and_gateway_have_bounded_autoscaling_contracts() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    staging = yaml.safe_load(
        (CHART / "values-staging.yaml").read_text(encoding="utf-8")
    )

    assert values["frontend"]["resources"]["limits"]["memory"] == "512Mi"
    for component in ("frontend", "gateway"):
        autoscaling = values[component]["autoscaling"]
        assert autoscaling == {
            "enabled": False,
            "minReplicas": 2,
            "maxReplicas": 8,
            "targetCPUUtilizationPercentage": 70,
            "targetMemoryUtilizationPercentage": 80,
        }
        staging_autoscaling = staging[component]["autoscaling"]
        assert staging_autoscaling["enabled"] is True
        assert staging_autoscaling["minReplicas"] >= 2
        assert staging_autoscaling["maxReplicas"] >= staging_autoscaling["minReplicas"]


def test_helm_hpas_target_matching_deployments_and_avoid_keda_conflicts() -> None:
    for component in ("frontend", "gateway"):
        template = (CHART / "templates" / f"{component}-hpa.yaml").read_text(
            encoding="utf-8"
        )
        deployment = (CHART / "templates" / f"{component}-deployment.yaml").read_text(
            encoding="utf-8"
        )
        assert "apiVersion: autoscaling/v2" in template
        assert "kind: HorizontalPodAutoscaler" in template
        assert f".Values.{component}.autoscaling" in template
        assert (
            f'name: {{{{ include "university-ecosystem.fullname" . }}}}-{component}'
            in template
        )
        assert ".Values.keda.enabled" in template
        assert f".Values.{component}.autoscaling.enabled" in deployment


def test_backend_image_and_go_overlay_use_readiness_probes() -> None:
    dockerfile = (ROOT / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "127.0.0.1:8000/health/ready" in dockerfile
    assert "127.0.0.1:8000/healthz" not in dockerfile

    compose = yaml.safe_load(
        (ROOT / "docker-compose.go.yml").read_text(encoding="utf-8")
    )
    healthcheck = compose["services"]["file-processor"]["healthcheck"]
    assert healthcheck["test"] == [
        "CMD",
        "/usr/local/bin/grpc_health_probe",
        "-addr=:50051",
    ]


def test_observability_override_defines_tempo_healthprobe() -> None:
    source = (ROOT / "docker-compose.observability.yml").read_text(encoding="utf-8")
    marker = "  tempo-healthprobe:\n"
    assert marker in source
    probe = source[source.index(marker) :]
    assert 'network_mode: "service:tempo"' in probe
    assert "http://localhost:3200/ready" in probe
    assert "curlimages/curl:8.10.1@sha256:" in probe


def test_standalone_ingress_requires_explicit_certificate_issuer() -> None:
    source = (ROOT / "k8s/ingress.yaml").read_text(encoding="utf-8")
    assert 'cert-manager.io/cluster-issuer: "${CERT_MANAGER_ISSUER_NAME}"' in source
    assert 'cert-manager.io/cluster-issuer: "letsencrypt-prod"' not in source
    assert "CERT_MANAGER_ISSUER_NAME" in source


def test_raw_k8s_scope_declares_helm_as_canonical_application_producer() -> None:
    """Keep the raw-manifest scope and the Helm workload inventory aligned.

    The standalone tree intentionally omits the Go workloads.  This contract
    prevents a future documentation edit from presenting the partial raw
    bundle as a production deployment, while also making additions to the
    chart's first-party workload set visible in the canonical-owner guidance.
    """

    readme = (ROOT / "k8s/README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split()).lower()

    assert "sole canonical producer" in normalized
    assert "single canonical deployment artifact" in normalized
    assert "must not be used as a staging or production release path" in normalized
    assert "does not duplicate the go service deployments or services" in normalized

    deployment_templates = sorted(
        path.stem.removesuffix("-deployment")
        for path in (CHART / "templates").glob("*-deployment.yaml")
    )
    assert deployment_templates == [
        "backend",
        "file-processor",
        "frontend",
        "gateway",
        "outbox-worker",
        "ws-hub",
    ]
    for component in deployment_templates:
        assert f"`{component}`" in readme

    for component in ("gateway", "ws-hub", "file-processor"):
        assert not list((ROOT / "k8s").rglob(f"{component}*deployment*.yaml"))
