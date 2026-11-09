"""Run the fixed client-IP probe once against an owned Core stand (AUD-164/167).

The caller holds the stand's lifecycle lock. Under it this module verifies the
signed owner, Docker daemon and Compose resources, creates one no-mount probe
container from the backend image, derives the probe input from inspected records,
runs the probe through stdin, and rechecks the stack before removing the probe.

Output is limited to case names, status codes and timings. Addresses, identities,
headers and bodies stay private. Gateway and deployment paths are not assessed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import live_stand, owned_client_ip_runtime, owned_nats_outage
from scripts.owned_client_ip_acceptance import (
    ProbeObservations,
    SubsetVerdict,
    decode_observations,
    evaluate_observations,
)
from scripts.owned_nats_process import (
    PrivateProcessRequest,
    PrivateProcessResult,
    run_private_process,
)

_PROBE_PURPOSE = "aud164-167-client-ip-probe"
_LOGICAL_NETWORKS = ("public", "frontend_net", "internal", "revocation_net")
_PROBE_BUDGET_MS = 120_000
_ATTACH_CAP_SECONDS = 120.0
_INPUT_LIMIT = 262_144
_PROBE_SOURCE = Path(__file__).with_name("owned_client_ip_probe.py")
_PROBE_TRAILER = """
print(
    json.dumps(
        _collect(parse_input(json.loads(_OWNED_INPUT)), _request),
        separators=(",", ":"),
    )
)
"""


class ClientIpNotAccepted(RuntimeError):
    """A closed failure naming only the phase and fixed step that did not pass."""

    def __init__(self, phase: str, step: str | None = None) -> None:
        super().__init__(phase)
        self.phase = phase
        self.step = step


class _LiveDocker:
    def read(self, arguments: Sequence[str]) -> str:
        return live_stand._docker_output(arguments, "owned client-IP docker failed")

    def inspect(self, arguments: Sequence[str]) -> dict[str, Any]:
        return live_stand._docker_inspect_object(
            arguments, "owned client-IP inspect failed"
        )

    def attach(self, container_id: str, program: bytes) -> PrivateProcessResult:
        request = PrivateProcessRequest(
            argv=("docker", "attach", "--sig-proxy=false", container_id),
            cwd=str(live_stand.REPO_ROOT),
            env={
                name: os.environ[name]
                for name in ("PATH", "HOME")
                if name in os.environ
            },
            stdin=program,
            input_limit=_INPUT_LIMIT,
        )
        deadline = owned_nats_outage.Deadline.after(
            _ATTACH_CAP_SECONDS, clock=time.monotonic
        )
        return run_private_process(request, deadline=deadline)


@dataclass(frozen=True, slots=True)
class ClientIpResult:
    observed: ProbeObservations
    verdict: SubsetVerdict


def _network_names(evidence: live_stand.ComposeResourceEvidence) -> dict[str, str]:
    bindings = {key: name for key, name, _external in evidence.network_bindings}
    if any(name not in bindings for name in _LOGICAL_NETWORKS):
        raise ClientIpNotAccepted("networks")
    return {name: bindings[name] for name in _LOGICAL_NETWORKS}


def _inspect_services(
    docker: _LiveDocker, owner: live_stand.StandOwner
) -> dict[str, dict[str, Any]]:
    containers: dict[str, dict[str, Any]] = {}
    for identity in live_stand._project_container_ids(owner.project_name):
        record = docker.inspect(["container", "inspect", identity])
        labels = record.get("Config", {}).get("Labels", {})
        service = labels.get("com.docker.compose.service")
        if service not in live_stand.LIVE_TRUSTED_PROXY_SERVICES:
            continue
        if service in containers:
            raise ClientIpNotAccepted("containers")
        containers[service] = record
    if set(containers) != set(live_stand.LIVE_TRUSTED_PROXY_SERVICES):
        raise ClientIpNotAccepted("containers")
    return containers


def _inspect_networks(
    docker: _LiveDocker, names: dict[str, str]
) -> dict[str, dict[str, Any]]:
    return {
        name: docker.inspect(["network", "inspect", name]) for name in names.values()
    }


def _create_arguments(run_id: str, image: str, network: str) -> list[str]:
    return [
        "create",
        "--interactive",
        "--attach",
        "stdin",
        "--attach",
        "stdout",
        "--attach",
        "stderr",
        "--label",
        f"org.university.audit.run={run_id}",
        "--label",
        f"org.university.audit.purpose={_PROBE_PURPOSE}",
        "--network",
        network,
        "--user",
        "10001:10001",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--no-healthcheck",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--cpus",
        "1",
        "--restart",
        "no",
        "--entrypoint",
        "python",
        image,
        "-",
    ]


def _stable_container(record: dict[str, Any]) -> dict[str, Any]:
    """Keep the identity and wiring; drop health logs and other moving fields."""
    state = record.get("State", {})
    settings = record.get("NetworkSettings", {})
    return {
        "Id": record.get("Id"),
        "Image": record.get("Image"),
        "Config": record.get("Config"),
        "HostConfig": record.get("HostConfig"),
        "RestartCount": record.get("RestartCount"),
        "Networks": settings.get("Networks"),
        "State": {key: state.get(key) for key in ("Running", "Status", "StartedAt")},
    }


def _stable_network(record: dict[str, Any], probe_id: str) -> dict[str, Any]:
    """The probe leaves its networks when it exits, so it is not part of the witness."""
    endpoints = {
        identity: value
        for identity, value in record.get("Containers", {}).items()
        if identity != probe_id
    }
    return {**record, "Containers": endpoints}


def _stable_probe(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in ("Id", "Image", "Config", "HostConfig")}


def _witness(
    owner: live_stand.StandOwner,
    evidence: live_stand.ComposeResourceEvidence,
    containers: dict[str, dict[str, Any]],
    networks: dict[str, dict[str, Any]],
    probe: dict[str, Any],
    image: dict[str, Any],
    *,
    probe_id: str,
    run_id: str,
) -> object:
    return owned_client_ip_runtime.freeze_topology_witness(
        {
            "owner": owner,
            "evidence": evidence,
            "containers": {
                name: _stable_container(record) for name, record in containers.items()
            },
            "networks": {
                name: _stable_network(record, probe_id)
                for name, record in networks.items()
            },
            "probe": _stable_probe(probe),
            "image": {"Id": image.get("Id")},
            "expected_probe_id": probe_id,
            "run_id": run_id,
        }
    )


def _program(probe_input: dict[str, object]) -> bytes:
    source = _PROBE_SOURCE.read_text(encoding="utf-8")
    payload = json.dumps(json.dumps(probe_input, separators=(",", ":")))
    return f"{source}\n_OWNED_INPUT = {payload}\n{_PROBE_TRAILER}".encode()


def _probe_removed(docker: _LiveDocker, probe_id: str) -> bool:
    try:
        docker.read(["rm", "--force", "--volumes", probe_id])
        remaining = docker.read(
            ["ps", "--all", "--quiet", "--no-trunc", "--filter", f"id={probe_id}"]
        )
    except live_stand.StandError:
        return False
    return not remaining.strip()


def _run_probe(
    docker: _LiveDocker,
    owner: live_stand.StandOwner,
    evidence: live_stand.ComposeResourceEvidence,
    names: dict[str, str],
    containers: dict[str, dict[str, Any]],
    probe_id: str,
    run_id: str,
    clock: Callable[[], float],
) -> ProbeObservations:
    docker.read(["network", "connect", names["frontend_net"], probe_id])
    docker.read(["start", probe_id])
    networks = _inspect_networks(docker, names)
    probe = docker.inspect(["container", "inspect", probe_id])
    image = docker.inspect(["image", "inspect", str(probe.get("Image"))])
    try:
        probe_input = owned_client_ip_runtime.derive_probe_input(
            owner,
            evidence,
            containers,
            networks,
            probe,
            image,
            expected_probe_id=probe_id,
            run_id=run_id,
        )
        before = _witness(
            owner,
            evidence,
            containers,
            networks,
            probe,
            image,
            probe_id=probe_id,
            run_id=run_id,
        )
    except owned_client_ip_runtime.RuntimeNotReady as error:
        raise ClientIpNotAccepted("topology", error.step) from None

    started = clock()
    result = docker.attach(probe_id, _program(probe_input))
    elapsed_ms = int((clock() - started) * 1000)
    observed = decode_observations(
        result,
        expected_source_sha=str(owner.source_sha),
        expected_run_id=run_id,
        now_ms=elapsed_ms,
        deadline_ms=_PROBE_BUDGET_MS,
    )
    if observed is None:
        raise ClientIpNotAccepted("probe")

    after_containers = _inspect_services(docker, owner)
    after_networks = _inspect_networks(docker, names)
    after = _witness(
        owner,
        evidence,
        after_containers,
        after_networks,
        docker.inspect(["container", "inspect", probe_id]),
        image,
        probe_id=probe_id,
        run_id=run_id,
    )
    try:
        owned_client_ip_runtime.assert_topology_unchanged(before, after)
    except owned_client_ip_runtime.RuntimeNotReady:
        raise ClientIpNotAccepted("topology_changed") from None
    return observed


def run_locked(
    docker: _LiveDocker,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> ClientIpResult:
    """Run one probe under the caller's lifecycle lock and require its cleanup."""
    live_stand._require_worktree()
    owner = live_stand.load_stand_owner(live_stand.WORKTREE)
    live_stand._require_owned_docker_daemon(owner)
    evidence = live_stand._verify_stand_owner_compose_resources(
        live_stand.WORKTREE, owner
    )
    names = _network_names(evidence)
    containers = _inspect_services(docker, owner)
    image_id = containers["backend"].get("Image")
    if not isinstance(image_id, str):
        raise ClientIpNotAccepted("containers")

    run_id = secrets.token_hex(32)
    probe_id = docker.read(_create_arguments(run_id, image_id, names["public"])).strip()
    try:
        observed = _run_probe(
            docker, owner, evidence, names, containers, probe_id, run_id, clock
        )
    finally:
        # A probe failure propagates from here, so a failed removal cannot hide it.
        removed = _probe_removed(docker, probe_id)
    if not removed:
        raise ClientIpNotAccepted("cleanup")
    return ClientIpResult(observed, evaluate_observations(observed))


