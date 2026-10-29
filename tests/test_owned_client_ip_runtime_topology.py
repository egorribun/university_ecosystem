"""Outer client-IP adapter contracts over synthetic Docker inspect records.

These records are controlled test inputs, not an attestation of a Docker
daemon, an owned stand, or a deployed network. The caller must authenticate
and recheck the real inventory under its own lease.
"""

from __future__ import annotations

import copy
import importlib
import secrets
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from scripts import live_stand, owned_client_ip_probe
from scripts.owned_client_ip_acceptance import _BACKEND_COMMAND
from tests.test_live_stand_core_selection import _trusted_proxy_topology


@pytest.fixture
def runtime():
    return importlib.import_module("scripts.owned_client_ip_runtime")


def _inspect_fixture():
    owner, evidence, containers, networks = _trusted_proxy_topology()
    project = owner.project_name
    public = f"{project}_public"
    frontend = f"{project}_frontend_net"
    owner = replace(
        owner,
        stack=live_stand.LIVE_STACK_CORE,
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )

    public_record = networks.pop("shared-public")
    public_record["Name"] = public
    public_record["Labels"] = {
        "com.docker.compose.project": project,
        "com.docker.compose.network": "public",
    }
    networks[public] = public_record
    for record in containers.values():
        attachments = record["NetworkSettings"]["Networks"]
        attachments[public] = attachments.pop("shared-public")

    frontend_id = secrets.token_hex(32)
    networks[frontend] = {
        "Name": frontend,
        "Id": frontend_id,
        "Labels": {
            "com.docker.compose.project": project,
            "com.docker.compose.network": "frontend_net",
        },
        "IPAM": {"Config": [{"Subnet": "172.31.0.0/24"}]},
    }
    for service, host in (("caddy", 2), ("backend", 3)):
        containers[service]["NetworkSettings"]["Networks"][frontend] = {
            "NetworkID": frontend_id,
            "IPAddress": f"172.31.0.{host}",
            "GlobalIPv6Address": "",
        }

    bindings = (
        *(
            (key, public if key == "public" else name, False)
            for key, name, _external in evidence.network_bindings
        ),
        ("frontend_net", frontend, False),
        ("published_ports", f"{project}_published_ports", False),
        ("alloy_docker_api", f"{project}_alloy_docker_api", False),
    )
    service_network_map = {
        "backend": ("frontend_net", "internal", "public", "revocation_net"),
        "caddy": ("frontend_net", "public"),
        "flagd": ("internal",),
        "flagd-healthprobe": (),
        "frontend": ("frontend_net",),
        "gateway": ("internal", "public", "revocation_net"),
        "imgproxy": ("internal", "public"),
        "mailpit": ("internal", "public"),
        "migrations": ("internal", "revocation_net"),
        "minio": ("internal", "public"),
        "minio-init": ("internal",),
        "nats": ("internal",),
        "notifications-worker": ("internal",),
        "outbox-worker": ("internal",),
        "postgres": ("internal", "published_ports"),
        "postgres-databases-init": ("internal",),
        "redis": ("internal",),
        "revocation-redis": ("revocation_net",),
        "spicedb": ("internal",),
        "spicedb-migrate": ("internal",),
        "tempo": ("internal",),
        "tempo-healthprobe": (),
        "ws-hub": ("internal", "public", "revocation_net"),
    }
    assert set(service_network_map) == set(owner.selected_services)
    service_networks = tuple(sorted(service_network_map.items()))
    evidence = replace(
        evidence,
        stack=owner.stack,
        service_roots=owner.service_roots,
        selected_services=owner.selected_services,
        managed_services=owner.selected_services,
        managed_networks=tuple((key, name) for key, name, _ in bindings),
        network_bindings=bindings,
        service_networks=service_networks,
    )

    backend_trust = "172.28.0.2,172.28.0.4,172.29.0.4,172.30.0.4,172.31.0.2"
    backend_marker = secrets.token_urlsafe(24)
    containers["backend"]["Config"]["Cmd"] = list(_BACKEND_COMMAND)
    containers["backend"]["Config"]["Entrypoint"] = ["/usr/bin/tini", "--"]
    containers["backend"]["Config"]["WorkingDir"] = "/app"
    containers["backend"]["Config"]["Env"] = [
        f"TRUSTED_PROXIES={backend_trust}",
        f"BACKEND_RUNTIME_MARKER={backend_marker}",
    ]
    containers["gateway"]["Config"]["Env"] = ["GATEWAY_TRUSTED_PROXIES=172.28.0.2"]
    containers["ws-hub"]["Config"]["Env"] = ["TRUSTED_PROXIES=172.28.0.2"]
    for record in containers.values():
        record["RestartCount"] = 0

    run_id = secrets.token_hex(32)
    probe_id = secrets.token_hex(32)
    image_id = containers["backend"]["Image"]
    image_env = ["PATH=/opt/venv/bin:/usr/bin:/bin", "PYTHONUNBUFFERED=1"]
    image = {
        "Id": image_id,
        "Config": {"User": "10001:10001", "Volumes": {}, "Env": image_env.copy()},
    }
    probe = {
        "Id": probe_id,
        "Image": image_id,
        "Name": "/owned-client-ip-probe",
        "RestartCount": 0,
        "Config": {
            "Image": image_id,
            "User": "10001:10001",
            "Env": image_env.copy(),
            "Entrypoint": ["python"],
            "Cmd": ["-"],
            "OpenStdin": True,
            "Healthcheck": {"Test": ["NONE"]},
            "Labels": {
                "org.university.audit.run": run_id,
                "org.university.audit.purpose": "aud164-167-client-ip-probe",
            },
        },
        "State": {"Running": True, "Status": "running"},
        "Mounts": [],
        "HostConfig": {
            "NetworkMode": public,
            "ReadonlyRootfs": True,
            "Privileged": False,
            "AutoRemove": False,
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "Binds": None,
            "Tmpfs": None,
            "Mounts": None,
            "Devices": [],
            "DeviceRequests": None,
            "DeviceCgroupRules": None,
            "GroupAdd": None,
            "PortBindings": {},
            "PublishAllPorts": False,
            "CapAdd": None,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "NanoCpus": 1_000_000_000,
            "Memory": 256 * 1024 * 1024,
            "MemorySwap": 256 * 1024 * 1024,
            "PidsLimit": 64,
            "PidMode": "",
            "IpcMode": "",
        },
        "NetworkSettings": {
            "Ports": {},
            "Networks": {
                public: {
                    "NetworkID": networks[public]["Id"],
                    "IPAddress": "172.28.0.10",
                    "GlobalIPv6Address": "",
                },
                frontend: {
                    "NetworkID": networks[frontend]["Id"],
                    "IPAddress": "172.31.0.10",
                    "GlobalIPv6Address": "",
                },
            },
        },
    }
    for network in networks.values():
        network["Containers"] = {}
    for service, record in [*containers.items(), ("probe", probe)]:
        for name, attachment in record["NetworkSettings"]["Networks"].items():
            endpoint_id = secrets.token_hex(32)
            attachment["EndpointID"] = endpoint_id
            networks[name]["Containers"][record["Id"]] = {
                "Name": service,
                "EndpointID": endpoint_id,
                "IPv4Address": f"{attachment['IPAddress']}/24",
                "IPv6Address": "",
            }

    return {
        "owner": owner,
        "evidence": evidence,
        "containers": containers,
        "networks": networks,
        "probe": probe,
        "image": image,
        "expected_probe_id": probe_id,
        "run_id": run_id,
    }, backend_marker


