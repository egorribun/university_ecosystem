"""AUD-164 / AUD-490: Compose wiring for the API's trusted peers and idempotency key.

The backend refuses to start in staging or production without a non-empty
TRUSTED_PROXIES for the HTTP API, and without IDEMPOTENCY_HMAC_SECRET. The
production overlay must supply both through required Compose syntax, and the
development stack must trust exactly the explicit subnets it declares.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_COMPOSE = "docker-compose.yml"
PROD_COMPOSE = "docker-compose.prod.yml"
BACKEND_IMAGE_SERVICES = (
    "backend",
    "notifications-worker",
    "outbox-worker",
    "migrations",
)
DEV_SUBNET_DEFAULTS = {
    "UE_PUBLIC_NET_SUBNET": "10.210.12.0/24",
    "UE_FRONTEND_NET_SUBNET": "10.210.11.0/24",
    "UE_SERVICE_NET_SUBNET": "10.210.10.0/24",
}


def _compose(relative_path: str) -> dict:
    # Compose merge tags are not YAML; the sibling compose contracts strip them the same way.
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return yaml.safe_load(source.replace("!override", "").replace("!reset", ""))


def test_production_api_requires_explicit_trusted_proxies_with_required_syntax() -> (
    None
):
    backend_env = _compose(PROD_COMPOSE)["services"]["backend"]["environment"]
    trusted = backend_env["TRUSTED_PROXIES"]
    assert trusted.startswith("${TRUSTED_PROXIES:?"), (
        "production must fail rendering when TRUSTED_PROXIES is absent (AUD-164)"
    )
    assert trusted.endswith("}")
    assert "production" in trusted


def test_production_idempotency_key_is_a_required_file_secret_for_every_backend_process() -> (
    None
):
    compose = _compose(PROD_COMPOSE)
    source = compose["secrets"]["idempotency_hmac_secret"]["file"]
    assert source.startswith("${IDEMPOTENCY_HMAC_SECRET_SOURCE_FILE:?"), (
        "IDEMPOTENCY_HMAC_SECRET must be supplied through a required source path (AUD-490)"
    )
    for service_name in BACKEND_IMAGE_SERVICES:
        service = compose["services"][service_name]
        assert "idempotency_hmac_secret" in service["secrets"], service_name
        assert (
            service["environment"]["IDEMPOTENCY_HMAC_SECRET_FILE"]
            == "/run/secrets/idempotency_hmac_secret"
        ), service_name
        assert "IDEMPOTENCY_HMAC_SECRET" not in service["environment"], service_name


def test_production_overlay_header_documents_the_new_required_sources() -> None:
    header = "\n".join(
        line
        for line in (REPO_ROOT / PROD_COMPOSE).read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    )
    assert (
        "#   IDEMPOTENCY_HMAC_SECRET_SOURCE_FILE=/etc/university/secrets/idempotency_hmac_secret"
        in header
    )
    assert "TRUSTED_PROXIES=" in header


def test_development_api_trusts_exactly_the_explicit_bridge_subnets() -> None:
    compose = _compose(BASE_COMPOSE)
    networks = compose["networks"]
    for name, default in (
        ("public", "UE_PUBLIC_NET_SUBNET"),
        ("frontend_net", "UE_FRONTEND_NET_SUBNET"),
        ("service_net", "UE_SERVICE_NET_SUBNET"),
    ):
        subnet = networks[name]["ipam"]["config"][0]["subnet"]
        assert subnet == f"${{{default}:-{DEV_SUBNET_DEFAULTS[default]}}}", name

    trusted = compose["services"]["backend"]["environment"]["TRUSTED_PROXIES"]
    assert trusted == ",".join(
        f"${{{variable}:-{value}}}" for variable, value in DEV_SUBNET_DEFAULTS.items()
    )


def test_development_api_trusts_every_network_that_caddy_shares_with_it() -> None:
    compose = _compose(BASE_COMPOSE)
    shared = set(compose["services"]["caddy"]["networks"]) & set(
        compose["services"]["backend"]["networks"]
    )
    assert shared == {"public", "frontend_net", "service_net"}
    trusted = compose["services"]["backend"]["environment"]["TRUSTED_PROXIES"]
    for network in shared:
        assert network in {"public", "frontend_net", "service_net"}
        variable = {
            "public": "UE_PUBLIC_NET_SUBNET",
            "frontend_net": "UE_FRONTEND_NET_SUBNET",
            "service_net": "UE_SERVICE_NET_SUBNET",
        }[network]
        assert f"${{{variable}:-" in trusted
