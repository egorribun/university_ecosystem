"""Offline validation and TLS material for the disposable backup proof."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID
from networkpolicy_runtime_kube import run_command

BRIDGE_OWNER_LABEL = "org.university-ecosystem.netpol-owner"
_SYNTHETIC_RANGE = ipaddress.ip_network("198.18.0.0/15")
_DOCKER_ID = re.compile(r"[0-9a-f]{64}")
_RUN_TOKEN = re.compile(r"[0-9a-f]{12}")
_BACKUP_SUBNET = ipaddress.ip_network("198.18.42.0/24")
_SERVER_IP = "198.18.42.11"
_PROXY_IP = "198.18.42.10"
_COMPOSE_IMAGE = re.compile(
    r"ghcr\.io/chrislusf/seaweedfs:[0-9]+(?:\.[0-9]+){1,2}@sha256:[0-9a-f]{64}"
)
_CADDY_FROM = re.compile(
    r"(?i:FROM)[ \t]+(caddy:[0-9]+\.[0-9]+\.[0-9]+-alpine@sha256:[0-9a-f]{64})"
    r"(?:[ \t]+(?i:AS)[ \t]+[a-zA-Z0-9_-]+)?[ \t]*"
)
_BUCKET = re.compile(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]")
_PORT = re.compile(r"[1-9][0-9]{0,4}/(?:tcp|udp|sctp)")


def _network_inventory(objects: object, identities: list[str]) -> list[dict[str, Any]]:
    """Bind one Docker inspection response to its complete, unique inventory."""
    if (
        not isinstance(objects, list)
        or len(identities) != len(set(identities))
        or len(objects) != len(identities)
        or any(
            not isinstance(item, str) or not _DOCKER_ID.fullmatch(item)
            for item in identities
        )
    ):
        raise ValueError("invalid network inventory")
    seen: set[str] = set()
    for item in objects:
        if not isinstance(item, dict):
            raise ValueError("invalid network inventory")
        identity, name = item.get("Id"), item.get("Name")
        if identity not in identities or identity in seen or not isinstance(name, str):
            raise ValueError("invalid network inventory")
        seen.add(identity)
    return objects


def validate_network_preflight(objects: object, identities: list[str]) -> None:
    """Reject an existing Kind bridge or overlap with the fixture subnet."""
    try:
        for item in _network_inventory(objects, identities):
            if item["Name"] == "kind":
                raise ValueError()
            config = item["IPAM"]["Config"]
            if config is None and (item["Name"], item.get("Driver")) in (
                ("host", "host"),
                ("none", "null"),
            ):
                continue
            if not isinstance(config, list):
                raise ValueError()
            for entry in config:
                subnet = ipaddress.ip_network(entry["Subnet"], strict=False)
                if subnet.version == 4 and subnet.overlaps(_BACKUP_SUBNET):
                    raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError(
            "invalid, occupied, or overlapping network inventory"
        ) from None


def recover_bridge_identity(
    objects: object, identities: list[str], recorded: str
) -> str:
    """Find the exact original Kind network, or an eligible partial creation."""
    found = ""
    for item in _network_inventory(objects, identities):
        identity, name = item["Id"], item["Name"]
        if recorded and identity == recorded and name != "kind":
            raise ValueError("recorded bridge was renamed")
        if name == "kind":
            if found or (recorded and identity != recorded):
                raise ValueError("recorded bridge identity changed")
            found = identity
    return found


def validate_host_routes(routes: object) -> None:
    """Exclude the default route and reject overlap with explicit IPv4 routes."""
    try:
        if not isinstance(routes, list):
            raise ValueError()
        for route in routes:
            destination = route["dst"]
            if destination != "default":
                network = ipaddress.ip_network(destination, strict=False)
                if network.version != 4 or network.overlaps(_BACKUP_SUBNET):
                    raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError("invalid or overlapping host route inventory") from None


def validate_container_inspection(
    objects: object,
    *,
    role: str,
    identity: str,
    name: str,
    bridge: str,
    owner: str,
    cluster: str,
    image: str,
) -> str:
    """Validate an owned fixture container or Kind node and return its endpoint."""
    try:
        if (
            not _DOCKER_ID.fullmatch(identity)
            or not _DOCKER_ID.fullmatch(bridge)
            or not _RUN_TOKEN.fullmatch(owner)
            or not isinstance(image, str)
            or not image
            or not isinstance(objects, list)
            or len(objects) != 1
        ):
            raise ValueError()
        item = objects[0]
        labels = item["Config"]["Labels"]
        host = item["HostConfig"]
        running = item["State"]["Running"]
        settings = item["NetworkSettings"]
        if (
            item["Id"] != identity
            or item["Name"] != "/" + name
            or item["Config"]["Image"] != image
            or not isinstance(labels, dict)
            or not isinstance(running, bool)
            or not isinstance(settings, dict)
            or host["NetworkMode"] not in ("kind", bridge)
        ):
            raise ValueError()
        if role in ("server", "proxy"):
            ports = settings.get("Ports")
            if (
                labels.get(BRIDGE_OWNER_LABEL) != owner
                or host["PublishAllPorts"] is not False
                or host["PortBindings"] not in (None, {})
                or (
                    ports is not None
                    and (
                        not isinstance(ports, dict)
                        or any(
                            not isinstance(port, str)
                            or not _PORT.fullmatch(port)
                            or int(port.partition("/")[0]) > 65535
                            or value is not None
                            for port, value in ports.items()
                        )
                    )
                )
            ):
                raise ValueError()
        elif role == "node":
            if (
                labels.get("io.x-k8s.kind.cluster") != cluster
                or labels.get("io.x-k8s.kind.role") != "control-plane"
            ):
                raise ValueError()
        else:
            raise ValueError()
        networks = settings["Networks"]
        if not isinstance(networks, dict) or set(networks) - {"kind"}:
            raise ValueError()
        endpoint = networks.get("kind", {})
        if not isinstance(endpoint, dict):
            raise ValueError()
        address = endpoint.get("IPAddress", "")
        network_id = endpoint.get("NetworkID", "")
        if not isinstance(address, str):
            raise ValueError()
        if not address:
            if running or network_id not in ("", bridge):
                raise ValueError()
            return "-"
        ip = ipaddress.ip_address(address)
        if (
            network_id != bridge
            or not isinstance(ip, ipaddress.IPv4Address)
            or ip not in _BACKUP_SUBNET
            or str(ip) in ("198.18.42.0", "198.18.42.1", "198.18.42.255")
            or (role == "server" and str(ip) != _SERVER_IP)
            or (role == "proxy" and str(ip) != _PROXY_IP)
            or (role == "node" and str(ip) in (_SERVER_IP, _PROXY_IP))
        ):
            raise ValueError()
        return str(ip)
    except (ValueError, TypeError, KeyError):
        raise ValueError("container identity or network membership differs") from None


def recover_container_identity(listing: str, recorded: str, name: str) -> str:
    """Recover a full container ID without accepting a replacement or rename."""
    found = ""
    for line in listing.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not _DOCKER_ID.fullmatch(parts[0]):
            raise ValueError("invalid container inventory")
        identity, candidate = parts
        if recorded and identity == recorded and candidate != name:
            raise ValueError("recorded container was renamed")
        if candidate == name:
            if found or (recorded and identity != recorded):
                raise ValueError("recorded container identity changed")
            found = identity
    return found


def read_compose_image(path: Path) -> str:
    """Read the pinned storage image from the committed source archive."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]["minio"][
            "image"
        ]
        if not isinstance(value, str) or not _COMPOSE_IMAGE.fullmatch(value):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError):
        raise ValueError("archived Compose storage image is invalid") from None