def _derive(runtime, snapshot):
    return runtime.derive_probe_input(
        snapshot["owner"],
        snapshot["evidence"],
        snapshot["containers"],
        snapshot["networks"],
        snapshot["probe"],
        snapshot["image"],
        expected_probe_id=snapshot["expected_probe_id"],
        run_id=snapshot["run_id"],
    )


def _expected_input(snapshot):
    project = snapshot["owner"].project_name
    networks = snapshot["networks"]
    names = {
        name: f"{project}_{name}"
        for name in ("public", "frontend_net", "internal", "revocation_net")
    }
    return {
        "schema": "ue-owned-client-ip-probe-input-v2",
        "source_sha": snapshot["owner"].source_sha,
        "run_id": snapshot["run_id"],
        "routes": [
            {
                "network": "public",
                "network_id": networks[names["public"]]["Id"],
                "subnet": "172.28.0.0/24",
                "source_ip": "172.28.0.10",
                "caddy_ip": "172.28.0.2",
            },
            {
                "network": "frontend_net",
                "network_id": networks[names["frontend_net"]]["Id"],
                "subnet": "172.31.0.0/24",
                "source_ip": "172.31.0.10",
                "caddy_ip": "172.31.0.2",
            },
        ],
        "gateway_ip": "172.28.0.4",
        "ws_hub_ip": "172.28.0.5",
        "backend_public_ip": "172.28.0.3",
        "gateway_backend_peers": [
            {
                "network": key,
                "network_id": networks[names[key]]["Id"],
                "subnet": subnet,
                "address": address,
            }
            for key, subnet, address in (
                ("public", "172.28.0.0/24", "172.28.0.4"),
                ("internal", "172.29.0.0/24", "172.29.0.4"),
                ("revocation_net", "172.30.0.0/24", "172.30.0.4"),
            )
        ],
        "trusted_proxies": [
            ["172.28.0.2", "172.28.0.4", "172.29.0.4", "172.30.0.4", "172.31.0.2"],
            ["172.28.0.2"],
            ["172.28.0.2"],
        ],
    }


