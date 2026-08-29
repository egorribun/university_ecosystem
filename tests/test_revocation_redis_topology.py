"""Deployment contracts for the isolated durable revocation datastore."""

from pathlib import Path

import pytest
import yaml


def _find_repo_root() -> Path | None:
    """Locate the checkout when mutmut executes a copied test module.

    mutmut materialises tests below ``mutants/``; resolving ``parents[1]``
    there points at the temporary copy rather than the repository checkout.
    Keep these deployment-contract tests hermetic in both locations.
    """

    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "k8s").is_dir():
            return candidate
    return None


REPO_ROOT = _find_repo_root()
if REPO_ROOT is None or not (REPO_ROOT / "docker-compose.yml").is_file():
    pytest.skip(  # QUALITY-123 @egorribun
        "repository deployment assets are unavailable in isolated mutation copy",
        allow_module_level=True,
    )


def _compose(name: str) -> dict:
    assert REPO_ROOT is not None
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


def test_compose_revocation_store_has_a_disjoint_password_and_private_network() -> None:
    """Cache-only workers cannot connect to, or authenticate with, revocation Redis."""

    for compose_name, store_name, direct_consumers, worker_names in (
        (
            "docker-compose.yml",
            "revocation-valkey",
            ("backend", "migrations"),
            ("notifications-worker", "outbox-worker"),
        ),
        (
            "docker-compose.full.yml",
            "revocation-redis",
            ("backend", "migrations", "gateway", "ws-hub"),
            ("notifications-worker", "outbox-worker"),
        ),
    ):
        compose = _compose(compose_name)
        services = compose["services"]
        networks = compose["networks"]
        store = services[store_name]

        assert networks["revocation_net"] == {"internal": True}, compose_name
        assert store["networks"] == ["revocation_net"], compose_name
        assert any(
            "REVOCATION_REDIS_PASSWORD" in str(argument)
            for argument in store["command"]
        ), compose_name
        assert "REVOCATION_REDIS_PASSWORD" in store["environment"]["REDIS_PASSWORD"]

        for service_name in direct_consumers:
            service = services[service_name]
            assert "revocation_net" in service["networks"], (
                compose_name,
                service_name,
            )
            assert (
                "REVOCATION_REDIS_PASSWORD"
                in service["environment"]["REVOCATION_REDIS_URL"]
            )
            assert store_name in service["depends_on"]

        for worker_name in worker_names:
            worker = services[worker_name]
            assert "REVOCATION_REDIS_URL" not in worker["environment"], (
                compose_name,
                worker_name,
            )
            assert store_name not in worker["depends_on"], (compose_name, worker_name)
            assert "revocation_net" not in worker["networks"], (
                compose_name,
                worker_name,
            )
            assert worker["environment"]["REVOCATION_REDIS_ACCESS_ENABLED"] == "false"


def test_full_stack_workers_use_a_generated_redacted_environment_file() -> None:
    """A broad full-stack env_file must never give workers revocation credentials."""

    services = _compose("docker-compose.full.yml")["services"]

    for worker_name in ("notifications-worker", "outbox-worker"):
        assert services[worker_name]["env_file"] == [".env.docker.workers"]


def test_go_overlay_joins_the_private_revocation_network_with_a_distinct_password() -> (
    None
):
    services = _compose("docker-compose.go.yml")["services"]

    for service_name in ("gateway", "ws-hub"):
        service = services[service_name]
        assert "revocation_net" in service["networks"]
        assert (
            "REVOCATION_REDIS_PASSWORD"
            in service["environment"]["REVOCATION_REDIS_URL"]
        )


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


def test_base_migration_hook_uses_the_dedicated_revocation_store() -> None:
    """The local irreversible migration cannot fall back to DB-only revocation."""

    services = _compose("docker-compose.yml")["services"]
    migration = services["migrations"]
    backend_env = services["backend"]["environment"]

    assert (
        migration["environment"]["REVOCATION_REDIS_URL"]
        == backend_env["REVOCATION_REDIS_URL"]
    )
    assert migration["depends_on"]["revocation-valkey"]["condition"] == (
        "service_healthy"
    )
    assert migration["networks"] == ["db_net", "revocation_net"]


