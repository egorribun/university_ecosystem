"""Private, fail-closed server evidence for the AUD-373 no-client-SVID probe.

This collector never changes TLS enforcement. It uses the current authenticated
kubectl context, freezes the serving workload before the probe, and accepts only
one server-generated missing-certificate event from that unchanged workload.
Raw Kubernetes metadata belongs in the private work directory, never artifacts.
Only the finite summary produced by ``verify`` is safe for publication.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import selectors
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

MAX_BYTES = 1_048_576
MAX_LOG_BYTES = 262_144
MAX_PODS = 16
MAX_WINDOW_SECONDS = 180
COMMAND_TIMEOUT = 20
EVENT = "internal_mtls_handshake_rejected"
LOGGER = "app.server.spiffe_transport"
REASON = "PEER_DID_NOT_RETURN_A_CERTIFICATE"
VALID_SUMMARY = (
    "SERVER_REJECTION_EVIDENCE=VALID\n"
    "SERVER_REJECTION_EVENT=MISSING_CLIENT_CERTIFICATE\n"
    "SERVER_REJECTION_MATCHES=1\n"
)
INVALID_SUMMARY = "SERVER_REJECTION_EVIDENCE=INVALID\n"
Runner = Callable[[list[str], int], bytes]
PHASES = frozenset(
    {
        "PREPARE",
        "VERIFY",
        "CLIENT",
        "STATE",
        "SNAPSHOT",
        "LOGS",
        "COMPARE",
        "EVENT",
        "OUTPUT",
    }
)
COLLECTION_ERRORS = (
    OSError,
    LookupError,
    AttributeError,
    TypeError,
    ValueError,
    RecursionError,
)


class EvidenceError(ValueError):
    """Evidence is absent, ambiguous, malformed, incomplete, or changed."""

    def __init__(self, message: str, phase: str | None = None):
        super().__init__(message)
        self.phase = phase


@contextmanager
def collection_phase(phase: str) -> Iterator[None]:
    """Attach only a finite trusted phase, never a raw collection error."""
    try:
        yield
    except COLLECTION_ERRORS as error:
        raise EvidenceError("collection failed", phase=phase) from error


def require(condition: bool) -> None:
    if not condition:
        raise EvidenceError("evidence rejected")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise EvidenceError("non-finite JSON")


def parse_json(raw: bytes | str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw, object_pairs_hook=unique_object, parse_constant=reject_constant
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EvidenceError("invalid JSON") from error
    require(isinstance(value, dict))
    return value


def bounded_command(arguments: list[str], limit: int) -> bytes:
    """Bound stdout, stderr, wall time and memory, without using a shell."""
    executable = shutil.which("kubectl")
    require(executable is not None and arguments[0] == "kubectl")
    command = [executable, *arguments[1:]]
    try:
        with subprocess.Popen(  # noqa: S603  # Fixed kubectl executable and validated read-only arguments.
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        ) as process:
            try:
                with selectors.DefaultSelector() as selector:
                    require(process.stdout is not None and process.stderr is not None)
                    selector.register(process.stdout, selectors.EVENT_READ, True)
                    selector.register(process.stderr, selectors.EVENT_READ, False)
                    output = bytearray()
                    total = 0
                    deadline = time.monotonic() + COMMAND_TIMEOUT
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        require(remaining > 0)
                        for key, _ in selector.select(min(remaining, 0.1)):
                            chunk = os.read(key.fd, 8192)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            total += len(chunk)
                            require(total <= limit)
                            if key.data:
                                output.extend(chunk)
                    require(
                        process.wait(timeout=max(0.01, deadline - time.monotonic()))
                        == 0
                    )
                    return bytes(output)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError("collection failed") from error


def bounded_read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit)
    return value


def name(value: Any) -> str:
    require(
        isinstance(value, str)
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", value) is not None
    )
    return value


def uid(value: Any) -> str:
    require(
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value)
        is not None
    )
    return value


def timestamp(value: Any) -> int:
    require(
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", value)
        is not None
    )
    try:
        whole = datetime.fromisoformat(value[:19]).replace(tzinfo=UTC)
        fraction = value[20:-1] if value[19:20] == "." else ""
        return int(whole.timestamp()) * 1_000_000_000 + int(fraction.ljust(9, "0"))
    except ValueError as error:
        raise EvidenceError("invalid timestamp") from error


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def labels(value: Any) -> dict[str, str]:
    require(isinstance(value, dict) and 0 < len(value) <= 32)
    for key, entry in value.items():
        require(
            isinstance(key, str)
            and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./-]{0,252}", key) is not None
        )
        require(
            isinstance(entry, str)
            and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", entry) is not None
        )
    return value


def metadata(value: dict[str, Any], namespace: str) -> dict[str, Any]:
    meta = value["metadata"]
    require(isinstance(meta, dict) and meta.get("namespace") == namespace)
    name(meta["name"])
    uid(meta["uid"])
    require("deletionTimestamp" not in meta)
    return meta


def controller(meta: dict[str, Any], kind: str) -> tuple[str, str]:
    owners = [
        entry
        for entry in meta.get("ownerReferences", [])
        if entry.get("controller") is True
    ]
    require(len(owners) == 1 and owners[0].get("kind") == kind)
    return name(owners[0]["name"]), uid(owners[0]["uid"])


def backend_container(spec: dict[str, Any], image: str) -> dict[str, Any]:
    containers = [
        entry for entry in spec["containers"] if entry.get("name") == "backend"
    ]
    require(len(containers) == 1 and containers[0].get("image") == image)
    return containers[0]


class Collector:
    """Read-only API/log collection through a pinned authenticated context."""

    def __init__(self, namespace: str, context: str, runner: Runner = bounded_command):
        self.namespace = name(namespace)
        require(
            isinstance(context, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,252}", context)
            is not None
        )
        self.context = context
        self.runner = runner

    def command(self, *arguments: str, limit: int = MAX_BYTES) -> bytes:
        result = self.runner(
            [
                "kubectl",
                f"--context={self.context}",
                f"--namespace={self.namespace}",
                "--request-timeout=15s",
                *arguments,
            ],
            limit,
        )
        require(isinstance(result, bytes) and len(result) <= limit)
        return result

    def get(
        self, kind: str, resource: str | None = None, selector: str | None = None
    ) -> dict[str, Any]:
        arguments = ["get", kind]
        if resource is not None:
            arguments.append(name(resource))
        if selector is not None:
            arguments.append(f"--selector={selector}")
        return parse_json(self.command(*arguments, "--output=json"))

    def identity(self) -> dict[str, Any]:
        value = parse_json(self.command("auth", "whoami", "--output=json"))
        identity = value["status"]["userInfo"]
        require(isinstance(identity, dict))
        username = identity.get("username")
        groups = identity.get("groups")
        require(
            isinstance(username, str)
            and 0 < len(username) <= 512
            and username != "system:anonymous"
        )
        require(
            isinstance(groups, list)
            and "system:authenticated" in groups
            and "system:unauthenticated" not in groups
        )
        require(all(isinstance(group, str) for group in groups))
        return {
            "username": username,
            "uid": identity.get("uid"),
            "groups": sorted(groups),
        }

    def snapshot(self, deployment: str, service: str, image: str) -> dict[str, Any]:
        identity = self.identity()
        deploy = self.get("deployment", deployment)
        deploy_meta = metadata(deploy, self.namespace)
        require(
            deploy_meta["name"] == deployment and deploy.get("kind") == "Deployment"
        )
        spec = deploy["spec"]
        selector = spec["selector"]
        require(set(selector) == {"matchLabels"})
        selected = labels(selector["matchLabels"])
        query = ",".join(f"{key}={value}" for key, value in sorted(selected.items()))
        backend_container(spec["template"]["spec"], image)
        replicas = spec["replicas"]
        generation = deploy_meta["generation"]
        require(type(replicas) is int and 1 <= replicas <= MAX_PODS)
        require(type(generation) is int and generation >= 1)
        status = deploy["status"]
        require(status.get("observedGeneration") == generation)
        require(
            all(
                status.get(field) == replicas
                for field in (
                    "replicas",
                    "updatedReplicas",
                    "readyReplicas",
                    "availableReplicas",
                )
            )
        )
        require(status.get("unavailableReplicas", 0) == 0)
        sets = self.get("replicasets", selector=query)["items"]
        require(isinstance(sets, list) and 1 <= len(sets) <= 32)
        owned_sets = {}
        for item in sets:
            meta = metadata(item, self.namespace)
            require(item.get("kind") == "ReplicaSet")
            require(controller(meta, "Deployment") == (deployment, deploy_meta["uid"]))
            require(meta["name"] not in owned_sets)
            owned_sets[meta["name"]] = meta["uid"]
        pods = self.get("pods", selector=query)["items"]
        require(isinstance(pods, list) and len(pods) == replicas)
        frozen_pods: dict[str, Any] = {}
        for pod in pods:
            meta = metadata(pod, self.namespace)
            require(pod.get("kind") == "Pod" and meta["name"] not in frozen_pods)
            owner_name, owner_uid = controller(meta, "ReplicaSet")
            require(owned_sets.get(owner_name) == owner_uid)
            require(
                all(
                    meta.get("labels", {}).get(key) == value
                    for key, value in selected.items()
                )
            )
            container = backend_container(pod["spec"], image)
            pod_status = pod["status"]
            require(pod_status.get("phase") == "Running")
            require(
                any(
                    entry.get("type") == "Ready" and entry.get("status") == "True"
                    for entry in pod_status.get("conditions", [])
                )
            )
            statuses = [
                entry
                for entry in pod_status["containerStatuses"]
                if entry.get("name") == "backend"
            ]
            require(len(statuses) == 1)
            runtime = statuses[0]
            require(
                runtime.get("ready") is True and set(runtime["state"]) == {"running"}
            )
            # CRI may report an already-pulled repository tag in status.image,
            # even while both immutable workload specs requested the digest.
            runtime_image = runtime.get("image")
            require(
                isinstance(runtime_image, str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,511}", runtime_image)
                is not None
            )
            image_id = runtime["imageID"]
            require(
                isinstance(image_id, str)
                and len(image_id) <= 1024
                and "://" not in image_id
                and re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}",
                    image_id,
                )
                is not None
            )
            # This Kind proof's containerd runtime supplies a repository digest.
            # Require the requested manifest content, allowing repository aliases
            # but never assuming a bare runtime/configuration ID is equivalent.
            require(image_id.rsplit("@", 1)[1] == image.rsplit("@", 1)[1])
            restarts = runtime["restartCount"]
            require(type(restarts) is int and restarts >= 0)
            started_at = runtime["state"]["running"]["startedAt"]
            timestamp(started_at)
            addresses = sorted(
                str(ipaddress.ip_address(entry["ip"])) for entry in pod_status["podIPs"]
            )
            require(1 <= len(addresses) <= 2 and len(set(addresses)) == len(addresses))
            frozen_pods[meta["name"]] = {
                "uid": meta["uid"],
                "owner": [owner_name, owner_uid],
                "image": image,
                "imageID": image_id,
                "runtimeImage": runtime_image,
                "restarts": restarts,
                "startedAt": started_at,
                "addresses": addresses,
                "ports": container.get("ports", []),
            }
        svc = self.get("service", service)
        svc_meta = metadata(svc, self.namespace)
        require(svc.get("kind") == "Service" and svc_meta["name"] == service)
        require(svc["spec"]["selector"] == selected)
        ports = svc["spec"]["ports"]
        require(isinstance(ports, list) and len(ports) == 1)
        port = ports[0]
        require(port.get("name") == "http" and port.get("protocol") == "TCP")
        require(type(port.get("port")) is int and 1 <= port["port"] <= 65535)
        target = port.get("targetPort")
        target_ports = set()
        for pod in frozen_pods.values():
            matches = (
                [
                    entry["containerPort"]
                    for entry in pod["ports"]
                    if entry.get("name") == target
                    and entry.get("protocol", "TCP") == "TCP"
                ]
                if isinstance(target, str)
                else [target]
            )
            require(
                len(matches) == 1
                and type(matches[0]) is int
                and 1 <= matches[0] <= 65535
            )
            target_ports.add(matches[0])
        require(len(target_ports) == 1)
        slices = self.get(
            "endpointslices", selector=f"kubernetes.io/service-name={service}"
        )["items"]
        require(isinstance(slices, list) and 1 <= len(slices) <= 32)
        frozen_slices = {}
        covered: set[tuple[str, str]] = set()
        for item in slices:
            meta = metadata(item, self.namespace)
            require(
                item.get("kind") == "EndpointSlice"
                and meta["name"] not in frozen_slices
            )
            require(controller(meta, "Service") == (service, svc_meta["uid"]))
            require(meta.get("labels", {}).get("kubernetes.io/service-name") == service)
            require(item.get("addressType") in {"IPv4", "IPv6"})
            slice_ports = item["ports"]
            require(
                len(slice_ports) == 1
                and slice_ports[0].get("name") == "http"
                and slice_ports[0].get("protocol") == "TCP"
                and slice_ports[0].get("port") in target_ports
            )
            endpoints = item["endpoints"]
            require(isinstance(endpoints, list) and 1 <= len(endpoints) <= MAX_PODS)
            frozen_endpoints = []
            for endpoint in endpoints:
                conditions = endpoint["conditions"]
                require(
                    conditions.get("ready") is True
                    and conditions.get("terminating", False) is False
                    and conditions.get("serving", True) is True
                )
                ref = endpoint["targetRef"]
                require(
                    ref.get("kind") == "Pod" and ref.get("namespace") == self.namespace
                )
                pod = frozen_pods.get(ref.get("name"))
                require(pod is not None and ref.get("uid") == pod["uid"])
                addresses = endpoint["addresses"]
                require(isinstance(addresses, list) and len(addresses) == 1)
                address = str(ipaddress.ip_address(addresses[0]))
                require(address in pod["addresses"])
                require((ref["name"], address) not in covered)
                covered.add((ref["name"], address))
                frozen_endpoints.append(
                    {
                        "pod": ref["name"],
                        "uid": ref["uid"],
                        "address": address,
                        "conditions": conditions,
                    }
                )
            frozen_slices[meta["name"]] = {
                "uid": meta["uid"],
                "addressType": item["addressType"],
                "ports": slice_ports,
                "endpoints": sorted(
                    frozen_endpoints, key=lambda entry: (entry["pod"], entry["address"])
                ),
            }
        require(
            covered
            == {
                (pod_name, address)
                for pod_name, pod in frozen_pods.items()
                for address in pod["addresses"]
            }
        )
        return {
            "identity": identity,
            "deployment": {
                "name": deployment,
                "uid": deploy_meta["uid"],
                "generation": generation,
                "replicas": replicas,
                "selector": selected,
                "image": image,
            },
            "replicasets": owned_sets,
            "pods": frozen_pods,
            "service": {"uid": svc_meta["uid"], "spec": svc["spec"]},
            "endpointslices": frozen_slices,
        }


def validate_probe(raw: bytes) -> str:
    require(len(raw) <= 1024 and raw.endswith(b"\n") and b"\r" not in raw)
    try:
        lines = raw.decode("ascii").split("\n")[:-1]
    except UnicodeError as error:
        raise EvidenceError("invalid probe") from error
    fields = {}
    for line in lines:
        key, separator, value = line.partition("=")
        require(separator == "=" and key not in fields)
        fields[key] = value
    expected = {
        "NO_SVID_TCP": "CONNECTED",
        "NO_SVID_STAGE": "READ_ALERT",
        "NO_SVID_EVENT": "EOF",
        "NO_SVID_TLS": "ERROR",
        "PROBE_OUTPUT": "VALID",
        "PROBE_EXIT": "0",
    }
    require(set(fields) == {*expected, "NO_SVID_PROBE_ID"})
    require(all(fields[key] == value for key, value in expected.items()))
    probe = fields["NO_SVID_PROBE_ID"]
    require(re.fullmatch(r"[0-9a-f]{32}", probe) is not None)
    return str(UUID(hex=probe))


def validate_logs(raw: bytes, probe: str, start: str, end: str) -> int:
    require(len(raw) <= MAX_LOG_BYTES and (not raw or raw.endswith(b"\n")))
    try:
        lines = raw.decode("utf-8").split("\n")[:-1]
    except UnicodeError as error:
        raise EvidenceError("invalid logs") from error
    require(len(lines) <= 4096)
    lower, upper = timestamp(start), timestamp(end)
    require(0 <= upper - lower <= MAX_WINDOW_SECONDS * 1_000_000_000)
    matches = 0
    for line in lines:
        require(len(line) <= 8192)
        clock, separator, payload = line.partition(" ")
        require(separator == " ")
        observed = timestamp(clock)
        require(lower <= observed <= upper)
        relevant = EVENT in payload or probe in payload or UUID(probe).hex in payload
        if payload.startswith("{"):
            event = parse_json(payload)
            relevant = (
                relevant
                or event.get("event") == EVENT
                or event.get("probe_id") == probe
            )
            if not relevant:
                continue
            require(set(event) == {"event", "logger", "probe_id", "reason"})
            require(
                event["event"] == EVENT
                and event["logger"] == LOGGER
                and event["reason"] == REASON
            )
            tag = uid(event["probe_id"])
            require(str(UUID(tag)) == tag)
            if tag == probe:
                matches += 1
                require(matches <= 1)
        else:
            require(not relevant)
    return matches


def prepare(
    namespace: str,
    deployment: str,
    service: str,
    image: str,
    state: Path,
    *,
    runner: Runner = bounded_command,
    now: Callable[[], str] = utc_now,
) -> None:
    require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}", image)
        is not None
    )
    context = (
        runner(["kubectl", "config", "current-context"], 1024).decode("utf-8").strip()
    )
    collector = Collector(namespace, context, runner)
    with collection_phase("SNAPSHOT"):
        snapshot = collector.snapshot(name(deployment), name(service), image)
    current = now()
    timestamp(current)
    # Kubernetes PodLogOptions.sinceTime uses metav1.Time and serializes seconds.
    # Use that same boundary locally. The random nonce is generated only after
    # prepare returns, so preceding same-second records cannot match this probe.
    started = current[:19] + "Z"
    value = {
        "version": 1,
        "namespace": namespace,
        "context": context,
        "deployment": deployment,
        "service": service,
        "image": image,
        "started": started,
        "snapshot": snapshot,
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    require(len(raw) <= MAX_BYTES)
    # Never overwrite an old state or follow a symlink. The caller uses WORK_DIR.
    descriptor = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)


def verify(
    state: Path,
    probe_file: Path,
    *,
    runner: Runner = bounded_command,
    now: Callable[[], str] = utc_now,
) -> str:
    with collection_phase("CLIENT"):
        probe = validate_probe(bounded_read(probe_file, 1024))
    with collection_phase("STATE"):
        value = parse_json(bounded_read(state, MAX_BYTES))
        require(
            set(value)
            == {
                "version",
                "namespace",
                "context",
                "deployment",
                "service",
                "image",
                "started",
                "snapshot",
            }
            and type(value["version"]) is int
            and value["version"] == 1
        )
        start = value["started"]
        require(
            0
            <= timestamp(now()) - timestamp(start)
            <= MAX_WINDOW_SECONDS * 1_000_000_000
        )
    collector = Collector(value["namespace"], value["context"], runner)
    before = value["snapshot"]
    require(
        isinstance(before, dict)
        and isinstance(before.get("pods"), dict)
        and 1 <= len(before["pods"]) <= MAX_PODS
    )
    with collection_phase("LOGS"):
        logs = []
        for pod in sorted(before["pods"]):
            logs.append(
                collector.command(
                    "logs",
                    name(pod),
                    "--container=backend",
                    f"--since-time={start}",
                    "--timestamps=true",
                    "--tail=-1",
                    limit=MAX_LOG_BYTES,
                )
            )
    with collection_phase("SNAPSHOT"):
        after = collector.snapshot(
            value["deployment"], value["service"], value["image"]
        )
    with collection_phase("COMPARE"):
        require(before == after)
    with collection_phase("EVENT"):
        end = now()
        require(sum(validate_logs(raw, probe, start, end) for raw in logs) == 1)
    return VALID_SUMMARY


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    for argument in ("namespace", "deployment", "service", "image"):
        preparation.add_argument(f"--{argument}", required=True)
    preparation.add_argument("--state", type=Path, required=True)
    verification = commands.add_parser("verify")
    verification.add_argument("--state", type=Path, required=True)
    verification.add_argument("--probe", type=Path, required=True)
    verification.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = INVALID_SUMMARY
    success = False
    failed_phase = "PREPARE" if args.command == "prepare" else "VERIFY"
    try:
        if args.command == "prepare":
            prepare(
                args.namespace, args.deployment, args.service, args.image, args.state
            )
        else:
            result = verify(args.state, args.probe)
        success = True
    except COLLECTION_ERRORS as error:
        # Never echo Kubernetes errors, log payloads, arguments, IDs or metadata.
        if isinstance(error, EvidenceError) and error.phase in PHASES:
            failed_phase = error.phase
        result += f"SERVER_EVIDENCE_PHASE={failed_phase}\n"
    if args.command == "verify":
        try:
            args.output.write_text(result, encoding="ascii")
        except OSError:
            failed_phase = "OUTPUT"
            success = False
    print(
        "SERVER_EVIDENCE_COLLECTION=VALID"
        if success
        else "SERVER_EVIDENCE_COLLECTION=INVALID"
    )
    if not success:
        print(f"SERVER_EVIDENCE_PHASE={failed_phase}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