def test_synthetic_core_fixture_matches_current_proxy_and_producer_contracts():
    snapshot, _ = _inspect_fixture()
    settings, _ = live_stand._trusted_proxy_settings_from_inspects(
        snapshot["owner"],
        snapshot["evidence"],
        snapshot["containers"],
        snapshot["networks"],
    )
    expected = _expected_input(snapshot)
    assert [
        list(settings["TRUSTED_PROXIES"]),
        list(settings["GATEWAY_TRUSTED_PROXIES"]),
        list(settings["WS_HUB_TRUSTED_PROXIES"]),
    ] == expected["trusted_proxies"]
    assert owned_client_ip_probe.parse_input(expected).run_id == snapshot["run_id"]


def test_derive_uses_signed_inspects_and_emits_exact_producer_v2(runtime, monkeypatch):
    snapshot, marker = _inspect_fixture()
    spy = MagicMock(wraps=live_stand._trusted_proxy_settings_from_inspects)
    monkeypatch.setattr(live_stand, "_trusted_proxy_settings_from_inspects", spy)

    result = _derive(runtime, snapshot)

    assert result == _expected_input(snapshot)
    spy.assert_any_call(
        snapshot["owner"],
        snapshot["evidence"],
        snapshot["containers"],
        snapshot["networks"],
    )
    assert owned_client_ip_probe.parse_input(result).run_id == snapshot["run_id"]
    assert marker not in repr(result)


def test_consistent_changed_probe_endpoint_is_derived_from_both_inspects(runtime):
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    public = f"{snapshot['owner'].project_name}_public"
    snapshot["probe"]["NetworkSettings"]["Networks"][public]["IPAddress"] = (
        "172.28.0.11"
    )
    snapshot["networks"][public]["Containers"][snapshot["expected_probe_id"]][
        "IPv4Address"
    ] = "172.28.0.11/24"

    result = _derive(runtime, snapshot)

    assert result["routes"][0]["source_ip"] == "172.28.0.11"
    owned_client_ip_probe.parse_input(result)


def test_unbound_declared_port_is_not_a_published_probe_port(runtime):
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    snapshot["probe"]["NetworkSettings"]["Ports"] = {"8000/tcp": None}
    assert _derive(runtime, snapshot) == _expected_input(snapshot)