def summary_lines(result: ClientIpResult) -> list[str]:
    """Render finite statuses and timings, never an address or an identity."""
    lines = []
    for case in result.observed.cases:
        direct = case.backend_direct_untrusted
        lines.append(
            f"owned client-IP case={case.case} allowed={len(case.allowed)}"
            f" allowed_status={case.allowed[0]} blocked={case.blocked}"
            f" other_client={case.other_client}"
            f" spoofed={','.join(map(str, case.spoofed))}"
            f" direct_untrusted={case.direct_untrusted}"
            f" backend_direct_untrusted={'n/a' if direct is None else direct}"
            f" elapsed_ms={case.elapsed_ms}"
        )
    verdict = result.verdict
    lines.append(
        f"owned client-IP verdict backend={str(verdict.backend).lower()}"
        f" ws_hub={str(verdict.ws_hub).lower()} gateway={verdict.gateway}"
        f" deployment={verdict.deployment}"
    )
    lines.append(f"owned client-IP source_sha={result.observed.source_sha}")
    lines.append("owned client-IP topology=unchanged cleanup=confirmed")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args(argv)
    args.in_place = True
    args.command = "client-ip"
    try:
        live_stand._configure_state_mode(args)
        with live_stand.stand_lifecycle_lock():
            result = run_locked(_LiveDocker())
    except ClientIpNotAccepted as error:
        step = f" step={error.step}" if error.step else ""
        print(f"owned client-IP outcome=failed phase={error.phase}{step}", flush=True)
        return 1
    except live_stand.StandError:
        print("owned client-IP outcome=failed phase=stand", flush=True)
        return 1
    for line in summary_lines(result):
        print(line, flush=True)
    accepted = result.verdict.backend and result.verdict.ws_hub
    print(
        f"owned client-IP outcome={'passed' if accepted else 'failed'}"
        f"{'' if accepted else ' phase=verdict'}",
        flush=True,
    )
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())