def test_full_migration_hook_uses_the_dedicated_revocation_store() -> None:
    """The full Docker topology cannot degrade the migration to DB-only revocation."""

    services = _compose("docker-compose.full.yml")["services"]
    migration = services["migrations"]
    backend_env = services["backend"]["environment"]

    assert (
        migration["environment"]["REVOCATION_REDIS_URL"]
        == backend_env["REVOCATION_REDIS_URL"]
    )
    assert migration["depends_on"]["revocation-redis"]["condition"] == (
        "service_healthy"
    )
    assert migration["networks"] == ["internal", "revocation_net"]


def test_helm_declares_isolated_durable_revocation_dependency() -> None:
    app_chart = yaml.safe_load(
        (REPO_ROOT / "charts/university-ecosystem/Chart.yaml").read_text(
            encoding="utf-8"
        )
    )
    store_chart = yaml.safe_load(
        (REPO_ROOT / "charts/revocation-store/Chart.yaml").read_text(encoding="utf-8")
    )
    app_values = _compose("charts/university-ecosystem/values.yaml")
    store_values = _compose("charts/revocation-store/values.yaml")

    assert all(
        dependency.get("alias") != "revocationRedis"
        for dependency in app_chart["dependencies"]
    )
    assert "revocationRedis" not in app_values
    assert app_values["connections"]["redisRevocationURLKey"] == (
        "redis-revocation-url"
    )
    assert store_chart["dependencies"] == [
        {
            "name": "redis",
            "version": "20.13.4",
            "repository": "oci://registry-1.docker.io/bitnamicharts",
        }
    ]
    revocation = store_values["redis"]
    assert revocation["nameOverride"] == "revocation-redis"
    assert revocation["auth"]["existingSecret"] == "revocation-redis-credentials"
    assert (
        revocation["auth"]["existingSecretPasswordKey"] == "revocation-redis-password"
    )
    assert (
        revocation["auth"]["existingSecret"]
        != app_values["redis"]["auth"]["existingSecret"]
    )
    assert (
        revocation["auth"]["existingSecretPasswordKey"]
        != app_values["redis"]["auth"]["existingSecretPasswordKey"]
    )
    assert revocation["master"]["persistence"]["enabled"] is True
    assert revocation["master"]["persistentVolumeClaimRetentionPolicy"] == {
        "enabled": True,
        "whenScaled": "Retain",
        "whenDeleted": "Retain",
    }
    configuration = revocation["commonConfiguration"]
    assert "maxmemory-policy noeviction" in configuration
    assert "appendonly yes" in configuration


def test_bootstrap_script_uses_a_separate_atomic_release_before_the_app_hook() -> None:
    assert REPO_ROOT is not None
    script = (REPO_ROOT / ".github/scripts/deploy-revocation-store.sh").read_text(
        encoding="utf-8"
    )

    assert 'chart="charts/revocation-store"' in script
    assert 'store_release="${HELM_RELEASE_NAME}-revocation-store"' in script
    assert 'store_fullname="${HELM_RELEASE_NAME}-revocation-redis"' in script
    assert '"redis.fullnameOverride=$store_fullname"' in script
    assert (
        '"redis.commonLabels.university-ecosystem\\\\.io/revocation-store-for=$HELM_RELEASE_NAME"'
        in script
    )
    assert (
        '"redis.commonLabels.app\\\\.kubernetes\\\\.io/instance=$HELM_RELEASE_NAME"'
        in script
    )
    assert '"redis.image.digest=$REVOCATION_REDIS_IMAGE_DIGEST"' in script
    assert (
        '"redis.metrics.image.digest=$REVOCATION_REDIS_METRICS_IMAGE_DIGEST"' in script
    )
    assert 'redis_secret_name="revocation-redis-credentials"' in script
    assert 'redis_secret_key="revocation-redis-password"' in script
    assert 'helm upgrade --install "$store_release"' in script
    for required_flag in ("--atomic", "--wait", "--history-max 10"):
        assert required_flag in script
    assert "CACHE_REDIS_URL" not in script
