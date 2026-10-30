"""AUD-506: Temporal verifies JWT signing keys only over TLS from the internal edge.

Temporal's claim mapper trusts whatever keys its JWKS source returns, so the
source must be an https URL whose certificate chains to a trust anchor that
Temporal itself receives. Both Compose stacks serve that URL from Caddy's
internal TLS listener (caddy:8443) and copy only the public root certificate
into a read-only volume. The caddy_data volume also holds the CA private key,
so Temporal must never mount it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPORAL_ENTRYPOINT = REPO_ROOT / "services" / "temporal" / "entrypoint.sh"
TEMPORAL_CONFIG = REPO_ROOT / "services" / "temporal" / "config.yaml"
JWKS_URL = "https://caddy:8443/.well-known/jwks.json"
COMPOSE_STACKS = ("docker-compose.yml", "docker-compose.full.yml")


def _compose(relative_path: str) -> dict:
    # Compose merge tags are not YAML; the sibling compose contracts strip them the same way.
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return yaml.safe_load(source.replace("!override", "").replace("!reset", ""))


def _volume_sources(service: dict) -> set[str]:
    sources: set[str] = set()
    for volume in service.get("volumes", []):
        if isinstance(volume, str):
            sources.add(volume.split(":", 1)[0])
        else:
            sources.add(str(volume.get("source", "")))
    return sources


def _dependency_conditions(service: dict) -> dict[str, str]:
    return {
        name: (spec or {}).get("condition", "")
        for name, spec in service.get("depends_on", {}).items()
    }


def test_temporal_config_fetches_keys_from_rendered_url_and_uses_default_authorizer() -> (
    None
):
    config = yaml.safe_load(TEMPORAL_CONFIG.read_text(encoding="utf-8"))
    authorization = config["global"]["authorization"]
    assert authorization["jwtKeyProvider"]["keySourceURIs"] == ["${TEMPORAL_JWKS_URL}"]
    assert authorization["claimMapper"] == "default"
    assert authorization["authorizer"] == "default"


@pytest.mark.parametrize(
    "jwks_url",
    [
        "http://backend:8000/.well-known/jwks.json",
        "https:/caddy/.well-known/jwks.json",
        "caddy:8443/.well-known/jwks.json",
        "https://caddy:8443/a|b",
        "https://caddy:8443/a b",
    ],
)
def test_temporal_entrypoint_refuses_to_start_without_an_https_jwks_url(
    jwks_url: str, tmp_path: Path
) -> None:
    """Plain HTTP, scheme-less or unsafe JWKS URLs exit before temporal-server runs."""
    shell = shutil.which("sh")
    assert shell, "POSIX sh is required to exercise the Temporal entrypoint"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "POSTGRES_USER": "temporal",
        "POSTGRES_PWD": tmp_path.name,
        "TEMPORAL_JWKS_URL": jwks_url,
        "TEMPORAL_JWKS_CA_FILE": str(tmp_path / "missing-root.crt"),
    }
    result = subprocess.run(  # noqa: S603 - fixed shell running the repository entrypoint
        [shell, str(TEMPORAL_ENTRYPOINT)],
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert b"temporal-server" not in result.stdout


def test_temporal_entrypoint_trusts_only_the_mounted_jwks_root_in_addition_to_system_roots() -> (
    None
):
    entrypoint = TEMPORAL_ENTRYPOINT.read_text(encoding="utf-8")
    assert (
        'TEMPORAL_JWKS_CA_FILE="${TEMPORAL_JWKS_CA_FILE:-/etc/temporal/jwks-ca/root.crt}"'
        in (entrypoint)
    )
    assert "until [ -s " in entrypoint
    assert "export SSL_CERT_FILE=/tmp/temporal-jwks-ca-bundle.pem" in entrypoint
    assert "${TEMPORAL_JWKS_URL}|${TEMPORAL_JWKS_URL}|g" in entrypoint
    # The renderer must not place the CA private key or the whole Caddy data
    # directory in Temporal's trust path.
    assert "caddy_data" not in entrypoint
    assert "/caddy-data" not in entrypoint


@pytest.mark.parametrize("relative_path", COMPOSE_STACKS)
def test_compose_temporal_gets_https_jwks_url_and_only_the_public_root(
    relative_path: str,
) -> None:
    services = _compose(relative_path)["services"]
    temporal = services["temporal"]
    assert temporal["environment"]["TEMPORAL_JWKS_URL"] == JWKS_URL
    assert temporal["entrypoint"] == [
        "/bin/sh",
        "/etc/temporal/wave144-entrypoint.sh",
    ]

    trust_mounts = [
        volume
        for volume in temporal["volumes"]
        if isinstance(volume, str)
        and volume.startswith("temporal")
        and ":/etc/temporal/jwks-ca" in volume
    ]
    assert trust_mounts, "Temporal must mount the JWKS trust anchor volume"
    assert trust_mounts[0].endswith(":ro")
    anchor_volume = trust_mounts[0].split(":", 1)[0]

    caddy_data_volumes = {
        name for name in _volume_sources(temporal) if "caddy" in name.lower()
    }
    assert caddy_data_volumes == set(), "Temporal must not mount Caddy's CA state"

    conditions = _dependency_conditions(temporal)
    assert conditions.get("caddy") == "service_started"
    assert conditions.get("temporal-jwks-ca") == "service_completed_successfully"

    exporter = services["temporal-jwks-ca"]
    assert exporter["network_mode"] == "none"
    assert exporter["restart"] == "no"
    assert exporter["depends_on"]["caddy"]["condition"] == "service_started"
    exporter_volumes = exporter["volumes"]
    assert any(
        isinstance(volume, str)
        and volume.endswith(":ro")
        and volume.split(":", 1)[0] in {"caddy_data", "caddy-data"}
        and ":/caddy-data" in volume
        for volume in exporter_volumes
    ), "the exporter reads Caddy's state read-only"
    assert f"{anchor_volume}:/out" in exporter_volumes

    command = "\n".join(exporter["command"])
    assert "/caddy-data/caddy/pki/authorities/local/root.crt" in command
    assert "cp " in command
    assert "root.key" not in command
    assert "/out/root.crt" in command

    declared_volumes = _compose(relative_path)["volumes"]
    assert anchor_volume in declared_volumes


@pytest.mark.parametrize("relative_path", COMPOSE_STACKS)
def test_compose_caddy_serves_the_jwks_listener_on_the_temporal_network(
    relative_path: str,
) -> None:
    services = _compose(relative_path)["services"]
    caddy = services["caddy"]
    temporal_networks = set(services["temporal"]["networks"])
    assert temporal_networks & set(caddy["networks"]), (
        "Temporal and Caddy must share a network for the JWKS listener"
    )
    # The internal listener is reachable inside the stack and never published.
    for port in caddy.get("ports", []):
        assert "8443" not in str(port)
