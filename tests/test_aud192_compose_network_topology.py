"""Rendered network contract for the default and layered development stacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.test_s3_cutover_compose_contract import (
    _compose,
    _production_secret_source_overrides,
    _rendered,
)

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
        (BASE_COMPOSE.name, "docker-compose.go.yml"),
        {"postgres": "15432", "valkey": "16379", "spicedb": "15052"},
        id="go-overlay",
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
    pytest.param(
        (BASE_COMPOSE.name, "docker-compose.go.yml", "docker-compose.prod.yml"),
        {"postgres": "15432", "valkey": "16379", "spicedb": "15052"},
        id="documented-prod-stack",
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


def _assert_frontend_segment(model: dict[str, Any]) -> None:
    """Check the frontend bridge, including shared network namespaces."""
    services = model["services"]
    frontend = services["frontend"]
    assert _network_names(frontend) == {"frontend_net"}, "frontend networks"
    assert model["networks"]["frontend_net"].get("internal") is True, (
        "frontend network must be internal"
    )
    assert frontend.get("network_mode") is None, "frontend network mode"
    for bypass in ("links", "external_links", "extra_hosts"):
        assert not frontend.get(bypass), f"frontend {bypass}"
    assert frontend["environment"]["BACKEND_ORIGIN"] == "http://backend:8000", (
        "frontend SSR upstream"
    )

    members = {
        name
        for name, service in services.items()
        if "frontend_net" in _network_names(service)
    }
    assert members == {"frontend", "backend", "caddy"}, "frontend bridge members"

    # A service sharing the namespace of any bridge member reaches the same
    # bridge without declaring its own networks. Follow service: chains, and
    # reject opaque container: namespace targets that cannot be resolved here.
    for name in services:
        current = name
        seen = {current}
        while mode := services[current].get("network_mode"):
            assert not mode.startswith("container:"), (
                f"opaque network namespace: {name}"
            )
            if not mode.startswith("service:"):
                break
            target = mode.removeprefix("service:")
            assert target in services, f"unknown network namespace: {target}"
            assert target not in {"frontend", "backend", "caddy"}, (
                f"frontend bridge namespace shared by {name}"
            )
            assert target not in seen, f"network namespace cycle: {name}"
            seen.add(target)
            current = target


@pytest.mark.parametrize("filename", ("docker-compose.yml", "docker-compose.full.yml"))
def test_frontend_segment_in_source_models(filename: str) -> None:
    # This is a source-level check; the rendered tests below exercise Compose
    # merge semantics separately and neither check proves live connectivity.
    _assert_frontend_segment(_compose(filename))


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("frontend_public", "frontend networks"),
        ("external_bridge", "frontend network must be internal"),
        ("store_on_frontend_bridge", "frontend bridge members"),
        ("backend_namespace_shared", "frontend bridge namespace shared"),
        ("backend_namespace_chain", "frontend bridge namespace shared"),
        ("unknown_namespace", "unknown network namespace"),
        ("namespace_cycle", "network namespace cycle"),
        ("opaque_namespace", "opaque network namespace"),
        ("host_gateway", "frontend extra_hosts"),
        ("frontend_link", "frontend links"),
        ("external_link", "frontend external_links"),
        ("host_network", "frontend network mode"),
        ("missing_backend_bridge", "frontend bridge members"),
        ("wrong_ssr_upstream", "frontend SSR upstream"),
    ],
)
def test_frontend_segment_rejects_unsafe_models(change: str, reason: str) -> None:
    model = _compose(BASE_COMPOSE.name)
    services = model["services"]
    if change == "frontend_public":
        services["frontend"]["networks"].append("public")
    elif change == "external_bridge":
        model["networks"]["frontend_net"]["internal"] = False
    elif change == "store_on_frontend_bridge":
        services["postgres"]["networks"].append("frontend_net")
    elif change == "backend_namespace_shared":
        services["postgres"].pop("networks")
        services["postgres"]["network_mode"] = "service:backend"
    elif change == "backend_namespace_chain":
        services["postgres"].pop("networks")
        services["postgres"]["network_mode"] = "service:postgres-databases-init"
        services["postgres-databases-init"].pop("networks")
        services["postgres-databases-init"]["network_mode"] = "service:backend"
    elif change == "unknown_namespace":
        services["postgres"].pop("networks")
        services["postgres"]["network_mode"] = "service:missing"
    elif change == "namespace_cycle":
        services["postgres"].pop("networks")
        services["postgres"]["network_mode"] = "service:postgres-databases-init"
        services["postgres-databases-init"].pop("networks")
        services["postgres-databases-init"]["network_mode"] = "service:postgres"
    elif change == "opaque_namespace":
        services["postgres"].pop("networks")
        services["postgres"]["network_mode"] = "container:opaque"
    elif change == "host_gateway":
        services["frontend"]["extra_hosts"] = ["host.docker.internal:host-gateway"]
    elif change == "frontend_link":
        services["frontend"]["links"] = ["postgres"]
    elif change == "external_link":
        services["frontend"]["external_links"] = ["postgres"]
    elif change == "host_network":
        services["frontend"]["network_mode"] = "host"
    elif change == "missing_backend_bridge":
        services["backend"]["networks"].remove("frontend_net")
    elif change == "wrong_ssr_upstream":
        services["frontend"]["environment"]["BACKEND_ORIGIN"] = "http://other:8000"

    with pytest.raises(AssertionError, match=reason):
        _assert_frontend_segment(model)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        pytest.param(None, "127.0.0.1,::1", id="unset"),
        pytest.param("", "127.0.0.1,::1", id="empty"),
        pytest.param("192.0.2.10/32", "192.0.2.10/32", id="explicit-peer"),
    ],
)
def test_go_overlay_renders_ws_hub_trusted_proxy_setting(
    tmp_path: Path, setting: str | None, expected: str
) -> None:
    overrides = {} if setting is None else {"WS_HUB_TRUSTED_PROXIES": setting}
    unset = ("WS_HUB_TRUSTED_PROXIES",) if setting is None else ()
    model = _rendered(
        tmp_path,
        "aud167-ws-proxy-review",
        BASE_COMPOSE.name,
        "docker-compose.go.yml",
        environment_overrides=overrides,
        unset_environment=unset,
    )
    assert model["services"]["ws-hub"]["environment"]["TRUSTED_PROXIES"] == expected


@pytest.mark.parametrize(("files", "storage_host_ports"), _STACKS)
def test_default_and_layered_stacks_isolate_frontend_and_keep_local_access(
    tmp_path: Path,
    files: tuple[str, ...],
    storage_host_ports: dict[str, str],
) -> None:
    """Render real Compose merges without starting services."""
    environment_overrides = (
        _production_secret_source_overrides(tmp_path)
        if "docker-compose.prod.yml" in files
        else None
    )
    model: dict[str, Any] = _rendered(
        tmp_path,
        "aud192-network-review",
        *files,
        profiles=("prod",) if "docker-compose.prod.yml" in files else (),
        environment_overrides=environment_overrides,
    )
    services = model["services"]
    networks = model["networks"]

    _assert_frontend_segment(model)
    frontend_networks = _network_names(services["frontend"])
    assert {"public", "service_net", "frontend_net"} <= _network_names(
        services["caddy"]
    )
    backend_networks = _network_names(services["backend"])
    assert "frontend_net" in backend_networks
    assert not networks["published_ports"].get("internal", False)
    for network_name in ("db_net", "cache_net", "service_net", "revocation_net"):
        assert networks[network_name].get("internal") is True
    assert _network_names(services["revocation-valkey"]) == {"revocation_net"}

    frontend_ports = {
        (binding.get("host_ip"), str(binding.get("published")), int(binding["target"]))
        for binding in services["frontend"]["ports"]
    }
    assert frontend_ports == {("127.0.0.1", "8081", 3000)}

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

    for client_name, provider_name in (
        ("caddy", "backend"),
        ("caddy", "minio"),
        ("caddy", "imgproxy"),
        ("backend", "minio"),
    ):
        assert "service_net" in _network_names(services[client_name])
        assert "service_net" in _network_names(services[provider_name])

    if "docker-compose.go.yml" in files:
        assert {"gateway", "ws-hub", "file-processor"} <= services.keys()
        for client_name, provider_name, shared_network in (
            ("caddy", "gateway", "public"),
            ("caddy", "ws-hub", "public"),
            ("gateway", "backend", "public"),
            ("ws-hub", "backend", "public"),
            ("file-processor", "minio", "service_net"),
            ("file-processor", "nats", "event_net"),
        ):
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
    storage_ports = {
        (binding.get("host_ip"), str(binding.get("published")), int(binding["target"]))
        for binding in services["minio"].get("ports", [])
    }
    assert storage_ports == (
        {("127.0.0.1", "9000", 9000)} if "docker-compose.infra.yml" in files else set()
    )


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

    _assert_frontend_segment(model)
    backend_networks = _network_names(services["backend"])
    caddy_networks = _network_names(services["caddy"])
    assert "frontend_net" in backend_networks
    assert "frontend_net" in caddy_networks
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

    # Full-stack stores keep their existing private/client networks and do not
    # join the frontend bridge. Host loopback mappings remain available.
    for service_name in ("postgres", "redis", "spicedb", "temporal"):
        service_networks = _network_names(services[service_name])
        assert "frontend_net" not in service_networks
        assert "public" not in service_networks
        assert "internal" in service_networks

    assert _network_names(services["revocation-redis"]) == {"revocation_net"}
    assert "frontend_net" not in _network_names(services["minio"])

    for service_name, targets in (
        ("postgres", {5432}),
        ("temporal", {7233, 7243}),
        ("minio", {9000} if "docker-compose.live.yml" in files else set()),
        ("redis", set()),
        ("revocation-redis", set()),
        ("spicedb", set()),
    ):
        ports = services[service_name].get("ports", [])
        assert len(ports) == len(targets)
        assert {int(port["target"]) for port in ports} == targets
        assert all(
            port.get("host_ip") == "127.0.0.1" and port.get("published")
            for port in ports
        )

    for client_name, provider_name in (
        ("backend", "postgres"),
        ("backend", "redis"),
        ("backend", "spicedb"),
        ("backend", "minio"),
        ("gateway", "redis"),
        ("ws-hub", "redis"),
        ("file-processor", "minio"),
        ("file-processor", "temporal"),
        ("temporal-namespace-init", "temporal"),
    ):
        assert "internal" in _network_names(services[client_name])
        assert "internal" in _network_names(services[provider_name])
