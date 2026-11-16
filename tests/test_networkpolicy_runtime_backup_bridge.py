"""Offline contracts for the disposable backup bridge fixture."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import io
import ipaddress
import json
import os
import runpy
import shutil
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "k8s"))

NETWORK_ID = "a" * 64
NODE_ID = "b" * 64
SERVER_ID = "c" * 64
PROXY_ID = "f" * 64
RUN_TOKEN = "d" * 12
SUBNET = "198.18.42.0/24"
OWNER_LABEL = "org.university-ecosystem.netpol-owner"
ENDPOINTS = {NODE_ID: "198.18.42.2", SERVER_ID: "198.18.42.11"}


@pytest.fixture
def proof():
    return importlib.import_module("networkpolicy_runtime_backup_bridge")


@pytest.fixture
def bridge() -> dict:
    return {
        "Id": NETWORK_ID,
        "Name": "kind",
        "Driver": "bridge",
        "Scope": "local",
        "Internal": False,
        "EnableIPv6": False,
        "Labels": {OWNER_LABEL: RUN_TOKEN},
        "IPAM": {
            "Driver": "default",
            "Config": [{"Subnet": SUBNET, "Gateway": "198.18.42.1"}],
        },
        "Containers": {
            NODE_ID: {"IPv4Address": "198.18.42.2/24", "IPv6Address": ""},
            SERVER_ID: {"IPv4Address": "198.18.42.11/24", "IPv6Address": ""},
        },
    }


def validate(proof, bridge, *, endpoints=ENDPOINTS, **overrides):
    kwargs = {
        "expected_id": NETWORK_ID,
        "owner_token": RUN_TOKEN,
        "expected_subnet": SUBNET,
        "expected_endpoints": endpoints,
    }
    kwargs.update(overrides)
    return proof.validate_owned_kind_bridge(bridge, **kwargs)


def test_backup_bridge_helper_is_available() -> None:
    assert importlib.util.find_spec("networkpolicy_runtime_backup_bridge") is not None


@pytest.mark.parametrize(
    ("snapshot", "allowed"),
    [
        ({"Name": "host", "Driver": "host", "IPAM": {"Config": None}}, True),
        ({"Name": "none", "Driver": "null", "IPAM": {"Config": None}}, True),
        ({"Name": "other", "Driver": "bridge", "IPAM": {"Config": None}}, False),
        ({"Name": "host", "Driver": "bridge", "IPAM": {"Config": None}}, False),
        ({"Name": "kind", "Driver": "bridge", "IPAM": {"Config": []}}, False),
        (
            {
                "Name": "other",
                "Driver": "bridge",
                "IPAM": {"Config": [{"Subnet": "198.18.0.0/15"}]},
            },
            False,
        ),
    ],
)
def test_network_preflight_handles_builtin_nulls_and_conflicts(
    proof, snapshot, allowed
):
    snapshot["Id"] = NETWORK_ID
    if allowed:
        assert proof.validate_network_preflight([snapshot], [NETWORK_ID]) is None
    else:
        with pytest.raises(ValueError):
            proof.validate_network_preflight([snapshot], [NETWORK_ID])


def test_network_recovery_requires_original_identity(proof):
    snapshots = [{"Id": NETWORK_ID, "Name": "kind"}]
    assert proof.recover_bridge_identity(snapshots, [NETWORK_ID], "") == NETWORK_ID
    assert (
        proof.recover_bridge_identity(snapshots, [NETWORK_ID], NETWORK_ID) == NETWORK_ID
    )
    with pytest.raises(ValueError):
        proof.recover_bridge_identity(snapshots, [NETWORK_ID], "e" * 64)
    with pytest.raises(ValueError):
        proof.recover_bridge_identity(snapshots, [NETWORK_ID, NETWORK_ID], NETWORK_ID)


def test_host_route_validation_rejects_fixture_overlaps(proof):
    proof.validate_host_routes([{"dst": "default"}, {"dst": "172.17.0.0/16"}])
    with pytest.raises(ValueError):
        proof.validate_host_routes([{"dst": "198.18.42.10"}])


def test_container_recovery_never_accepts_replaced_or_renamed_identity(proof):
    listing = f"{SERVER_ID} server\n{NODE_ID} node\n"
    assert proof.recover_container_identity(listing, "", "server") == SERVER_ID
    assert proof.recover_container_identity(listing, SERVER_ID, "server") == SERVER_ID
    with pytest.raises(ValueError):
        proof.recover_container_identity(listing, NODE_ID, "server")
    with pytest.raises(ValueError):
        proof.recover_container_identity(f"{SERVER_ID} renamed\n", SERVER_ID, "server")


def test_compose_image_selection_requires_the_immutable_minio_service(proof, tmp_path):
    compose = tmp_path / "docker-compose.yml"
    pinned = "ghcr.io/chrislusf/seaweedfs:4.48@sha256:" + "a" * 64
    compose.write_text(f"services:\n  minio:\n    image: {pinned}\n", encoding="utf-8")
    assert proof.read_compose_image(compose) == pinned
    compose.write_text("services:\n  minio:\n    image: unpinned\n", encoding="utf-8")
    with pytest.raises(ValueError):
        proof.read_compose_image(compose)


def test_container_validation_rejects_a_replaced_bridge(proof):
    snapshot = [
        {
            "Id": SERVER_ID,
            "Name": "/server",
            "Config": {"Image": "fixture-image", "Labels": {OWNER_LABEL: RUN_TOKEN}},
            "HostConfig": {
                "PortBindings": {},
                "PublishAllPorts": False,
                "NetworkMode": NETWORK_ID,
            },
            "State": {"Running": True},
            "NetworkSettings": {
                "Networks": {
                    "kind": {"NetworkID": NETWORK_ID, "IPAddress": "198.18.42.11"}
                }
            },
        }
    ]
    kwargs = {
        "role": "server",
        "identity": SERVER_ID,
        "name": "server",
        "bridge": NETWORK_ID,
        "owner": RUN_TOKEN,
        "cluster": "cluster",
        "image": "fixture-image",
    }
    assert proof.validate_container_inspection(snapshot, **kwargs) == "198.18.42.11"
    snapshot[0]["NetworkSettings"]["Networks"]["kind"]["NetworkID"] = "e" * 64
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


def test_bridge_cli_rejects_malformed_input_without_echoing_it(
    proof, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "stdin", io.StringIO("sensitive-invalid-payload"))
    assert proof.main(["preflight-routes"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "sensitive-invalid-payload" not in captured.err


@pytest.mark.parametrize(
    ("objects", "identities"),
    [
        ({}, []),
        ([], [NETWORK_ID]),
        ([{}], ["short"]),
        ([None], [NETWORK_ID]),
        ([{"Id": "e" * 64, "Name": "x"}], [NETWORK_ID]),
        ([{"Id": NETWORK_ID, "Name": None}], [NETWORK_ID]),
        ([{"Id": NETWORK_ID, "Name": "x"}] * 2, [NETWORK_ID, NODE_ID]),
    ],
)
def test_network_inventory_rejects_incomplete_or_ambiguous_snapshots(
    proof, objects, identities
):
    with pytest.raises(ValueError):
        proof.validate_network_preflight(objects, identities)


def test_network_inventory_accepts_disjoint_v4_and_v6_and_recovers_absence(proof):
    objects = [
        {
            "Id": NETWORK_ID,
            "Name": "custom",
            "IPAM": {
                "Config": [
                    {"Subnet": "172.17.0.0/16"},
                    {"Subnet": "fd00::/64"},
                ]
            },
        }
    ]
    proof.validate_network_preflight(objects, [NETWORK_ID])
    assert proof.recover_bridge_identity(objects, [NETWORK_ID], "") == ""
    with pytest.raises(ValueError):
        proof.recover_bridge_identity(objects, [NETWORK_ID], NETWORK_ID)


@pytest.mark.parametrize(
    "routes", [None, [{}], [{"dst": "bad"}], [{"dst": "fd00::/64"}]]
)
def test_host_route_validation_fails_closed_on_malformed_input(proof, routes):
    with pytest.raises(ValueError):
        proof.validate_host_routes(routes)


def container_snapshot(role: str) -> tuple[list[dict], dict]:
    labels = (
        {OWNER_LABEL: RUN_TOKEN}
        if role in ("server", "proxy")
        else {
            "io.x-k8s.kind.cluster": "cluster",
            "io.x-k8s.kind.role": "control-plane",
        }
    )
    identity = {"server": SERVER_ID, "proxy": PROXY_ID, "node": NODE_ID}[role]
    address = {
        "server": "198.18.42.11",
        "proxy": "198.18.42.10",
        "node": "198.18.42.2",
    }[role]
    snapshot = [
        {
            "Id": identity,
            "Name": "/fixture",
            "Config": {"Image": "image", "Labels": labels},
            "HostConfig": {
                "NetworkMode": NETWORK_ID,
                "PortBindings": {},
                "PublishAllPorts": False,
            },
            "State": {"Running": True},
            "NetworkSettings": {
                "Networks": {"kind": {"NetworkID": NETWORK_ID, "IPAddress": address}}
            },
        }
    ]
    kwargs = {
        "role": role,
        "identity": identity,
        "name": "fixture",
        "bridge": NETWORK_ID,
        "owner": RUN_TOKEN,
        "cluster": "cluster",
        "image": "image",
    }
    return snapshot, kwargs


@pytest.mark.parametrize(
    "change",
    [
        lambda obj: obj.update(Id="e" * 64),
        lambda obj: obj.update(Name="/replacement"),
        lambda obj: obj["Config"].update(Labels=None),
        lambda obj: obj["Config"].update(Image="other"),
        lambda obj: obj["HostConfig"].update(NetworkMode="host"),
        lambda obj: obj["HostConfig"].update(PublishAllPorts=True),
        lambda obj: obj["HostConfig"].update(PortBindings={"443/tcp": [{}]}),
        lambda obj: obj["State"].update(Running="yes"),
        lambda obj: obj["NetworkSettings"].update(Networks=None),
        lambda obj: obj["NetworkSettings"]["Networks"].update(ambient={}),
        lambda obj: obj["NetworkSettings"]["Networks"].update(kind=None),
        lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
            NetworkID="e" * 64
        ),
        lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
            IPAddress="198.18.42.1"
        ),
        lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
            IPAddress="198.18.42.10"
        ),
        lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
            IPAddress="fd00::1"
        ),
    ],
)
def test_container_validation_rejects_changed_ownership_or_endpoints(proof, change):
    snapshot, kwargs = container_snapshot("server")
    change(snapshot[0])
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


def test_container_validation_supports_kind_and_stopped_partial_startup(proof):
    node, node_kwargs = container_snapshot("node")
    assert proof.validate_container_inspection(node, **node_kwargs) == "198.18.42.2"
    node[0]["Config"]["Labels"]["io.x-k8s.kind.role"] = "worker"
    with pytest.raises(ValueError):
        proof.validate_container_inspection(node, **node_kwargs)
    node[0]["Config"]["Labels"]["io.x-k8s.kind.role"] = "control-plane"
    node[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"] = "198.18.42.10"
    with pytest.raises(ValueError):
        proof.validate_container_inspection(node, **node_kwargs)
    server, kwargs = container_snapshot("server")
    server[0]["NetworkSettings"]["Networks"] = {}
    with pytest.raises(ValueError):
        proof.validate_container_inspection(server, **kwargs)
    server[0]["State"]["Running"] = False
    assert proof.validate_container_inspection(server, **kwargs) == "-"
    server[0]["NetworkSettings"]["Networks"] = {"kind": {"NetworkID": "e" * 64}}
    with pytest.raises(ValueError):
        proof.validate_container_inspection(server, **kwargs)
    for objects, override in [
        ([], {}),
        (server, {"identity": "short"}),
        (server, {"role": "unknown"}),
    ]:
        with pytest.raises(ValueError):
            proof.validate_container_inspection(objects, **(kwargs | override))


def test_container_validation_binds_the_distinct_server_and_proxy_roles(proof):
    server, server_kwargs = container_snapshot("server")
    server[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"] = "198.18.42.11"
    assert (
        proof.validate_container_inspection(server, **server_kwargs) == "198.18.42.11"
    )

    proxy = copy.deepcopy(server)
    proxy[0]["Id"] = PROXY_ID
    proxy[0]["Config"]["Image"] = "caddy-image"
    proxy[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"] = "198.18.42.10"
    proxy_kwargs = server_kwargs | {
        "role": "proxy",
        "identity": PROXY_ID,
        "image": "caddy-image",
    }
    assert proof.validate_container_inspection(proxy, **proxy_kwargs) == "198.18.42.10"
    proxy[0]["HostConfig"]["PortBindings"] = {"443/tcp": [{}]}
    with pytest.raises(ValueError):
        proof.validate_container_inspection(proxy, **proxy_kwargs)


@pytest.mark.parametrize("role", ["server", "proxy"])
@pytest.mark.parametrize(
    "ports",
    [
        False,
        [],
        {"443/tcp": False},
        {"443/tcp": 0},
        {"443/tcp": ""},
        {"443/tcp": []},
        {"not-a-port": None},
        {"70000/tcp": None},
        {"80/unknown": None},
        {80: None},
    ],
)
def test_fixture_container_rejects_malformed_published_port_information(
    proof, role, ports
):
    snapshot, kwargs = container_snapshot(role)
    snapshot[0]["NetworkSettings"]["Ports"] = ports
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


@pytest.mark.parametrize("role", ["server", "proxy"])
def test_fixture_container_allows_only_unbound_network_ports(proof, role):
    snapshot, kwargs = container_snapshot(role)
    snapshot[0]["NetworkSettings"]["Ports"] = {"443/tcp": None}
    assert proof.validate_container_inspection(snapshot, **kwargs) in (
        "198.18.42.10",
        "198.18.42.11",
    )
    snapshot[0]["NetworkSettings"]["Ports"]["443/tcp"] = [{"HostIp": "127.0.0.1"}]
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


@pytest.mark.parametrize("address", [None, False, 0, []])
def test_partial_container_requires_a_well_formed_missing_address(proof, address):
    snapshot, kwargs = container_snapshot("server")
    snapshot[0]["State"]["Running"] = False
    snapshot[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"] = address
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


def test_container_inspection_rejects_malformed_network_settings(proof):
    snapshot, kwargs = container_snapshot("proxy")
    snapshot[0]["NetworkSettings"] = []
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


@pytest.mark.parametrize("role", ["server", "proxy"])
@pytest.mark.parametrize(
    "change",
    [
        lambda item: item["Config"]["Labels"].clear(),
        lambda item: item["Config"].update(Image="wrong-image"),
        lambda item: item["HostConfig"].update(PublishAllPorts=True),
        lambda item: item["HostConfig"].update(PortBindings={"443/tcp": [{}]}),
        lambda item: item["NetworkSettings"]["Networks"]["kind"].update(
            NetworkID="e" * 64
        ),
        lambda item: item["NetworkSettings"]["Networks"]["kind"].update(
            IPAddress="198.18.42.12"
        ),
    ],
)
def test_each_fixture_role_requires_owned_image_address_and_no_publication(
    proof, role, change
):
    snapshot, kwargs = container_snapshot(role)
    change(snapshot[0])
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)


@pytest.mark.parametrize("role", ["server", "proxy", "node"])
def test_stopped_unattached_container_is_allowed_for_safe_cleanup(proof, role):
    snapshot, kwargs = container_snapshot(role)
    snapshot[0]["NetworkSettings"]["Networks"] = {}
    with pytest.raises(ValueError):
        proof.validate_container_inspection(snapshot, **kwargs)
    snapshot[0]["State"]["Running"] = False
    assert proof.validate_container_inspection(snapshot, **kwargs) == "-"


def test_node_inspection_rejects_wrong_image_and_both_fixture_ips(proof):
    node, kwargs = container_snapshot("node")
    node[0]["Config"]["Image"] = "replaced"
    with pytest.raises(ValueError):
        proof.validate_container_inspection(node, **kwargs)
    node[0]["Config"]["Image"] = kwargs["image"]
    for address in ("198.18.42.10", "198.18.42.11"):
        node[0]["NetworkSettings"]["Networks"]["kind"]["IPAddress"] = address
        with pytest.raises(ValueError):
            proof.validate_container_inspection(node, **kwargs)


def test_node_retains_existing_loopback_api_binding(proof):
    node, kwargs = container_snapshot("node")
    node[0]["HostConfig"]["PortBindings"] = {
        "6443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "12345"}]
    }
    node[0]["NetworkSettings"]["Ports"] = node[0]["HostConfig"]["PortBindings"]
    assert proof.validate_container_inspection(node, **kwargs) == "198.18.42.2"


def test_bridge_accepts_three_exact_recorded_endpoints(proof, bridge):
    bridge["Containers"][SERVER_ID]["IPv4Address"] = "198.18.42.11/24"
    bridge["Containers"][PROXY_ID] = {
        "IPv4Address": "198.18.42.10/24",
        "IPv6Address": "",
    }
    endpoints = {
        NODE_ID: "198.18.42.2",
        SERVER_ID: "198.18.42.11",
        PROXY_ID: "198.18.42.10",
    }
    assert validate(proof, bridge, endpoints=endpoints)["endpoints"] == endpoints


def test_caddy_image_comes_from_the_last_pinned_runtime_stage(proof, tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    image = "caddy:2.11.7-alpine@sha256:" + "a" * 64
    dockerfile.write_text(f"FROM golang:1 AS builder\nFROM {image}\n", encoding="utf-8")
    assert proof.read_caddy_image(dockerfile) == image


def test_caddy_image_requires_lowercase_exact_image_and_digest(proof, tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    for image in (
        "CADDY:2.11.7-alpine@sha256:" + "a" * 64,
        "caddy:2.11.7-alpine@sha256:" + "A" * 64,
    ):
        dockerfile.write_text(f"FROM {image}\n", encoding="utf-8")
        with pytest.raises(ValueError):
            proof.read_caddy_image(dockerfile)


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "# FROM caddy:latest\n",
        "FROM caddy:2.11.7-alpine\n",
        "FROM caddy:2.11.7-alpine@sha256:short\n",
        "FROM caddy:2.11.7-alpine@sha256:" + "a" * 64 + "\nFROM busybox:1\n",
    ],
)
def test_caddy_image_rejects_missing_unpinned_or_non_runtime_stages(
    proof, tmp_path, contents
):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        proof.read_caddy_image(dockerfile)


def test_caddy_image_reads_archived_runtime_stage_and_rejects_unreadable_files(
    proof, tmp_path
):
    dockerfile = ROOT / "services" / "caddy" / "Dockerfile"
    runtime = proof.read_caddy_image(dockerfile)
    assert runtime.startswith("caddy:2.11.7-alpine@sha256:")
    assert f"FROM {runtime}" in dockerfile.read_text(encoding="utf-8").splitlines()
    with pytest.raises(ValueError):
        proof.read_caddy_image(tmp_path / "missing")
    invalid = tmp_path / "invalid"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError):
        proof.read_caddy_image(invalid)


def test_backup_bucket_is_taken_from_archived_chart_values(proof, tmp_path):
    values = tmp_path / "values.yaml"
    values.write_text("backup:\n  minioBucket: backups\n", encoding="utf-8")
    assert proof.read_backup_bucket(values) == "backups"


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "backup: []\n",
        "backup: {}\n",
        "backup:\n  minioBucket: 123\n",
        "backup:\n  minioBucket: [backups]\n",
        "backup:\n  minioBucket: uppercaseBucket\n",
        "backup:\n  minioBucket: invalid_bucket\n",
        "backup:\n  minioBucket: ab\n",
        "backup:\n  minioBucket: " + "a" * 64 + "\n",
        "backup:\n  minioBucket: first\n  minioBucket: second\n",
        "backup: {minioBucket: first}\nbackup: {minioBucket: second}\n",
        "backup: [\n",
        "!!int backup: {minioBucket: backups}\n",
        "backup: {!!int minioBucket: backups}\n",
    ],
)
def test_backup_bucket_rejects_malformed_or_ambiguous_archived_values(
    proof, tmp_path, contents
):
    values = tmp_path / "values.yaml"
    values.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        proof.read_backup_bucket(values)


def test_backup_bucket_reads_repository_chart_and_rejects_unreadable_files(
    proof, tmp_path
):
    assert (
        proof.read_backup_bucket(ROOT / "charts/university-ecosystem/values.yaml")
        == "backups"
    )
    with pytest.raises(ValueError):
        proof.read_backup_bucket(tmp_path / "missing")
    invalid = tmp_path / "invalid"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError):
        proof.read_backup_bucket(invalid)


def test_container_inventory_rejects_malformed_or_duplicate_lines(proof):
    assert proof.recover_container_identity("\n", "", "fixture") == ""
    with pytest.raises(ValueError):
        proof.recover_container_identity("short fixture\n", "", "fixture")
    with pytest.raises(ValueError):
        proof.recover_container_identity(
            f"{SERVER_ID} fixture\n{NODE_ID} fixture\n", "", "fixture"
        )


def test_cli_routes_each_supported_operation_without_daemon_access(
    proof, monkeypatch, capsys, tmp_path, bridge
):
    server, kwargs = container_snapshot("server")
    compose = tmp_path / "compose.yml"
    image = "ghcr.io/chrislusf/seaweedfs:4.48@sha256:" + "a" * 64
    compose.write_text(f"services:\n  minio:\n    image: {image}\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    caddy = "caddy:2.11.7-alpine@sha256:" + "b" * 64
    dockerfile.write_text(f"FROM {caddy}\n", encoding="utf-8")
    values = tmp_path / "values.yaml"
    values.write_text("backup:\n  minioBucket: backups\n", encoding="utf-8")
    requests = []

    def generate_certificate(path, **kwargs):
        requests.append((path, kwargs))
        return SimpleNamespace(directory=path)

    monkeypatch.setattr(
        proof,
        "generate_fixture_certificate",
        generate_certificate,
    )
    bridge["Containers"][PROXY_ID] = {
        "IPv4Address": "198.18.42.10/24",
        "IPv6Address": "",
    }
    cases = [
        (["preflight-networks"], "[]"),
        (["preflight-routes"], "[]"),
        (
            ["find-bridge", "", NETWORK_ID],
            json.dumps([{"Id": NETWORK_ID, "Name": "kind"}]),
        ),
        (["find-container", "", "fixture"], f"{SERVER_ID} fixture\n"),
        (["inspect-container", *kwargs.values()], json.dumps(server)),
        (
            [
                "validate-bridge",
                NETWORK_ID,
                RUN_TOKEN,
                NODE_ID,
                "198.18.42.2",
                SERVER_ID,
                "198.18.42.11",
                PROXY_ID,
                "198.18.42.10",
            ],
            json.dumps([bridge]),
        ),
        (["compose-image", str(compose)], ""),
        (["caddy-image", str(dockerfile)], ""),
        (["backup-bucket", str(values)], ""),
        (["certificate", str(tmp_path)], ""),
    ]
    for argv, payload in cases:
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        assert proof.main(argv) == 0
        output = capsys.readouterr().out.strip()
        if argv[0] == "caddy-image":
            assert output == caddy
        elif argv[0] == "backup-bucket":
            assert output == "backups"
    assert requests == [(tmp_path, {"server_ip": "198.18.42.10"})]


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["unknown"],
        ["preflight-routes", "extra"],
        ["validate-bridge", NETWORK_ID, RUN_TOKEN, NODE_ID],
        [
            "validate-bridge",
            NETWORK_ID,
            RUN_TOKEN,
            NODE_ID,
            "198.18.42.2",
            NODE_ID,
            "198.18.42.3",
        ],
    ],
)
def test_cli_rejects_invalid_commands_and_bridge_members(proof, monkeypatch, args):
    monkeypatch.setattr(sys, "stdin", io.StringIO("[{}]"))
    assert proof.main(args) == 1


def test_cli_module_entrypoint_uses_the_same_dispatch(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["fixture", "preflight-routes"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("[]"))
    with pytest.raises(SystemExit) as result:
        runpy.run_path(
            str(ROOT / "scripts/k8s/networkpolicy_runtime_backup_bridge.py"),
            run_name="__main__",
        )
    assert result.value.code == 0


class PosixOSProxy:
    name = "posix"

    def __init__(self):
        self.modes = []

    def __getattr__(self, name):
        return getattr(os, name)

    def fchmod(self, descriptor, mode):
        self.modes.append((descriptor, mode))


def test_posix_private_directory_guard_and_file_modes(proof, tmp_path, monkeypatch):
    os_proxy = PosixOSProxy()
    monkeypatch.setattr(proof, "os", os_proxy)
    monkeypatch.setattr(proof, "stat", SimpleNamespace(S_IMODE=lambda _: 0o755))
    with pytest.raises(ValueError, match="must be private"):
        proof._work_directory(tmp_path)
    target = tmp_path / "private"
    created = []
    proof._write_fixture(target, "fixture", created)
    assert target.read_text(encoding="ascii") == "fixture"
    assert created == [target]
    assert os_proxy.modes[0][1] == 0o600


def test_certificate_sets_private_child_mode(proof, tmp_path, openssl, monkeypatch):
    os_proxy = PosixOSProxy()
    modes = []
    monkeypatch.setattr(proof, "os", os_proxy)
    monkeypatch.setattr(proof, "_work_directory", lambda path: path)
    monkeypatch.setattr(
        type(tmp_path), "chmod", lambda path, mode: modes.append((path, mode))
    )
    certificate = proof.generate_fixture_certificate(
        tmp_path, server_ip="198.18.42.10", openssl=openssl
    )
    assert modes == [(certificate.directory, 0o700)]
    assert all(mode == 0o600 for _, mode in os_proxy.modes)


def test_bridge_accepts_only_the_recorded_identity_and_members(proof, bridge) -> None:
    assert callable(getattr(proof, "validate_owned_kind_bridge", None))
    assert validate(proof, bridge) == {
        "network_id": NETWORK_ID,
        "subnet": SUBNET,
        "gateway": "198.18.42.1",
        "endpoints": ENDPOINTS,
    }


def test_bridge_accepts_an_owned_empty_bridge_before_attachments(proof, bridge) -> None:
    bridge["Containers"] = {}
    assert validate(proof, bridge, endpoints={})["endpoints"] == {}


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("Id",), "e" * 64),
        (("Name",), "kind-copy"),
        (("Driver",), "host"),
        (("Scope",), "global"),
        (("Internal",), True),
        (("EnableIPv6",), True),
        (("Labels", OWNER_LABEL), "e" * 12),
        (("IPAM", "Driver"), "other"),
        (("IPAM", "Config"), []),
        (("IPAM", "Config"), [{"Subnet": "198.18.43.0/24", "Gateway": "198.18.43.1"}]),
        (("IPAM", "Config"), [{"Subnet": SUBNET, "Gateway": "198.18.43.1"}]),
        (("Containers", NODE_ID, "IPv4Address"), "198.18.42.2/16"),
        (("Containers", NODE_ID, "IPv4Address"), "198.18.42.3/24"),
        (("Containers", NODE_ID, "IPv4Address"), "not-an-address"),
        (("Containers", NODE_ID, "IPv6Address"), "fd00::1/64"),
        (("Containers",), {}),
    ],
)
def test_bridge_rejects_modified_snapshot(proof, bridge, path, value) -> None:
    candidate = copy.deepcopy(bridge)
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate(proof, candidate)


def test_bridge_rejects_unowned_extra_endpoint(proof, bridge) -> None:
    bridge["Containers"]["e" * 64] = {
        "IPv4Address": "198.18.42.12/24",
        "IPv6Address": "",
    }
    with pytest.raises(ValueError):
        validate(proof, bridge)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_id": "a" * 12},
        {"owner_token": "not-an-owned-run"},
        {"expected_subnet": None},
        {"expected_subnet": "10.18.42.0/24"},
        {"expected_subnet": "198.18.42.2/24"},
        {"expected_subnet": "2001:db8::/64"},
        {"expected_endpoints": {"b" * 12: "198.18.42.2"}},
        {"expected_endpoints": {NODE_ID: None}},
        {"expected_endpoints": {NODE_ID: "bad"}},
        {
            "expected_endpoints": {
                NODE_ID: "198.18.42.2",
                SERVER_ID: "198.18.42.11",
                PROXY_ID: "198.18.42.10",
                "e" * 64: "198.18.42.12",
            }
        },
        {"expected_endpoints": {NODE_ID: "198.18.42.1", SERVER_ID: "198.18.42.10"}},
        {"expected_endpoints": {NODE_ID: "198.18.42.2", SERVER_ID: "198.18.42.2"}},
    ],
)
def test_bridge_rejects_malformed_or_unsafe_expectations(
    proof, bridge, overrides
) -> None:
    with pytest.raises(ValueError):
        validate(proof, bridge, **overrides)


def test_bridge_rejects_a_non_object_snapshot(proof) -> None:
    with pytest.raises(ValueError):
        validate(proof, [])


@pytest.fixture(scope="module")
def openssl() -> str:
    found = shutil.which("openssl")
    if found is None and os.name == "nt":
        git = shutil.which("git")
        if git is not None:
            candidate = Path(git).parent.parent / "usr" / "bin" / "openssl.exe"
            if candidate.is_file():
                found = str(candidate)
    assert found is not None, "the proof requires its existing OpenSSL executable"
    return found


def test_fixture_certificate_has_a_trusted_ip_san_and_bounded_lifetime(
    proof, tmp_path, openssl, request
) -> None:
    assert callable(getattr(proof, "generate_fixture_certificate", None))
    issued_at = datetime.now(UTC)
    result = proof.generate_fixture_certificate(
        tmp_path, server_ip="198.18.42.10", openssl=openssl
    )

    def cleanup() -> None:
        for path in (result.ca_cert, result.server_cert, result.server_key):
            path.unlink(missing_ok=True)
        result.directory.rmdir()

    request.addfinalizer(cleanup)
    assert result.directory.parent == tmp_path
    assert set(result.directory.iterdir()) == {
        result.ca_cert,
        result.server_cert,
        result.server_key,
    }
    ca = x509.load_pem_x509_certificate(result.ca_cert.read_bytes())
    server = x509.load_pem_x509_certificate(result.server_cert.read_bytes())
    key = serialization.load_pem_private_key(
        result.server_key.read_bytes(), password=None
    )
    ca.verify_directly_issued_by(ca)
    server.verify_directly_issued_by(ca)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert (
        server.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        is False
    )
    assert server.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value == x509.SubjectAlternativeName(
        [x509.IPAddress(ipaddress.ip_address("198.18.42.10"))]
    )
    assert (
        ExtendedKeyUsageOID.SERVER_AUTH
        in server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    )
    assert key.public_key().public_numbers() == server.public_key().public_numbers()
    now = datetime.now(UTC)
    for cert, maximum in ((ca, timedelta(days=3)), (server, timedelta(days=2))):
        assert cert.not_valid_before_utc <= now < cert.not_valid_after_utc
        assert cert.not_valid_after_utc - cert.not_valid_before_utc <= maximum
    assert server.not_valid_after_utc > issued_at + timedelta(days=1)
    assert server.not_valid_after_utc > now + timedelta(days=1)
    assert ca.not_valid_before_utc <= server.not_valid_before_utc
    assert server.not_valid_after_utc < ca.not_valid_after_utc
    if os.name == "posix":
        assert stat.S_IMODE(result.directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(result.server_key.stat().st_mode) == 0o600


def test_certificate_validity_accepts_bounded_lifetimes_and_rejects_invalid_ones(
    proof, tmp_path, openssl, monkeypatch
):
    fixture = proof.generate_fixture_certificate(
        tmp_path, server_ip="198.18.42.10", openssl=openssl
    )
    ca_pem = fixture.ca_cert.read_bytes()
    server_pem = fixture.server_cert.read_bytes()
    key_pem = fixture.server_key.read_text(encoding="ascii")
    ca = x509.load_pem_x509_certificate(ca_pem)
    server = x509.load_pem_x509_certificate(server_pem)
    now = datetime.now(UTC)
    ca_before = now - timedelta(seconds=10)
    server_before = now - timedelta(seconds=5)
    ca_after = now + timedelta(days=2, hours=12)
    server_after = now + timedelta(days=1, hours=12)

    class CertificateWithValidity:
        def __init__(self, cert, before, after):
            self.cert = cert
            self.not_valid_before_utc = before
            self.not_valid_after_utc = after

        def __getattr__(self, name):
            return getattr(self.cert, name)

        def verify_directly_issued_by(self, issuer):
            self.cert.verify_directly_issued_by(issuer.cert)

    def check(ca_dates, server_dates):
        candidates = (
            CertificateWithValidity(ca, *ca_dates),
            CertificateWithValidity(server, *server_dates),
        )
        monkeypatch.setattr(
            proof.x509,
            "load_pem_x509_certificate",
            lambda contents: candidates[0] if contents == ca_pem else candidates[1],
        )
        proof._validate_certificate(
            ca_pem.decode("ascii"),
            server_pem.decode("ascii"),
            key_pem,
            ipaddress.ip_address("198.18.42.10"),
        )

    # A valid pair need not have the exact OpenSSL default durations.
    check((ca_before, ca_after), (server_before, server_after))
    bad_dates = [
        (
            (ca_before, ca_before + timedelta(days=3, seconds=1)),
            (server_before, server_after),
        ),
        (
            (ca_before, ca_after),
            (server_before, server_before + timedelta(days=2, seconds=1)),
        ),
        (
            (server_before + timedelta(seconds=1), ca_after),
            (server_before, server_after),
        ),
        ((ca_before, server_after), (server_before, server_after)),
        ((ca_before, now - timedelta(seconds=1)), (server_before, server_after)),
        ((ca_before, ca_after), (now + timedelta(seconds=1), server_after)),
        ((ca_before, ca_after), (server_before, now - timedelta(seconds=1))),
        ((ca_before, ca_after), (server_before, now + timedelta(hours=23))),
    ]
    for ca_dates, server_dates in bad_dates:
        with pytest.raises(ValueError):
            check(ca_dates, server_dates)


@pytest.mark.parametrize(
    "server_ip",
    [None, "127.0.0.1", "198.20.0.1", "::1", "not-an-ip", "198.18.42.10/24"],
)
def test_fixture_certificate_rejects_non_synthetic_or_malformed_ips(
    proof, tmp_path, openssl, server_ip
) -> None:
    with pytest.raises(ValueError):
        proof.generate_fixture_certificate(
            tmp_path, server_ip=server_ip, openssl=openssl
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("directory", [Path("relative"), Path("does-not-exist")])
def test_fixture_certificate_rejects_invalid_work_directories(proof, directory) -> None:
    with pytest.raises(ValueError):
        proof.generate_fixture_certificate(directory, server_ip="198.18.42.10")


def test_fixture_certificate_rejects_missing_absolute_work_directory(
    proof, tmp_path
) -> None:
    with pytest.raises(ValueError):
        proof.generate_fixture_certificate(
            tmp_path / "absent", server_ip="198.18.42.10"
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_fixture_certificate_requires_private_work_directory(proof, tmp_path) -> None:
    tmp_path.chmod(0o755)
    try:
        with pytest.raises(ValueError, match="private"):
            proof.generate_fixture_certificate(tmp_path, server_ip="198.18.42.10")
        assert not list(tmp_path.iterdir())
    finally:
        tmp_path.chmod(0o700)


def test_fixture_certificate_rejects_an_empty_openssl_command(proof, tmp_path) -> None:
    with pytest.raises(ValueError):
        proof.generate_fixture_certificate(
            tmp_path, server_ip="198.18.42.10", openssl=""
        )
    assert not list(tmp_path.iterdir())


def test_fixture_certificate_rejects_a_symlinked_work_directory(
    proof, tmp_path, openssl
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable on this platform")
    with pytest.raises(ValueError):
        proof.generate_fixture_certificate(
            linked, server_ip="198.18.42.10", openssl=openssl
        )
    assert not list(actual.iterdir())


def test_fixture_certificate_cleans_its_directory_on_openssl_failure(
    proof, tmp_path
) -> None:
    with pytest.raises(RuntimeError, match="certificate generation failed"):
        proof.generate_fixture_certificate(
            tmp_path,
            server_ip="198.18.42.10",
            openssl=str(tmp_path / "missing-openssl"),
        )
    assert not list(tmp_path.iterdir())


def test_fixture_certificate_does_not_delete_an_unowned_temp_path(
    proof, tmp_path, monkeypatch
) -> None:
    work = tmp_path / "work"
    victim = tmp_path / "not-owned"
    work.mkdir(mode=0o700)
    victim.mkdir()
    monkeypatch.setattr(proof.tempfile, "mkdtemp", lambda **kwargs: str(victim))
    with pytest.raises(RuntimeError, match="certificate generation failed"):
        proof.generate_fixture_certificate(work, server_ip="198.18.42.10")
    assert victim.is_dir()


def test_fixture_certificate_rejects_malformed_successful_openssl_output(
    proof, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        proof, "run_command", lambda *args, **kwargs: SimpleNamespace(stdout="")
    )
    with pytest.raises(RuntimeError, match="certificate generation failed"):
        proof.generate_fixture_certificate(tmp_path, server_ip="198.18.42.10")
    assert not list(tmp_path.iterdir())


def test_fixture_certificate_rejects_a_wrong_ip_san(
    proof, tmp_path, openssl, monkeypatch
) -> None:
    original = proof.run_command

    def wrong_san(command, **kwargs):
        if command[1] == "x509":
            config = Path(command[command.index("-extfile") + 1])
            config.write_text(
                config.read_text(encoding="ascii").replace(
                    "198.18.42.10", "198.18.42.11"
                ),
                encoding="ascii",
            )
        return original(command, **kwargs)

    monkeypatch.setattr(proof, "run_command", wrong_san)
    with pytest.raises(RuntimeError, match="certificate generation failed"):
        proof.generate_fixture_certificate(
            tmp_path, server_ip="198.18.42.10", openssl=openssl
        )
    assert not list(tmp_path.iterdir())