@pytest.mark.parametrize(
    "defect",
    [
        "probe_id",
        "expected_id",
        "run_label",
        "purpose_label",
        "resource_fingerprint",
        "incomplete_core_closure",
        "incomplete_core_roots",
        "managed_core_drift",
        "owner_schema_version",
        "image_id",
        "backend_image_id",
        "same_tag_in_place_of_image_id",
        "image_volumes",
        "probe_executable",
        "probe_argument",
        "probe_closed_stdin",
        "probe_auto_remove",
        "probe_auto_restart",
        "enabled_healthcheck",
        "missing_healthcheck",
        "source_attachment_spoof",
        "source_network_inspect_spoof",
        "source_endpoint_prefix",
        "probe_endpoint_id_mismatch",
        "missing_probe_endpoint",
        "caddy_endpoint_spoof",
        "gateway_endpoint_spoof",
        "backend_endpoint_spoof",
        "attachment_network_id",
        "inspected_network_id",
        "missing_probe_network",
        "extra_probe_network",
        "outside_network",
        "bad_ipam",
        "ambiguous_ipam",
        "foreign_network_label",
        "external_public",
        "external_frontend_net",
        "external_internal",
        "external_revocation_net",
        "unhealthy_backend",
        "foreign_service_label",
    ],
)
def test_mismatched_inspection_identity_or_endpoints_fail_closed(runtime, defect):
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    owner = snapshot["owner"]
    public = f"{owner.project_name}_public"
    frontend = f"{owner.project_name}_frontend_net"
    containers, networks, probe = (
        snapshot["containers"],
        snapshot["networks"],
        snapshot["probe"],
    )
    endpoint = networks[public]["Containers"][snapshot["expected_probe_id"]]

    if defect == "probe_id":
        probe["Id"] = secrets.token_hex(32)
    elif defect == "expected_id":
        snapshot["expected_probe_id"] = secrets.token_hex(32)
    elif defect == "run_label":
        probe["Config"]["Labels"]["org.university.audit.run"] = secrets.token_hex(32)
    elif defect == "purpose_label":
        probe["Config"]["Labels"]["org.university.audit.purpose"] = "other"
    elif defect == "resource_fingerprint":
        snapshot["evidence"] = replace(
            snapshot["evidence"], fingerprint=secrets.token_hex(32)
        )
    elif defect == "incomplete_core_closure":
        incomplete = tuple(
            service for service in owner.selected_services if service != "spicedb"
        )
        snapshot["owner"] = replace(owner, selected_services=incomplete)
        snapshot["evidence"] = replace(
            snapshot["evidence"],
            selected_services=incomplete,
            managed_services=incomplete,
        )
    elif defect == "incomplete_core_roots":
        incomplete = tuple(root for root in owner.service_roots if root != "spicedb")
        snapshot["owner"] = replace(owner, service_roots=incomplete)
        snapshot["evidence"] = replace(snapshot["evidence"], service_roots=incomplete)
    elif defect == "managed_core_drift":
        evidence = snapshot["evidence"]
        snapshot["evidence"] = replace(
            evidence,
            managed_services=tuple(
                service for service in evidence.managed_services if service != "spicedb"
            ),
        )
    elif defect == "owner_schema_version":
        snapshot["owner"] = replace(
            owner, schema_version=live_stand.OWNER_SCHEMA_VERSION
        )
    elif defect == "image_id":
        probe["Image"] = "sha256:" + secrets.token_hex(32)
    elif defect == "backend_image_id":
        containers["backend"]["Image"] = "sha256:" + secrets.token_hex(32)
    elif defect == "same_tag_in_place_of_image_id":
        tag = "example/backend:latest"
        containers["backend"]["Image"] = tag
        probe["Image"] = tag
        probe["Config"]["Image"] = tag
        snapshot["image"]["Id"] = tag
    elif defect == "image_volumes":
        snapshot["image"]["Config"]["Volumes"] = {"/probe-volume": {}}
    elif defect == "probe_executable":
        probe["Config"]["Entrypoint"] = ["sh"]
    elif defect == "probe_argument":
        probe["Config"]["Cmd"] = ["-c", "pass"]
    elif defect == "probe_closed_stdin":
        probe["Config"]["OpenStdin"] = False
    elif defect == "probe_auto_remove":
        probe["HostConfig"]["AutoRemove"] = True
    elif defect == "probe_auto_restart":
        probe["HostConfig"]["RestartPolicy"]["Name"] = "always"
    elif defect == "enabled_healthcheck":
        probe["Config"]["Healthcheck"] = {"Test": ["CMD", "python", "-V"]}
    elif defect == "missing_healthcheck":
        del probe["Config"]["Healthcheck"]
    elif defect == "source_attachment_spoof":
        probe["NetworkSettings"]["Networks"][public]["IPAddress"] = "172.28.0.11"
    elif defect == "source_network_inspect_spoof":
        endpoint["IPv4Address"] = "172.28.0.11/24"
    elif defect == "source_endpoint_prefix":
        endpoint["IPv4Address"] = "172.28.0.10/25"
    elif defect == "probe_endpoint_id_mismatch":
        endpoint["EndpointID"] = secrets.token_hex(32)
    elif defect == "missing_probe_endpoint":
        del networks[public]["Containers"][snapshot["expected_probe_id"]]
    elif defect == "caddy_endpoint_spoof":
        networks[public]["Containers"][containers["caddy"]["Id"]]["IPv4Address"] = (
            "172.28.0.12/24"
        )
    elif defect == "gateway_endpoint_spoof":
        networks[public]["Containers"][containers["gateway"]["Id"]]["IPv4Address"] = (
            "172.28.0.12/24"
        )
    elif defect == "backend_endpoint_spoof":
        networks[public]["Containers"][containers["backend"]["Id"]]["IPv4Address"] = (
            "172.28.0.12/24"
        )
    elif defect == "attachment_network_id":
        probe["NetworkSettings"]["Networks"][frontend]["NetworkID"] = secrets.token_hex(
            32
        )
    elif defect == "inspected_network_id":
        networks[frontend]["Id"] = secrets.token_hex(32)
    elif defect == "missing_probe_network":
        del probe["NetworkSettings"]["Networks"][frontend]
    elif defect == "extra_probe_network":
        probe["NetworkSettings"]["Networks"]["unexpected"] = {}
    elif defect == "outside_network":
        probe["NetworkSettings"]["Networks"][public]["IPAddress"] = "172.27.0.10"
        endpoint["IPv4Address"] = "172.27.0.10/24"
    elif defect == "bad_ipam":
        networks[public]["IPAM"]["Config"] = []
    elif defect == "ambiguous_ipam":
        networks[public]["IPAM"]["Config"].append({"Subnet": "172.28.1.0/24"})
    elif defect == "foreign_network_label":
        networks[frontend]["Labels"]["com.docker.compose.project"] = "foreign"
    elif defect.startswith("external_"):
        logical = defect.removeprefix("external_")
        evidence = snapshot["evidence"]
        snapshot["evidence"] = replace(
            evidence,
            network_bindings=tuple(
                (key, name, True if key == logical else external)
                for key, name, external in evidence.network_bindings
            ),
        )
    elif defect == "unhealthy_backend":
        containers["backend"]["State"]["Health"]["Status"] = "unhealthy"
    else:
        containers["gateway"]["Config"]["Labels"]["com.docker.compose.project"] = (
            "foreign"
        )

    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_backend_trust",
        "backend_extra_source_trust",
        "backend_trust_cidr",
        "duplicate_backend_trust",
        "gateway_trust",
        "ws_hub_trust",
        "duplicate_env_key",
        "different_backend_command",
        "different_backend_entrypoint",
        "different_backend_working_dir",
        "gunicorn_environment_override",
        "pythonpath_override",
        "pythonhome_override",
        "forwarded_allow_all",
        "forwarded_allow_cidr",
        "forwarded_allow_probe",
        "backend_env_in_probe",
    ],
)
def test_runtime_trust_and_worker_overrides_fail_closed(runtime, defect):
    snapshot, marker = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    containers = snapshot["containers"]
    backend_env = containers["backend"]["Config"]["Env"]
    if defect == "missing_backend_trust":
        backend_env.pop(0)
    elif defect == "backend_extra_source_trust":
        backend_env[0] += ",172.28.0.10"
    elif defect == "backend_trust_cidr":
        backend_env[0] += ",172.28.0.0/24"
    elif defect == "duplicate_backend_trust":
        backend_env[0] += ",172.28.0.2"
    elif defect == "gateway_trust":
        containers["gateway"]["Config"]["Env"][0] += ",172.31.0.10"
    elif defect == "ws_hub_trust":
        containers["ws-hub"]["Config"]["Env"][0] = "TRUSTED_PROXIES=*"
    elif defect == "duplicate_env_key":
        backend_env.append(backend_env[0])
    elif defect == "different_backend_command":
        containers["backend"]["Config"]["Cmd"] += ["--forwarded-allow-ips", "*"]
    elif defect == "different_backend_entrypoint":
        containers["backend"]["Config"]["Entrypoint"] = ["python"]
    elif defect == "different_backend_working_dir":
        containers["backend"]["Config"]["WorkingDir"] = "/other"
    elif defect == "gunicorn_environment_override":
        backend_env.append("GUNICORN_CMD_ARGS=--workers 1")
    elif defect == "pythonpath_override":
        backend_env.append("PYTHONPATH=/other")
    elif defect == "pythonhome_override":
        backend_env.append("PYTHONHOME=/other")
    elif defect == "forwarded_allow_all":
        backend_env.append("FORWARDED_ALLOW_IPS=*")
    elif defect == "forwarded_allow_cidr":
        backend_env.append("FORWARDED_ALLOW_IPS=0.0.0.0/0")
    elif defect == "forwarded_allow_probe":
        backend_env.append("FORWARDED_ALLOW_IPS=172.28.0.10")
    else:
        snapshot["probe"]["Config"]["Env"].append(f"BACKEND_RUNTIME_MARKER={marker}")

    with pytest.raises(runtime.RuntimeNotReady) as denied:
        _derive(runtime, snapshot)
    assert marker not in str(denied.value)