def read_caddy_image(path: Path) -> str:
    """Read the immutable Caddy image in the archive's final Dockerfile stage."""
    try:
        stages = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"^[ \t]*FROM[ \t]+", line, re.IGNORECASE)
        ]
        match = _CADDY_FROM.fullmatch(stages[-1]) if stages else None
        if match is None:
            raise ValueError()
        return match.group(1)
    except (OSError, UnicodeError, ValueError):
        raise ValueError("archived Caddy runtime image is invalid") from None


def read_backup_bucket(path: Path) -> str:
    """Read the dedicated synthetic bucket from the archived chart values."""
    try:
        node = yaml.compose(path.read_text(encoding="utf-8"))
        for name in ("backup", "minioBucket"):
            if not isinstance(node, yaml.MappingNode):
                raise ValueError()
            matches = [
                (key, value)
                for key, value in node.value
                if isinstance(key, yaml.ScalarNode) and key.value == name
            ]
            if len(matches) != 1 or matches[0][0].tag != "tag:yaml.org,2002:str":
                raise ValueError()
            node = matches[0][1]
        if (
            not isinstance(node, yaml.ScalarNode)
            or node.tag != "tag:yaml.org,2002:str"
            or not _BUCKET.fullmatch(node.value)
        ):
            raise ValueError()
        return node.value
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        raise ValueError("archived backup bucket is invalid") from None


