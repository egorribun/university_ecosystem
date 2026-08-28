"""Regression contracts for bounded Docker Compose resource usage."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose(name: str) -> dict:
    source = (ROOT / name).read_text(encoding="utf-8")
    return yaml.safe_load(source.replace("!override", ""))


def _limits(compose_name: str, service_name: str) -> dict:
    service = _compose(compose_name)["services"][service_name]
    return service["deploy"]["resources"]["limits"]


def test_default_and_full_compose_bound_every_declared_service() -> None:
    for compose_name in ("docker-compose.yml", "docker-compose.full.yml"):
        services = _compose(compose_name)["services"]
        for service_name, service in services.items():
            limits = (service.get("deploy") or {}).get("resources", {}).get("limits")
            assert limits and limits.get("cpus") and limits.get("memory"), (
                compose_name,
                service_name,
            )


def test_observability_override_bounds_every_service_it_introduces() -> None:
    services = _compose("docker-compose.observability.yml")["services"]
    for service_name in (
        "tempo",
        "loki",
        "loki-healthprobe",
        "alloy",
        "pyroscope",
        "grafana",
        "prometheus",
        "redis-exporter",
    ):
        limits = (
            (services[service_name].get("deploy") or {})
            .get("resources", {})
            .get("limits")
        )
        assert limits and limits.get("cpus") and limits.get("memory"), service_name


def test_ephemeral_test_and_sandbox_stacks_are_bounded() -> None:
    for compose_name in ("docker-compose.test.yml", "docker-compose.sandbox.yml"):
        services = _compose(compose_name)["services"]
        for service_name, service in services.items():
            limits = (service.get("deploy") or {}).get("resources", {}).get("limits")
            assert limits and limits.get("cpus") and limits.get("memory"), (
                compose_name,
                service_name,
            )


def test_production_pooler_has_a_memory_ceiling() -> None:
    limits = _limits("docker-compose.prod.yml", "pgbouncer")
    assert limits == {"cpus": "0.25", "memory": "128M"}


def test_docker_context_excludes_quality_caches_and_reports() -> None:
    required_patterns = {"**/.cache/", "**/artifacts/", "**/.root-*/"}
    for name in (".dockerignore", "Dockerfile.test.dockerignore"):
        patterns = {
            line.strip()
            for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert required_patterns <= patterns, name
