import re
from pathlib import Path

import pytest
import yaml

from tests.test_s3_cutover_compose_contract import (
    _production_secret_source_overrides,
    _rendered,
)

ROOT = Path(__file__).resolve().parents[1]
DOCKER_SOCKET_PATH = "/var/run/docker.sock"
DEFAULT_SOCKET_GROUP = "${DOCKER_SOCKET_GID:-0}"
DOCKER_PROXY_DOCKERFILE = (
    "infrastructure/observability/alloy/Dockerfile.docker-log-proxy"
)


def _compose(relative_path: str) -> dict:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    return yaml.safe_load(source.replace("!override", "").replace("!reset", ""))


def _socket_binding(volume: object) -> tuple[str | None, str | None, bool] | None:
    """Normalize Compose short/long bind syntax when it references the Docker socket."""
    if isinstance(volume, str):
        fields = volume.split(":")
        if len(fields) < 2:
            return None
        source, target = fields[0], fields[1]
        read_only = "ro" in fields[2:]
    elif isinstance(volume, dict):
        source = volume.get("source")
        target = volume.get("target", volume.get("destination"))
        bind = volume.get("bind")
        bind_read_only = (
            bind.get("read_only", False) if isinstance(bind, dict) else False
        )
        read_only = bool(volume.get("read_only", bind_read_only))
    else:
        return None

    if source != DOCKER_SOCKET_PATH and target != DOCKER_SOCKET_PATH:
        return None
    return source, target, read_only


def _network_names(service: dict) -> set[str]:
    networks = service.get("networks", [])
    if isinstance(networks, dict):
        return set(networks)
    return set(networks)


@pytest.mark.parametrize(
    "compose_path",
    ("docker-compose.full.yml", "docker-compose.observability.yml"),
)
def test_alloy_uses_an_isolated_read_only_docker_api_proxy(compose_path: str) -> None:
    compose = _compose(compose_path)
    services = compose["services"]
    alloy = services["alloy"]
    proxy = services["docker-log-proxy"]

    socket_mounts = [
        (service_name, binding)
        for service_name, service in services.items()
        for volume in service.get("volumes", [])
        if (binding := _socket_binding(volume)) is not None
    ]
    assert socket_mounts == [
        ("docker-log-proxy", (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, True))
    ]
    assert proxy["build"] == {
        "context": ".",
        "dockerfile": DOCKER_PROXY_DOCKERFILE,
    }
    assert _network_names(proxy) == {"alloy_docker_api"}
    assert "alloy_docker_api" in _network_names(alloy)
    api_members = {
        service_name
        for service_name, service in services.items()
        if "alloy_docker_api" in _network_names(service)
    }
    assert api_members == {"alloy", "docker-log-proxy"}
    assert compose["networks"]["alloy_docker_api"]["internal"] is True
    assert "ports" not in proxy
    assert proxy["expose"] == ["2375"]
    assert proxy["read_only"] is True
    assert proxy["user"] == "65532:65532"
    assert proxy["group_add"] == [DEFAULT_SOCKET_GROUP]
    assert proxy["cap_drop"] == ["ALL"]
    assert proxy.get("cap_add", []) == []
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert alloy["depends_on"]["docker-log-proxy"]["condition"] == "service_started"


@pytest.mark.parametrize(
    ("volume", "expected"),
    (
        (
            "/var/run/docker.sock:/var/run/docker.sock:ro",
            (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, True),
        ),
        (
            "/var/run/docker.sock:/var/run/docker.sock:rw",
            (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, False),
        ),
        (
            {
                "type": "bind",
                "source": DOCKER_SOCKET_PATH,
                "target": DOCKER_SOCKET_PATH,
                "read_only": True,
            },
            (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, True),
        ),
        (
            {
                "type": "bind",
                "source": DOCKER_SOCKET_PATH,
                "target": DOCKER_SOCKET_PATH,
                "read_only": False,
            },
            (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, False),
        ),
        ("alloy-data:/var/lib/alloy/data", None),
    ),
)
def test_socket_bind_normalizer_handles_short_and_long_compose_syntax(
    volume: object, expected: tuple[str | None, str | None, bool] | None
) -> None:
    assert _socket_binding(volume) == expected


