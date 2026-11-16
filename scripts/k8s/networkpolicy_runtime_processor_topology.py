"""Optional, sanitized control-plane snapshots for the real processor phase.

These reads issue no workload requests and do not establish packet translation or
NetworkPolicy verdicts. Missing or inconsistent data remains inconclusive.
"""

from __future__ import annotations

import datetime
import ipaddress
import json
import re
from collections.abc import Callable
from typing import Any

import yaml
from networkpolicy_runtime_kube import Pod, run_command

_UID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_NAME = re.compile(r"[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?\Z")


def _get(command_runner: Callable[..., Any], *args: str) -> dict[str, Any]:
    result = command_runner(["kubectl", *args], timeout=5)
    obj = json.loads(result.stdout)
    if not isinstance(obj, dict):
        raise ValueError("non-object Kubernetes response")
    return obj


def _valid_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 253
        and _NAME.fullmatch(value) is not None
    )


def _valid_uid(value: Any) -> bool:
    return isinstance(value, str) and _UID.fullmatch(value) is not None


def _address(value: Any) -> str:
    return str(ipaddress.ip_address(value))


def _pod(
    read: Callable[..., dict[str, Any]],
    release: str,
    name: str,
    uid: str,
    address: str,
    selector: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    obj = read("-n", release, "get", "pod", name, "-o", "json")
    meta, spec, status = obj["metadata"], obj["spec"], obj["status"]
    node = spec["nodeName"]
    labels = meta.get("labels", {})
    readiness = [
        condition.get("status")
        for condition in status.get("conditions", [])
        if condition.get("type") == "Ready"
    ]
    if (
        not _valid_name(name)
        or not _valid_uid(uid)
        or not _valid_name(node)
        or meta.get("deletionTimestamp") is not None
        or readiness != ["True"]
        or (meta.get("namespace"), meta.get("name"), meta.get("uid"))
        != (release, name, uid)
        or _address(status.get("podIP")) != _address(address)
        or not all(labels.get(k) == v for k, v in selector.items())
    ):
        raise ValueError("pod identity mismatch")
    return {"name": name, "uid": uid, "ip": _address(address), "node": node}, status


def _service(
    read: Callable[..., dict[str, Any]],
    release: str,
    name: str,
    selector: dict[str, str],
    target: dict[str, Any],
    port: int,
    port_name: str | None,
    target_port: int | str,
) -> dict[str, Any]:
    obj = read("-n", release, "get", "service", name, "-o", "json")
    meta, spec = obj["metadata"], obj["spec"]
    ports = spec.get("ports", [])
    if (
        (meta.get("namespace"), meta.get("name")) != (release, name)
        or not _valid_uid(meta.get("uid"))
        or meta.get("deletionTimestamp") is not None
        or spec.get("publishNotReadyAddresses", False) is not False
        or spec.get("selector") != selector
        or len(ports) != 1
        or ports[0].get("port") != port
        or ports[0].get("name")
        not in ((None, "") if port_name is None else (port_name,))
        or ports[0].get("protocol", "TCP") != "TCP"
        or ports[0].get("targetPort", port) != target_port
    ):
        raise ValueError("service identity mismatch")
    cluster_ip = _address(spec.get("clusterIP"))
    slices = read(
        "-n",
        release,
        "get",
        "endpointslices",
        "-l",
        f"kubernetes.io/service-name={name}",
        "-o",
        "json",
    )["items"]
    if not isinstance(slices, list) or not slices:
        raise ValueError("missing EndpointSlice")
    slice_uids = []
    endpoints = 0
    for item in slices:
        smeta = item["metadata"]
        sports = item.get("ports") or []
        matches = [
            owner
            for owner in smeta.get("ownerReferences", [])
            if owner.get("kind") == "Service"
            and owner.get("apiVersion") == "v1"
            and owner.get("name") == name
            and owner.get("uid") == meta["uid"]
            and owner.get("controller") is True
        ]
        if (
            smeta.get("namespace") != release
            or not _valid_uid(smeta.get("uid"))
            or smeta.get("deletionTimestamp") is not None
            or smeta.get("labels", {}).get("kubernetes.io/service-name") != name
            or len(matches) != 1
            or item.get("addressType")
            != ("IPv4" if ipaddress.ip_address(target["ip"]).version == 4 else "IPv6")
            or len(sports) != 1
            or sports[0].get("port") != port
            or sports[0].get("name")
            not in ((None, "") if port_name is None else (port_name,))
            or sports[0].get("protocol", "TCP") != "TCP"
            or not isinstance(item.get("endpoints"), list)
            or not item["endpoints"]
        ):
            raise ValueError("EndpointSlice identity mismatch")
        slice_uids.append(smeta["uid"])
        for endpoint in item.get("endpoints", []):
            ref = endpoint["targetRef"]
            conditions = endpoint.get("conditions", {})
            if (
                (ref.get("kind"), ref.get("namespace"), ref.get("name"), ref.get("uid"))
                != ("Pod", release, target["name"], target["uid"])
                or endpoint.get("addresses") != [target["ip"]]
                or conditions.get("ready") is not True
                or conditions.get("serving") is False
                or conditions.get("terminating") is True
            ):
                raise ValueError("endpoint identity mismatch")
            endpoints += 1
    if endpoints != 1 or len(set(slice_uids)) != len(slice_uids):
        raise ValueError("ambiguous endpoints")
    return {
        "name": name,
        "uid": meta["uid"],
        "cluster_ip": cluster_ip,
        "port": port,
        "selector": selector,
        "slice_uids": sorted(slice_uids),
        "target_uid": target["uid"],
        "target_ip": target["ip"],
    }


def _networks(values: Any) -> list[str] | None:
    if not isinstance(values, list) or not values:
        return None
    try:
        return sorted(
            {str(ipaddress.ip_network(value, strict=True)) for value in values}
        )
    except (TypeError, ValueError):
        return None


def _cidrs(read: Callable[..., dict[str, Any]], nodes: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"pod": None, "service": None, "nodes": {}}
    for name in sorted(nodes):
        try:
            node = read("get", "node", name, "-o", "json")
            if node["metadata"].get("name") != name or not _valid_uid(
                node["metadata"].get("uid")
            ):
                raise ValueError("node identity mismatch")
            spec = node.get("spec", {})
            values = spec.get("podCIDRs") or (
                [spec["podCIDR"]] if spec.get("podCIDR") else []
            )
            result["nodes"][name] = {
                "uid": node["metadata"]["uid"],
                "pod": _networks(values),
            }
        except Exception:
            result["nodes"][name] = {"uid": None, "pod": None}
    try:
        data = read("get", "servicecidrs.networking.k8s.io", "-o", "json")
        result["service"] = _networks(
            [cidr for item in data["items"] for cidr in item["spec"]["cidrs"]]
        )
    except Exception:
        result["service"] = None
    try:
        config = read(
            "-n", "kube-system", "get", "configmap", "kubeadm-config", "-o", "json"
        )
        parsed = yaml.safe_load(config["data"]["ClusterConfiguration"])
        value = parsed["networking"]["podSubnet"]
        result["pod"] = _networks([part.strip() for part in value.split(",")])
    except Exception:
        result["pod"] = None
    return result


def capture_topology(
    release: str,
    fixture: Any,
    pods: dict[str, Pod],
    replicas: list[dict[str, Any]],
    *,
    command_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Read only this phase's two processor pods and their positive dependencies."""
    try:

        def read(*args: str) -> dict[str, Any]:
            return _get(command_runner or run_command, *args)

        if (
            release != "probe-a"
            or fixture.jwks_hostname != "probe-a-backend"
            or len(replicas) != 2
        ):
            raise ValueError("unexpected processor scope")
        if any(
            not _valid_name(replica["name"]) or not _valid_uid(replica["uid"])
            for replica in replicas
        ):
            raise ValueError("invalid processor identity")
        for replica in replicas:
            _address(replica["ip"])
        selector = fixture.deployment["spec"]["selector"]["matchLabels"]
        if not isinstance(selector, dict) or not selector:
            raise ValueError("missing processor selector")
        sources = []
        for replica in replicas:
            source, status = _pod(
                read, release, replica["name"], replica["uid"], replica["ip"], selector
            )
            containers = [
                s
                for s in status.get("containerStatuses", [])
                if s.get("name") == "file-processor"
            ]
            if len(containers) != 1 or (
                containers[0].get("ready") is not True
                or containers[0].get("containerID") != replica["container_id"]
                or containers[0].get("imageID") != replica["image_id"]
                or containers[0].get("restartCount") != replica["restarts"]
            ):
                raise ValueError("processor container changed")
            sources.append(source)
        if any(
            len({source[key] for source in sources}) != 2
            for key in ("name", "uid", "ip")
        ):
            raise ValueError("ambiguous processor replicas")
        redis_selector = {
            "app.kubernetes.io/instance": release,
            "app.kubernetes.io/name": "revocation-redis",
            "app.kubernetes.io/component": "master",
        }
        backend_selector = {"probe-role": "a-backend"}
        targets = {}
        for kind, pod, expected_name, labels in (
            (
                "redis",
                pods["a-redis"],
                "probe-a-revocation-redis-master-0",
                redis_selector,
            ),
            ("jwks", pods["a-backend"], "probe-a-backend", backend_selector),
        ):
            if (pod.namespace, pod.name) != (release, expected_name):
                raise ValueError("unexpected dependency pod")
            targets[kind], _ = _pod(read, release, pod.name, pod.uid, pod.ip, labels)
        services = {
            "redis": _service(
                read,
                release,
                "probe-a-revocation-redis-master",
                redis_selector,
                targets["redis"],
                6379,
                "tcp-redis",
                "redis",
            ),
            "jwks": _service(
                read,
                release,
                fixture.jwks_hostname,
                backend_selector,
                targets["jwks"],
                8000,
                None,
                8000,
            ),
        }
        node_names = {pod["node"] for pod in [*sources, *targets.values()]}
        return {
            "status": "available",
            "sampled_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            "processors": sorted(sources, key=lambda source: source["uid"]),
            "targets": targets,
            "services": services,
            "cidrs": _cidrs(read, node_names),
        }
    except (Exception, SystemExit):
        # This optional observation must not replace existing application results.
        return {"status": "unavailable"}


def compare_topology(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare sampled identities; never claim continuous state or CNI verdicts."""
    result: dict[str, Any] = {
        "verdict": "inconclusive",
        "scope": "sampled positive service and endpoint bindings",
        "before": before,
        "after": after,
    }
    if before.get("status") != "available" or after.get("status") != "available":
        result["reason"] = "snapshot-unavailable"
    elif any(
        before.get(key) != after.get(key)
        for key in ("processors", "targets", "services", "cidrs")
    ):
        result["reason"] = "snapshot-changed"
    elif (
        before["cidrs"]["pod"] is None
        or before["cidrs"]["service"] is None
        or any(node["pod"] is None for node in before["cidrs"]["nodes"].values())
    ):
        result["reason"] = "cidr-unavailable"
    elif any(
        not any(
            ipaddress.ip_address(service["cluster_ip"]) in ipaddress.ip_network(cidr)
            for cidr in before["cidrs"]["service"]
        )
        for service in before["services"].values()
    ):
        result["reason"] = "service-cidr-mismatch"
    elif any(
        not any(
            ipaddress.ip_address(pod["ip"]) in ipaddress.ip_network(cidr)
            for cidr in before["cidrs"]["pod"]
        )
        for pod in [*before["processors"], *before["targets"].values()]
    ):
        result["reason"] = "configured-pod-cidr-mismatch"
    else:
        result["verdict"] = "pass"
    return result
