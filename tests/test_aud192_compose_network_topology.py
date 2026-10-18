"""Rendered network contract for the default and layered development stacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.test_s3_cutover_compose_contract import _rendered

ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = ROOT / "docker-compose.yml"

_STACKS = [
    pytest.param(
        (BASE_COMPOSE.name,),
        {"postgres": "15432", "valkey": "16379", "spicedb": "15052"},
        id="default",
    ),
    pytest.param(
        (BASE_COMPOSE.name, "docker-compose.infra.yml"),
        {"postgres": "54321", "valkey": "63791", "spicedb": "50052"},
        id="infra-port-override",
    ),
    pytest.param(
        (
            BASE_COMPOSE.name,
            "docker-compose.infra.yml",
            "docker-compose.go.yml",
            "docker-compose.ci-loadtest.yml",
        ),
        {"postgres": "54321", "valkey": "63791", "spicedb": "50052"},
        id="ci-development-stack",
    ),
    pytest.param(
        (BASE_COMPOSE.name, "docker-compose.observability.yml"),
        {"postgres": "15432", "valkey": "16379", "spicedb": "15052"},
        id="observability-overlay",
    ),
    pytest.param(
        (BASE_COMPOSE.name, "docker-compose.prod.yml"),
        {"postgres": "15432", "valkey": "16379", "spicedb": "15052"},
        id="prod-profile-overlay",
    ),
]

_SERVICE_NETWORKS = {
    "postgres": {"db_net", "published_ports"},
    "valkey": {"cache_net", "published_ports"},
    "spicedb": {"db_net", "service_net", "published_ports"},
    "temporal": {"db_net", "service_net", "published_ports"},
    "temporal-ui": {"service_net", "published_ports"},
}
_BACKEND_CONNECTIONS = {
    "postgres": "db_net",
    "valkey": "cache_net",
    "spicedb": "service_net",
    "temporal": "service_net",
}
_SERVICE_CLIENT_CONNECTIONS = (
    ("gateway", "valkey", "cache_net"),
    ("ws-hub", "valkey", "cache_net"),
    ("backend", "revocation-valkey", "revocation_net"),
    ("gateway", "revocation-valkey", "revocation_net"),
    ("ws-hub", "revocation-valkey", "revocation_net"),
    ("file-processor", "revocation-valkey", "revocation_net"),
    ("notifications-worker", "postgres", "db_net"),
    ("notifications-worker", "valkey", "cache_net"),
    ("notifications-worker", "spicedb", "service_net"),
    ("outbox-worker", "postgres", "db_net"),
    ("outbox-worker", "valkey", "cache_net"),
    ("temporal-ui", "temporal", "service_net"),
    ("temporal-namespace-init", "temporal", "service_net"),
)


def _network_names(service: dict[str, Any]) -> set[str]:
    configured = service.get("networks") or []
    return set(configured if isinstance(configured, list) else configured.keys())


@pytest.mark.parametrize(("files", "storage_host_ports"), _STACKS)
def test_default_and_layered_stacks_isolate_frontend_and_keep_local_access(
    tmp_path: Path,
    files: tuple[str, ...],
    storage_host_ports: dict[str, str],
) -> None:
    """Render real Compose merges without starting services."""
    model: dict[str, Any] = _rendered(
        tmp_path,
        "aud192-network-review",
        *files,
        profiles=("prod",) if "docker-compose.prod.yml" in files else (),
    )
    services = model["services"]
    networks = model["networks"]

    frontend_networks = _network_names(services["frontend"])
    assert frontend_networks == {"frontend_net"}
    assert networks["frontend_net"].get("internal") is True
    assert {"public", "service_net", "frontend_net"} <= _network_names(
        services["caddy"]
    )
    backend_networks = _network_names(services["backend"])
    assert "frontend_net" in backend_networks
    assert not networks["published_ports"].get("internal", False)
    for network_name in ("db_net", "cache_net", "service_net", "revocation_net"):
        assert networks[network_name].get("internal") is True
    assert _network_names(services["revocation-valkey"]) == {"revocation_net"}

    expected_host_ports = {
        **storage_host_ports,
        "temporal": "7233",
        "temporal-ui": "8233",
    }
    container_ports = {
        "postgres": 5432,
        "valkey": 6379,
        "spicedb": 50051,
        "temporal": 7233,
        "temporal-ui": 8080,
    }
    backend_networks = _network_names(services["backend"])

    for service_name, expected_networks in _SERVICE_NETWORKS.items():
        service = services[service_name]
        actual_networks = _network_names(service)
        assert actual_networks == expected_networks, service_name
        assert frontend_networks.isdisjoint(actual_networks), service_name
        assert "public" not in actual_networks
        assert "published_ports" in actual_networks

        bindings = {
            (
                binding.get("host_ip"),
                str(binding.get("published")),
                int(binding["target"]),
            )
            for binding in service["ports"]
        }
        assert bindings == {
            (
                "127.0.0.1",
                expected_host_ports[service_name],
                container_ports[service_name],
            )
        }, service_name

    for service_name, shared_network in _BACKEND_CONNECTIONS.items():
        assert shared_network in backend_networks
        assert shared_network in _network_names(services[service_name])

    for client_name, provider_name, shared_network in _SERVICE_CLIENT_CONNECTIONS:
        if client_name not in services:
            continue
        assert shared_network in _network_names(services[client_name])
        assert shared_network in _network_names(services[provider_name])

    if "docker-compose.ci-loadtest.yml" in files:
        # The CI overlay restates ws-hub's cache route. Compose merges this
        # sequence with the Go overlay, which supplies the revocation route.
        assert {"cache_net", "revocation_net"} <= _network_names(services["ws-hub"])
        assert {"cache_net", "revocation_net"} <= _network_names(services["gateway"])
        assert "cache_net" in _network_names(services["valkey"])
        assert "revocation_net" in _network_names(services["revocation-valkey"])

    temporal_networks = _network_names(services["temporal"])
    if "file-processor" in services:
        assert "service_net" in temporal_networks
        assert "service_net" in _network_names(services["file-processor"])

    # Keep SeaweedFS on its existing private application network.
    assert _network_names(services["minio"]) == {"service_net"}

    # Only the frontend, its SSR API upstream, and Caddy's frontend upstream
    # may share this internal bridge. In particular, published data services
    # must not gain an alternate path into the frontend segment.
    for service_name, service in services.items():
        if "frontend_net" in _network_names(service):
            assert service_name in {"frontend", "backend", "caddy"}


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(("docker-compose.full.yml",), id="full"),
        pytest.param(
            ("docker-compose.full.yml", "docker-compose.live.yml"),
            id="full-live-overlay",
        ),
    ],
)
def test_full_stack_frontend_ssr_is_confined_to_internal_frontend_network(
    tmp_path: Path, files: tuple[str, ...]
) -> None:
    model: dict[str, Any] = _rendered(tmp_path, "aud192-full-network-review", *files)
    services = model["services"]
    networks = model["networks"]

    frontend_networks = _network_names(services["frontend"])
    backend_networks = _network_names(services["backend"])
    caddy_networks = _network_names(services["caddy"])
    assert frontend_networks == {"frontend_net"}
    assert networks["frontend_net"].get("internal") is True
    assert "frontend_net" in backend_networks
    assert "frontend_net" in caddy_networks
    assert (
        services["frontend"]["environment"]["BACKEND_ORIGIN"] == "http://backend:8000"
    )
    frontend_ports = {
        (
            port.get("host_ip"),
            str(port.get("published")),
            int(port["target"]),
        )
        for port in services["frontend"]["ports"]
    }
    assert len(frontend_ports) == 1
    host_ip, _, target = next(iter(frontend_ports))
    assert host_ip == "127.0.0.1"
    assert target == 3000

    # Backend keeps its existing application/data and revocation routes, and
    # Caddy retains its public edge routes while joining the frontend bridge.
    assert {"internal", "public", "revocation_net", "frontend_net"} <= backend_networks
    assert {"public", "frontend_net"} <= caddy_networks
    for upstream in ("backend", "gateway", "ws-hub", "minio"):
        assert "public" in _network_names(services[upstream])

    # The new bridge is intentionally restricted to the SSR and edge trio.
    for service_name, service in services.items():
        if "frontend_net" in _network_names(service):
            assert service_name in {"frontend", "backend", "caddy"}

    # Full-stack stores keep their existing private/client networks and do not
    # join the frontend bridge. Host loopback mappings remain available.
    for service_name in ("postgres", "spicedb", "temporal"):
        service_networks = _network_names(services[service_name])
        assert "frontend_net" not in service_networks
        assert "public" not in service_networks
        assert "internal" in service_networks

    for client_name, provider_name in (
        ("backend", "postgres"),
        ("backend", "spicedb"),
        ("file-processor", "temporal"),
        ("temporal-namespace-init", "temporal"),
    ):
        assert "internal" in _network_names(services[client_name])
        assert "internal" in _network_names(services[provider_name])