@pytest.mark.parametrize(
    "defect",
    [
        "root_user",
        "root_group",
        "writable_root",
        "privileged",
        "bind_mount",
        "host_mount",
        "runtime_tmpfs",
        "runtime_mounts",
        "host_devices",
        "host_device_requests",
        "host_device_rules",
        "host_supplemental_groups",
        "published_port",
        "probe_inspect_published_port",
        "publish_all_ports",
        "added_capability",
        "missing_drop_all",
        "missing_no_new_privileges",
        "host_network",
        "host_pid",
        "host_ipc",
        "unlimited_cpu",
        "excess_cpu",
        "unlimited_memory",
        "excess_memory",
        "unlimited_swap",
        "unlimited_pids",
        "excess_pids",
    ],
)
def test_probe_must_remain_isolated_and_resource_bounded(runtime, defect):
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    probe = snapshot["probe"]
    config, host = probe["Config"], probe["HostConfig"]
    if defect == "root_user":
        config["User"] = "0:10001"
    elif defect == "root_group":
        config["User"] = "10001:0"
    elif defect == "writable_root":
        host["ReadonlyRootfs"] = False
    elif defect == "privileged":
        host["Privileged"] = True
    elif defect == "bind_mount":
        host["Binds"] = ["/host:/probe:ro"]
    elif defect == "host_mount":
        probe["Mounts"] = [{"Type": "bind", "Source": "/host", "Destination": "/probe"}]
    elif defect == "runtime_tmpfs":
        host["Tmpfs"] = {"/scratch": "rw"}
    elif defect == "runtime_mounts":
        host["Mounts"] = [{"Type": "tmpfs", "Target": "/scratch"}]
    elif defect == "host_devices":
        host["Devices"] = [
            {
                "PathOnHost": "/dev/null",
                "PathInContainer": "/dev/null",
                "CgroupPermissions": "rwm",
            }
        ]
    elif defect == "host_device_requests":
        host["DeviceRequests"] = [{"Driver": "example", "Count": -1}]
    elif defect == "host_device_rules":
        host["DeviceCgroupRules"] = ["c 1:3 rwm"]
    elif defect == "host_supplemental_groups":
        host["GroupAdd"] = ["0"]
    elif defect == "published_port":
        host["PortBindings"] = {
            "8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]
        }
    elif defect == "probe_inspect_published_port":
        probe["NetworkSettings"]["Ports"] = {
            "8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]
        }
    elif defect == "publish_all_ports":
        host["PublishAllPorts"] = True
    elif defect == "added_capability":
        host["CapAdd"] = ["NET_ADMIN"]
    elif defect == "missing_drop_all":
        host["CapDrop"] = []
    elif defect == "missing_no_new_privileges":
        host["SecurityOpt"] = []
    elif defect == "host_network":
        host["NetworkMode"] = "host"
    elif defect == "host_pid":
        host["PidMode"] = "host"
    elif defect == "host_ipc":
        host["IpcMode"] = "host"
    elif defect == "unlimited_cpu":
        host["NanoCpus"] = 0
    elif defect == "excess_cpu":
        host["NanoCpus"] = 2_000_000_000
    elif defect == "unlimited_memory":
        host["Memory"] = 0
    elif defect == "excess_memory":
        host["Memory"] = 512 * 1024 * 1024
    elif defect == "unlimited_swap":
        host["MemorySwap"] = -1
    elif defect == "unlimited_pids":
        host["PidsLimit"] = 0
    else:
        host["PidsLimit"] = 65

    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


