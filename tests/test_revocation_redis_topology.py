"""Deployment contracts for the isolated durable revocation datastore."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _compose(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / name).read_text(encoding="utf-8"))


def test_full_compose_uses_one_revocation_namespace() -> None:
    services = _compose("docker-compose.full.yml")["services"]
    backend_env = services["backend"]["environment"]
    gateway_env = services["gateway"]["environment"]
    ws_hub_env = services["ws-hub"]["environment"]
    revocation = services["revocation-redis"]

    assert gateway_env["REVOCATION_REDIS_URL"] == backend_env["REVOCATION_REDIS_URL"]
    assert ws_hub_env["REVOCATION_REDIS_URL"] == backend_env["REVOCATION_REDIS_URL"]
    assert backend_env["REVOCATION_REDIS_URL"] != backend_env["CACHE_REDIS_URL"]
    assert gateway_env["REDIS_URL"].endswith("/3")
    assert gateway_env["REVOCATION_REDIS_URL"].endswith("/0")
    assert str(ws_hub_env["REDIS_DB"]) == "0"
    assert "--appendonly" in revocation["command"]
    assert "yes" in revocation["command"]
    assert "noeviction" in revocation["command"]
    assert revocation["volumes"]


def test_hardened_revocation_stores_start_as_the_image_valkey_user() -> None:
    """Dropping every capability must not break the entrypoint's UID switch."""
    for compose_name, service_name in (
        ("docker-compose.yml", "revocation-valkey"),
        ("docker-compose.full.yml", "revocation-redis"),
    ):
        revocation = _compose(compose_name)["services"][service_name]

        assert revocation["user"] == "999:1000", compose_name
        assert revocation["cap_drop"] == ["ALL"], compose_name
        assert "no-new-privileges:true" in revocation["security_opt"], compose_name


def test_composed_go_stack_uses_one_revocation_namespace() -> None:
    base_services = _compose("docker-compose.yml")["services"]
    backend_env = base_services["backend"]["environment"]
    go_services = _compose("docker-compose.go.yml")["services"]
    gateway_env = go_services["gateway"]["environment"]
    ws_hub_env = go_services["ws-hub"]["environment"]

    assert gateway_env["REVOCATION_REDIS_URL"] == backend_env["REVOCATION_REDIS_URL"]
    assert ws_hub_env["REVOCATION_REDIS_URL"] == backend_env["REVOCATION_REDIS_URL"]
    assert backend_env["REVOCATION_REDIS_URL"] != backend_env["CACHE_REDIS_URL"]
    assert gateway_env["REDIS_URL"].endswith("/3")
    assert gateway_env["REVOCATION_REDIS_URL"].endswith("/0")
    assert str(ws_hub_env["REDIS_DB"]) == "0"
    assert ws_hub_env["REDIS_PASSWORD"]


def test_helm_declares_isolated_durable_revocation_dependency() -> None:
    chart = yaml.safe_load(
        (REPO_ROOT / "charts/university-ecosystem/Chart.yaml").read_text(
            encoding="utf-8"
        )
    )
    values = _compose("charts/university-ecosystem/values.yaml")

    dependency = next(
        dependency
        for dependency in chart["dependencies"]
        if dependency.get("alias") == "revocationRedis"
    )
    assert dependency["condition"] == "revocationRedis.enabled"
    assert values["connections"]["redisRevocationURLKey"] == "redis-revocation-url"
    assert values["revocationRedis"]["master"]["persistence"]["enabled"] is True
    configuration = values["revocationRedis"]["commonConfiguration"]
    assert "maxmemory-policy noeviction" in configuration
    assert "appendonly yes" in configuration
