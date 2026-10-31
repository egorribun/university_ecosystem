"""Bind private inspect records to the fixed owned client-IP probe input.

This module does not authenticate its inputs or perform Docker operations.
The runtime caller must hold the signed owner's lifecycle lease, establish the
source and daemon identities, and collect and recheck these records itself.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
from dataclasses import asdict, dataclass
from typing import Any, NoReturn

from scripts import live_stand, owned_client_ip_probe
from scripts.owned_client_ip_acceptance import _BACKEND_COMMAND

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_WITNESS_KEY = secrets.token_bytes(32)
_SNAPSHOT_KEYS = frozenset(
    {
        "owner",
        "evidence",
        "containers",
        "networks",
        "probe",
        "image",
        "expected_probe_id",
        "run_id",
    }
)


class RuntimeNotReady(RuntimeError):
    """A closed failure without private Docker or network details."""


def _not_ready() -> NoReturn:
    raise RuntimeNotReady("owned client-IP runtime is not ready") from None


def _environment(record: dict[str, Any]) -> dict[str, str]:
    config = record.get("Config")
    entries = config.get("Env") if isinstance(config, dict) else None
    if not isinstance(entries, list):
        _not_ready()
    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, str) or "=" not in entry:
            _not_ready()
        name, value = entry.split("=", 1)
        if not name or name in result:
            _not_ready()
        result[name] = value
    return result


def _subnet(record: dict[str, Any]) -> ipaddress.IPv4Network:
    ipam = record.get("IPAM")
    entries = ipam.get("Config") if isinstance(ipam, dict) else None
    if not isinstance(entries, list) or len(entries) != 1:
        _not_ready()
    item = entries[0]
    raw = item.get("Subnet") if isinstance(item, dict) else None
    try:
        network = ipaddress.IPv4Network(raw)
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, TypeError):
        _not_ready()
    if str(network) != raw:
        _not_ready()
    return network


def _check_endpoints(
    record: dict[str, Any], networks: dict[str, dict[str, Any]]
) -> None:
    settings = record.get("NetworkSettings")
    attachments = settings.get("Networks") if isinstance(settings, dict) else None
    container_id = record.get("Id")
    if not isinstance(container_id, str) or _HEX64.fullmatch(container_id) is None:
        _not_ready()
    if not isinstance(attachments, dict):
        _not_ready()
    for name, attachment in attachments.items():
        network = networks.get(name)
        if not isinstance(network, dict) or not isinstance(attachment, dict):
            _not_ready()
        endpoints = network.get("Containers")
        endpoint = endpoints.get(container_id) if isinstance(endpoints, dict) else None
        if not isinstance(endpoint, dict):
            _not_ready()
        subnet = _subnet(network)
        try:
            address = ipaddress.IPv4Address(attachment.get("IPAddress"))
            registered = ipaddress.IPv4Interface(endpoint.get("IPv4Address"))
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, TypeError):
            _not_ready()
        if (
            attachment.get("NetworkID") != network.get("Id")
            or not isinstance(attachment.get("EndpointID"), str)
            or _HEX64.fullmatch(attachment["EndpointID"]) is None
            or endpoint.get("EndpointID") != attachment["EndpointID"]
            or registered.ip != address
            or registered.network != subnet
            or address not in subnet
            or address in (subnet.network_address, subnet.broadcast_address)
            or attachment.get("GlobalIPv6Address") not in (None, "")
            or endpoint.get("IPv6Address") not in (None, "")
        ):
            _not_ready()


def _check_probe(
    probe: dict[str, Any],
    image: dict[str, Any],
    backend: dict[str, Any],
    *,
    expected_probe_id: str,
    run_id: str,
    public_name: str,
    public_id: str,
    frontend_name: str,
) -> None:
    config = probe.get("Config")
    image_config = image.get("Config")
    host = probe.get("HostConfig")
    state = probe.get("State")
    network_settings = probe.get("NetworkSettings")
    if not all(
        isinstance(value, dict)
        for value in (config, image_config, host, state, network_settings)
    ):
        _not_ready()
    labels = config.get("Labels")
    ports = network_settings.get("Ports")
    health = config.get("Healthcheck")
    if (
        probe.get("Id") != expected_probe_id
        or _HEX64.fullmatch(expected_probe_id) is None
        or _HEX64.fullmatch(run_id) is None
        or not isinstance(labels, dict)
        or labels.get("org.university.audit.run") != run_id
        or labels.get("org.university.audit.purpose") != "aud164-167-client-ip-probe"
        or any(str(key).startswith("com.docker.compose.") for key in labels)
        or not isinstance(image.get("Id"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]) is None
        or image.get("Id") != backend.get("Image")
        or probe.get("Image") != image.get("Id")
        or config.get("Image") != image.get("Id")
        or image_config.get("User") != "10001:10001"
        or config.get("User") != "10001:10001"
        or image_config.get("Volumes") not in (None, {})
        or not isinstance(image_config.get("Env"), list)
        or config.get("Env") != image_config.get("Env")
        or config.get("Entrypoint") != ["python"]
        or config.get("Cmd") != ["-"]
        or config.get("OpenStdin") is not True
        or not isinstance(health, dict)
        or health.get("Test") != ["NONE"]
        or state.get("Running") is not True
        or state.get("Status") != "running"
        or probe.get("RestartCount") != 0
        or probe.get("Mounts") != []
        or host.get("Binds") not in (None, [])
        or host.get("Mounts") not in (None, [])
        or host.get("Tmpfs") not in (None, {})
        or any(
            key not in host or host[key] not in (None, [])
            for key in ("Devices", "DeviceRequests", "DeviceCgroupRules", "GroupAdd")
        )
        or host.get("PortBindings") not in (None, {})
        or host.get("PublishAllPorts") is not False
        or host.get("ReadonlyRootfs") is not True
        or host.get("Privileged") is not False
        or host.get("CapAdd") not in (None, [])
        or host.get("CapDrop") != ["ALL"]
        or host.get("SecurityOpt") != ["no-new-privileges:true"]
        or host.get("NetworkMode") not in (public_name, public_id)
        or host.get("PidMode") not in (None, "")
        or host.get("IpcMode") not in (None, "")
        or host.get("AutoRemove") is not False
        or host.get("RestartPolicy") != {"Name": "no", "MaximumRetryCount": 0}
        or (
            ports is not None
            and (
                not isinstance(ports, dict)
                or any(
                    not isinstance(key, str) or value not in (None, [])
                    for key, value in ports.items()
                )
            )
        )
        or not isinstance(network_settings.get("Networks"), dict)
        or set(network_settings["Networks"]) != {public_name, frontend_name}
    ):
        _not_ready()
    for key, maximum in (
        ("NanoCpus", 1_000_000_000),
        ("Memory", 256 * 1024 * 1024),
        ("PidsLimit", 64),
    ):
        value = host.get(key)
        if type(value) is not int or not 0 < value <= maximum:
            _not_ready()
    if host.get("MemorySwap") != host.get("Memory"):
        _not_ready()


def derive_probe_input(
    owner: live_stand.StandOwner,
    evidence: live_stand.ComposeResourceEvidence,
    containers: dict[str, dict[str, Any]],
    networks: dict[str, dict[str, Any]],
    probe: dict[str, Any],
    image: dict[str, Any],
    *,
    expected_probe_id: str,
    run_id: str,
) -> dict[str, object]:
    """Derive the producer input from mutually consistent private records."""
    try:
        if (
            type(owner) is not live_stand.StandOwner
            or type(evidence) is not live_stand.ComposeResourceEvidence
            or owner.stack != live_stand.LIVE_STACK_CORE
            or owner.schema_version != live_stand.IN_PLACE_OWNER_SCHEMA_VERSION
            or owner.service_roots != live_stand.LIVE_CORE_SERVICE_ROOTS
            or owner.selected_services != live_stand.LIVE_CORE_EXPECTED_SERVICES
            or evidence.managed_services != live_stand.LIVE_CORE_EXPECTED_SERVICES
            or owner.source_sha is None
            or owner.compose_resource_fingerprint != evidence.fingerprint
            or type(containers) is not dict
            or type(networks) is not dict
            or type(probe) is not dict
            or type(image) is not dict
            or type(expected_probe_id) is not str
            or type(run_id) is not str
        ):
            _not_ready()
        settings, addresses = live_stand._trusted_proxy_settings_from_inspects(
            owner, evidence, containers, networks
        )
        bindings = {
            key: (name, external) for key, name, external in evidence.network_bindings
        }
        logical = ("public", "frontend_net", "internal", "revocation_net")
        if any(name not in bindings or bindings[name][1] for name in logical):
            _not_ready()
        names = {name: bindings[name][0] for name in logical}
        if set(networks) != set(names.values()):
            _not_ready()
        for record in (*containers.values(), probe):
            _check_endpoints(record, networks)

        expected_env = {
            "backend": ("TRUSTED_PROXIES", "TRUSTED_PROXIES"),
            "gateway": ("GATEWAY_TRUSTED_PROXIES", "GATEWAY_TRUSTED_PROXIES"),
            "ws-hub": ("TRUSTED_PROXIES", "WS_HUB_TRUSTED_PROXIES"),
        }
        for service, (variable, setting) in expected_env.items():
            if _environment(containers[service]).get(variable) != ",".join(
                settings[setting]
            ):
                _not_ready()
        backend_env = _environment(containers["backend"])
        if (
            containers["backend"]["Config"].get("Cmd") != list(_BACKEND_COMMAND)
            or containers["backend"]["Config"].get("Entrypoint")
            != ["/usr/bin/tini", "--"]
            or containers["backend"]["Config"].get("WorkingDir") != "/app"
            or "GUNICORN_CMD_ARGS" in backend_env
            or "PYTHONPATH" in backend_env
            or "PYTHONHOME" in backend_env
            or backend_env.get("FORWARDED_ALLOW_IPS", "127.0.0.1,::1")
            != "127.0.0.1,::1"
        ):
            _not_ready()

        _check_probe(
            probe,
            image,
            containers["backend"],
            expected_probe_id=expected_probe_id,
            run_id=run_id,
            public_name=names["public"],
            public_id=networks[names["public"]]["Id"],
            frontend_name=names["frontend_net"],
        )

        def address(service: str, network: str) -> str:
            values = addresses[service][network]
            if len(values) != 1:
                _not_ready()
            return values[0]

        def row(network: str, source: str, caddy: str) -> dict[str, str]:
            record = networks[names[network]]
            return {
                "network": network,
                "network_id": record["Id"],
                "subnet": str(_subnet(record)),
                "source_ip": source,
                "caddy_ip": caddy,
            }

        attachments = probe["NetworkSettings"]["Networks"]
        result: dict[str, object] = {
            "schema": "ue-owned-client-ip-probe-input-v2",
            "source_sha": owner.source_sha,
            "run_id": run_id,
            "routes": [
                row(name, attachments[names[name]]["IPAddress"], address("caddy", name))
                for name in ("public", "frontend_net")
            ],
            "gateway_ip": address("gateway", "public"),
            "ws_hub_ip": address("ws-hub", "public"),
            "backend_public_ip": address("backend", "public"),
            "gateway_backend_peers": [
                {
                    "network": name,
                    "network_id": networks[names[name]]["Id"],
                    "subnet": str(_subnet(networks[names[name]])),
                    "address": address("gateway", name),
                }
                for name in ("public", "internal", "revocation_net")
            ],
            "trusted_proxies": [
                list(settings[name]) for name in live_stand.LIVE_TRUSTED_PROXY_SETTINGS
            ],
        }
        owned_client_ip_probe.parse_input(result)
        return result
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        live_stand.StandError,
        owned_client_ip_probe.ProbeError,
    ):
        _not_ready()


@dataclass(frozen=True, slots=True, repr=False)
class _TopologyWitness:
    digest: bytes


def freeze_topology_witness(snapshot: object) -> object:
    """Take a defensive private witness; it is not an ownership attestation."""
    try:
        if type(snapshot) is not dict or snapshot.keys() != _SNAPSHOT_KEYS:
            _not_ready()
        if (
            type(snapshot["owner"]) is not live_stand.StandOwner
            or type(snapshot["evidence"]) is not live_stand.ComposeResourceEvidence
        ):
            _not_ready()
        data = {
            **snapshot,
            "owner": asdict(snapshot["owner"]),
            "evidence": asdict(snapshot["evidence"]),
        }
        encoded = json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(encoded) > 1_048_576:
            _not_ready()
        return _TopologyWitness(
            hmac.new(_WITNESS_KEY, encoded, hashlib.sha256).digest()
        )
    except (AttributeError, TypeError, ValueError, UnicodeError, RecursionError):
        _not_ready()


def assert_topology_unchanged(before: object, after: object) -> None:
    """Compare two same-phase immutable witnesses without exposing their data."""
    if type(before) is not _TopologyWitness or type(after) is not _TopologyWitness:
        _not_ready()
    if not hmac.compare_digest(before.digest, after.digest):
        _not_ready()