def test_extra_shared_signed_network_is_not_silently_omitted(runtime):
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    owner, evidence = snapshot["owner"], snapshot["evidence"]
    name = f"{owner.project_name}_extra"
    network_id = secrets.token_hex(32)
    snapshot["networks"][name] = {
        "Name": name,
        "Id": network_id,
        "Labels": {
            "com.docker.compose.project": owner.project_name,
            "com.docker.compose.network": "extra",
        },
        "IPAM": {"Config": [{"Subnet": "10.44.0.0/24"}]},
        "Containers": {},
    }
    for service, host in (("backend", 3), ("gateway", 4)):
        record = snapshot["containers"][service]
        endpoint_id = secrets.token_hex(32)
        address = f"10.44.0.{host}"
        record["NetworkSettings"]["Networks"][name] = {
            "NetworkID": network_id,
            "EndpointID": endpoint_id,
            "IPAddress": address,
            "GlobalIPv6Address": "",
        }
        snapshot["networks"][name]["Containers"][record["Id"]] = {
            "Name": service,
            "EndpointID": endpoint_id,
            "IPv4Address": f"{address}/24",
            "IPv6Address": "",
        }
    snapshot["evidence"] = replace(
        evidence,
        network_bindings=(*evidence.network_bindings, ("extra", name, False)),
        managed_networks=(*evidence.managed_networks, ("extra", name)),
        service_networks=tuple(
            (service, (*items, "extra") if service in {"backend", "gateway"} else items)
            for service, items in evidence.service_networks
        ),
    )
    settings, _ = live_stand._trusted_proxy_settings_from_inspects(
        owner, snapshot["evidence"], snapshot["containers"], snapshot["networks"]
    )
    snapshot["containers"]["backend"]["Config"]["Env"][0] = (
        "TRUSTED_PROXIES=" + ",".join(settings["TRUSTED_PROXIES"])
    )

    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