def _fixture_subnet(value: str) -> ipaddress.IPv4Network:
    if not isinstance(value, str):
        raise ValueError("fixture subnet must be an IPv4 CIDR")
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError:
        raise ValueError("fixture subnet must be an IPv4 CIDR") from None
    if (
        not isinstance(network, ipaddress.IPv4Network)
        or not network.subnet_of(_SYNTHETIC_RANGE)
        or not 16 <= network.prefixlen <= 29
    ):
        raise ValueError("fixture subnet must be a bounded synthetic IPv4 range")
    return network


def _fixture_address(
    value: str, network: ipaddress.IPv4Network
) -> ipaddress.IPv4Address:
    if not isinstance(value, str):
        raise ValueError("fixture address must be IPv4")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ValueError("fixture address must be IPv4") from None
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or address not in network
        or address in (network.network_address, network.broadcast_address)
    ):
        raise ValueError("fixture address must be usable within its subnet")
    return address


def validate_owned_kind_bridge(
    snapshot: dict[str, Any],
    *,
    expected_id: str,
    owner_token: str,
    expected_subnet: str,
    expected_endpoints: dict[str, str],
) -> dict[str, Any]:
    """Check a recorded Docker network snapshot without querying or changing Docker.

    Endpoint keys must be the complete container IDs recorded at creation. The
    exact set and addresses are checked, including the empty initial bridge.
    """
    if not isinstance(expected_id, str) or not _DOCKER_ID.fullmatch(expected_id):
        raise ValueError("a complete recorded network ID is required")
    if not isinstance(owner_token, str) or not _RUN_TOKEN.fullmatch(owner_token):
        raise ValueError("a valid run ownership token is required")
    network = _fixture_subnet(expected_subnet)
    if not isinstance(expected_endpoints, dict) or len(expected_endpoints) > 3:
        raise ValueError("at most three recorded fixture endpoints are allowed")

    expected: dict[str, str] = {}
    for endpoint_id, address in expected_endpoints.items():
        if not isinstance(endpoint_id, str) or not _DOCKER_ID.fullmatch(endpoint_id):
            raise ValueError("a complete recorded endpoint ID is required")
        expected[endpoint_id] = str(_fixture_address(address, network))
    if len(set(expected.values())) != len(expected):
        raise ValueError("fixture endpoints must use distinct addresses")

    if not isinstance(snapshot, dict):
        raise ValueError("network inspection must return one object")
    labels = snapshot.get("Labels")
    if (
        snapshot.get("Id") != expected_id
        or snapshot.get("Name") != "kind"
        or snapshot.get("Driver") != "bridge"
        or snapshot.get("Scope") != "local"
        or snapshot.get("Internal") is not False
        or snapshot.get("EnableIPv6") is not False
        or not isinstance(labels, dict)
        or labels.get(BRIDGE_OWNER_LABEL) != owner_token
    ):
        raise ValueError("network identity, ownership or bridge settings differ")

    ipam = snapshot.get("IPAM")
    if not isinstance(ipam, dict) or ipam.get("Driver") != "default":
        raise ValueError("network IPAM is not the expected default driver")
    config = ipam.get("Config")
    if (
        not isinstance(config, list)
        or len(config) != 1
        or not isinstance(config[0], dict)
    ):
        raise ValueError("network must contain exactly one IPv4 subnet")
    if config[0].get("Subnet") != str(network):
        raise ValueError("network subnet differs from the recorded subnet")
    gateway = _fixture_address(config[0].get("Gateway"), network)
    if str(gateway) in expected.values():
        raise ValueError("gateway cannot be a fixture endpoint")

    containers = snapshot.get("Containers")
    if not isinstance(containers, dict) or set(containers) != set(expected):
        raise ValueError("network endpoint membership differs from the recorded IDs")
    for endpoint_id, address in expected.items():
        observed = containers[endpoint_id]
        if not isinstance(observed, dict) or observed.get("IPv6Address") != "":
            raise ValueError("network endpoint data is malformed")
        try:
            interface = ipaddress.ip_interface(observed.get("IPv4Address"))
        except (TypeError, ValueError):
            raise ValueError("network endpoint IPv4 address is malformed") from None
        if interface.network != network or str(interface.ip) != address:
            raise ValueError("network endpoint address differs from its recorded value")

    return {
        "network_id": expected_id,
        "subnet": str(network),
        "gateway": str(gateway),
        "endpoints": dict(sorted(expected.items())),
    }