def test_full_compose_separates_published_data_services_from_frontend() -> None:
    compose = _compose("docker-compose.full.yml")
    services = compose["services"]
    frontend_networks = _network_names(services["frontend"])

    assert frontend_networks == {"frontend_net"}
    assert compose["networks"]["frontend_net"]["internal"] is True
    published_members = {
        service_name
        for service_name, service in services.items()
        if "published_ports" in _network_names(service)
    }
    assert published_members == {"postgres", "temporal"}
    for service_name in ("postgres", "temporal"):
        service = services[service_name]
        assert _network_names(service) == {"internal", "published_ports"}
        assert frontend_networks.isdisjoint(_network_names(service))
        assert "public" not in _network_names(service)
    assert not (compose["networks"].get("published_ports") or {}).get("internal", False)

    assert services["postgres"]["ports"] == ["127.0.0.1:15433:5432"]
    assert services["temporal"]["ports"] == [
        "127.0.0.1:7233:7233",
        "127.0.0.1:7243:7243",
    ]

    postgres_clients = {
        "backend",
        "notifications-worker",
        "outbox-worker",
        "migrations",
        "postgres-databases-init",
        "spicedb-migrate",
        "spicedb",
        "temporal",
        "temporal-admin-tools",
    }
    temporal_clients = {
        "file-processor",
        "temporal-admin-tools",
        "temporal-namespace-init",
    }
    for client in postgres_clients | temporal_clients:
        assert "internal" in _network_names(services[client]), client


def test_proxy_image_is_nonroot_and_has_a_local_healthcheck() -> None:
    dockerfile = (
        ROOT / "infrastructure/observability/alloy/Dockerfile.docker-log-proxy"
    ).read_text(encoding="utf-8")

    assert "USER 65532:65532" in dockerfile
    healthcheck = (
        "HEALTHCHECK --interval=30s --timeout=3s --start-period=5s "
        '--retries=3 CMD ["/docker-log-proxy", "--healthcheck"]'
    )
    assert healthcheck in dockerfile
    assert "USER 0:0" not in dockerfile


def test_alloy_docker_components_use_the_proxy_endpoint() -> None:
    config = (ROOT / "infrastructure/observability/alloy/config.alloy").read_text(
        encoding="utf-8"
    )

    assert config.count('"tcp://docker-log-proxy:2375"') == 2
    assert "/var/run/docker.sock" not in config
    assert 'discovery.docker "containers"' in config
    assert 'loki.source.docker "containers"' in config


@pytest.mark.parametrize(
    "compose_files",
    [
        pytest.param(("docker-compose.full.yml",), id="full"),
        pytest.param(
            ("docker-compose.full.yml", "docker-compose.live.yml"), id="full-live"
        ),
        pytest.param(
            ("docker-compose.yml", "docker-compose.observability.yml"), id="base-obs"
        ),
        pytest.param(
            (
                "docker-compose.yml",
                "docker-compose.observability.yml",
                "docker-compose.prod.yml",
            ),
            id="base-obs-prod",
        ),
    ],
)
def test_rendered_stack_keeps_docker_socket_behind_the_proxy(
    tmp_path: Path, compose_files: tuple[str, ...]
) -> None:
    production = "docker-compose.prod.yml" in compose_files
    model = _rendered(
        tmp_path,
        "aud193-socket-contract",
        *compose_files,
        profiles=("prod",) if production else (),
        environment_overrides=(
            _production_secret_source_overrides(tmp_path) if production else None
        ),
    )
    services = model["services"]
    proxy = services["docker-log-proxy"]
    socket_mounts = [
        (name, binding)
        for name, service in services.items()
        for volume in service.get("volumes", [])
        if (binding := _socket_binding(volume)) is not None
    ]
    assert socket_mounts == [
        ("docker-log-proxy", (DOCKER_SOCKET_PATH, DOCKER_SOCKET_PATH, True))
    ]
    assert model["networks"]["alloy_docker_api"].get("internal") is True
    assert {
        name
        for name, service in services.items()
        if "alloy_docker_api" in _network_names(service)
    } == {"alloy", "docker-log-proxy"}
    assert _network_names(proxy) == {"alloy_docker_api"}
    assert not proxy.get("ports")
    assert proxy["expose"] == ["2375"]
    assert proxy["build"]["dockerfile"] == DOCKER_PROXY_DOCKERFILE
    assert proxy["user"] == "65532:65532"
    assert len(proxy["group_add"]) == 1 and proxy["group_add"][0].isdigit()
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    assert not proxy.get("cap_add")
    assert "no-new-privileges:true" in proxy["security_opt"]


def test_alloy_source_forwards_to_the_loki_write_endpoint() -> None:
    config = (ROOT / "infrastructure/observability/alloy/config.alloy").read_text(
        encoding="utf-8"
    )
    source = re.search(
        r'^\s*loki\.source\.docker\s+"containers"\s*\{(?P<body>.*?)^\s*\}',
        config,
        re.MULTILINE | re.DOTALL,
    )
    assert source is not None
    assert re.search(
        r"^\s*forward_to\s*=\s*\[\s*loki\.write\.local\.receiver\s*\]\s*$",
        source.group("body"),
        re.MULTILINE,
    )
    sink = re.search(
        r'^\s*loki\.write\s+"local"\s*\{(?P<body>.*?)^\s*\}',
        config,
        re.MULTILINE | re.DOTALL,
    )
    assert sink is not None
    assert re.search(
        r'^\s*url\s*=\s*"http://loki:3100/loki/api/v1/push"\s*$',
        sink.group("body"),
        re.MULTILINE,
    )