def test_frozen_witness_is_defensive_and_does_not_reveal_environment(runtime):
    snapshot, marker = _inspect_fixture()
    before = runtime.freeze_topology_witness(snapshot)
    same = runtime.freeze_topology_witness(copy.deepcopy(snapshot))
    runtime.assert_topology_unchanged(before, same)
    assert marker not in repr(before)
    snapshot["containers"]["backend"]["RestartCount"] += 1

    with pytest.raises(runtime.RuntimeNotReady):
        after = runtime.freeze_topology_witness(snapshot)
        runtime.assert_topology_unchanged(before, after)


@pytest.mark.parametrize(
    "defect",
    [
        "owner",
        "source_sha",
        "service_id",
        "service_image",
        "restart",
        "network_id",
        "ipam",
        "endpoint_set",
        "trust_env",
        "worker_command",
        "probe_id",
        "probe_image",
        "probe_config",
    ],
)
def test_frozen_witness_rejects_independent_runtime_drift(runtime, defect):
    snapshot, _ = _inspect_fixture()
    before = runtime.freeze_topology_witness(snapshot)
    changed = copy.deepcopy(snapshot)
    project = changed["owner"].project_name
    public = f"{project}_public"
    if defect == "owner":
        changed["owner"] = replace(
            changed["owner"], project_name="ue-live-" + secrets.token_hex(8)
        )
    elif defect == "source_sha":
        changed["owner"] = replace(changed["owner"], source_sha=secrets.token_hex(20))
    elif defect == "service_id":
        changed["containers"]["gateway"]["Id"] = secrets.token_hex(32)
    elif defect == "service_image":
        changed["containers"]["gateway"]["Image"] = "sha256:" + secrets.token_hex(32)
    elif defect == "restart":
        changed["containers"]["ws-hub"]["RestartCount"] += 1
    elif defect == "network_id":
        changed["networks"][public]["Id"] = secrets.token_hex(32)
    elif defect == "ipam":
        changed["networks"][public]["IPAM"]["Config"][0]["Subnet"] = "172.28.1.0/24"
    elif defect == "endpoint_set":
        changed["networks"][public]["Containers"][secrets.token_hex(32)] = {
            "IPv4Address": "172.28.0.20/24"
        }
    elif defect == "trust_env":
        changed["containers"]["backend"]["Config"]["Env"][0] += ",172.28.0.10"
    elif defect == "worker_command":
        changed["containers"]["backend"]["Config"]["Cmd"].append("--preload")
    elif defect == "probe_id":
        changed["probe"]["Id"] = secrets.token_hex(32)
    elif defect == "probe_image":
        changed["probe"]["Image"] = "sha256:" + secrets.token_hex(32)
    else:
        changed["probe"]["HostConfig"]["Privileged"] = True

    with pytest.raises(runtime.RuntimeNotReady):
        after = runtime.freeze_topology_witness(changed)
        runtime.assert_topology_unchanged(before, after)


def test_plain_mutable_snapshots_cannot_be_passed_as_frozen_witnesses(runtime):
    snapshot, _ = _inspect_fixture()
    with pytest.raises(runtime.RuntimeNotReady):
        runtime.assert_topology_unchanged(snapshot, copy.deepcopy(snapshot))