@dataclass(frozen=True)
class FixtureCertificate:
    """Paths owned by the caller's disposable work directory."""

    directory: Path
    ca_cert: Path
    server_cert: Path
    server_key: Path


def _work_directory(directory: Path) -> Path:
    if (
        not isinstance(directory, Path)
        or not directory.is_absolute()
        or ".." in directory.parts
    ):
        raise ValueError("fixture work directory must be an absolute path")
    for component in (directory, *directory.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError("fixture work directory must not traverse links")
    if not directory.is_dir() or directory.resolve(strict=True) != directory:
        raise ValueError("fixture work directory must already exist")
    if os.name == "posix" and stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise ValueError("fixture work directory must be private")
    return directory


def _write_fixture(path: Path, contents: str, created: list[Path]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    created.append(path)
    with os.fdopen(descriptor, "wb") as stream:
        if os.name == "posix":
            os.fchmod(stream.fileno(), 0o600)
        stream.write(contents.encode("ascii"))


def _validate_certificate(
    ca_pem: str, server_pem: str, server_key_pem: str, address: ipaddress.IPv4Address
) -> None:
    """Fail closed if OpenSSL produced an unusable or unexpected identity."""
    try:
        ca = x509.load_pem_x509_certificate(ca_pem.encode("ascii"))
        server = x509.load_pem_x509_certificate(server_pem.encode("ascii"))
        key = serialization.load_pem_private_key(
            server_key_pem.encode("ascii"), password=None
        )
        ca.verify_directly_issued_by(ca)
        server.verify_directly_issued_by(ca)
        ca_constraints = ca.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value
        server_constraints = server.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value
        san = server.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        usage = server.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        public_encoding = serialization.Encoding.DER
        public_format = serialization.PublicFormat.SubjectPublicKeyInfo
        now = datetime.now(UTC)
        if (
            not ca_constraints.ca
            or ca_constraints.path_length != 0
            or server_constraints.ca
            or list(san) != [x509.IPAddress(address)]
            or list(usage) != [ExtendedKeyUsageOID.SERVER_AUTH]
            or key.public_key().public_bytes(public_encoding, public_format)
            != server.public_key().public_bytes(public_encoding, public_format)
            or any(
                not cert.not_valid_before_utc <= now < cert.not_valid_after_utc
                or cert.not_valid_after_utc - cert.not_valid_before_utc
                > timedelta(days=max_days)
                for cert, max_days in ((ca, 3), (server, 2))
            )
            or ca.not_valid_before_utc > server.not_valid_before_utc
            or ca.not_valid_after_utc <= server.not_valid_after_utc
            or server.not_valid_after_utc <= now + timedelta(days=1)
        ):
            raise ValueError("generated certificate identity differs from fixture")
    except (
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
    ):
        raise ValueError("generated certificate identity is invalid") from None


def generate_fixture_certificate(
    directory: Path, *, server_ip: str, openssl: str = "openssl"
) -> FixtureCertificate:
    """Create one short-lived CA and IP-SAN server identity using OpenSSL.

    The CA private key is removed before return. The caller owns the returned
    child directory and its remaining files; no Docker or network call is made.
    """
    if not isinstance(server_ip, str):
        raise ValueError("fixture server IP must be a synthetic IPv4 address")
    try:
        address = ipaddress.ip_address(server_ip)
    except ValueError:
        raise ValueError("fixture server IP must be a synthetic IPv4 address") from None
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or address not in _SYNTHETIC_RANGE
        or address
        in (_SYNTHETIC_RANGE.network_address, _SYNTHETIC_RANGE.broadcast_address)
    ):
        raise ValueError("fixture server IP must be a synthetic IPv4 address")
    if not isinstance(openssl, str) or not openssl or "\x00" in openssl:
        raise ValueError("OpenSSL executable is required")
    root = _work_directory(directory)
    child = Path(tempfile.mkdtemp(prefix="aud189-tls-", dir=root))
    created: list[Path] = []
    success = False
    owned_child = False
    try:
        if (
            child.parent != root
            or not child.name.startswith("aud189-tls-")
            or child.is_symlink()
            or child.is_junction()
            or not child.is_dir()
            or child.resolve(strict=True).parent != root
        ):
            raise ValueError("fixture certificate directory is unsafe")
        owned_child = True
        if os.name == "posix":
            child.chmod(0o700)
        ca_key = child / "ca.key"
        ca_cert = child / "ca.crt"
        server_key = child / "server.key"
        server_cert = child / "server.crt"
        config = child / "openssl.cnf"
        _write_fixture(
            config,
            "[req]\ndistinguished_name=dn\n[dn]\n[server]\n"
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            f"subjectAltName=IP:{address}\n",
            created,
        )
        ca_private = run_command(
            [
                openssl,
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
            ],
            timeout=30,
        ).stdout
        _write_fixture(ca_key, ca_private, created)
        ca_public = run_command(
            [
                openssl,
                "req",
                "-new",
                "-x509",
                "-config",
                str(config),
                "-key",
                str(ca_key),
                "-days",
                "3",
                "-sha256",
                "-subj",
                "/CN=aud189-fixture-ca",
                "-addext",
                "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            ],
            timeout=30,
        ).stdout
        _write_fixture(ca_cert, ca_public, created)
        server_private = run_command(
            [
                openssl,
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:2048",
            ],
            timeout=30,
        ).stdout
        _write_fixture(server_key, server_private, created)
        request = run_command(
            [
                openssl,
                "req",
                "-new",
                "-config",
                str(config),
                "-key",
                str(server_key),
                "-subj",
                "/CN=aud189-fixture",
            ],
            timeout=30,
        ).stdout
        server_public = run_command(
            [
                openssl,
                "x509",
                "-req",
                "-CA",
                str(ca_cert),
                "-CAkey",
                str(ca_key),
                "-set_serial",
                str(secrets.randbits(128) | 1),
                "-days",
                "2",
                "-sha256",
                "-extfile",
                str(config),
                "-extensions",
                "server",
            ],
            stdin=request,
            timeout=30,
        ).stdout
        _validate_certificate(ca_public, server_public, server_private, address)
        _write_fixture(server_cert, server_public, created)
        ca_key.unlink()
        created.remove(ca_key)
        config.unlink()
        created.remove(config)
        success = True
        return FixtureCertificate(child, ca_cert, server_cert, server_key)
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        raise RuntimeError("certificate generation failed") from None
    finally:
        if not success and owned_child:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            child.rmdir()


def main(argv: list[str] | None = None) -> int:
    """Expose the offline validators to the shell without Docker access."""
    arguments = sys.argv[1:] if argv is None else argv
    try:
        command, *args = arguments
        if command == "preflight-networks":
            validate_network_preflight(json.load(sys.stdin), args)
        elif command == "preflight-routes" and not args:
            validate_host_routes(json.load(sys.stdin))
        elif command == "find-bridge":
            recorded, *identities = args
            print(recover_bridge_identity(json.load(sys.stdin), identities, recorded))
        elif command == "find-container":
            recorded, name = args
            print(recover_container_identity(sys.stdin.read(), recorded, name))
        elif command == "inspect-container":
            role, identity, name, bridge, owner, cluster, image = args
            print(
                validate_container_inspection(
                    json.load(sys.stdin),
                    role=role,
                    identity=identity,
                    name=name,
                    bridge=bridge,
                    owner=owner,
                    cluster=cluster,
                    image=image,
                )
            )
        elif command == "validate-bridge":
            identity, owner, *members = args
            objects = json.load(sys.stdin)
            if len(members) % 2 or not isinstance(objects, list) or len(objects) != 1:
                raise ValueError()
            endpoints = dict(zip(members[::2], members[1::2], strict=True))
            if len(endpoints) != len(members) // 2:
                raise ValueError()
            validate_owned_kind_bridge(
                objects[0],
                expected_id=identity,
                owner_token=owner,
                expected_subnet=str(_BACKUP_SUBNET),
                expected_endpoints=endpoints,
            )
        elif command == "compose-image":
            (path,) = args
            print(read_compose_image(Path(path)))
        elif command == "caddy-image":
            (path,) = args
            print(read_caddy_image(Path(path)))
        elif command == "backup-bucket":
            (path,) = args
            print(read_backup_bucket(Path(path)))
        elif command == "certificate":
            (directory,) = args
            print(
                generate_fixture_certificate(
                    Path(directory), server_ip=_PROXY_IP
                ).directory
            )
        else:
            raise ValueError()
    except (ValueError, TypeError, KeyError, IndexError, OSError, RuntimeError):
        print("backup fixture validation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
