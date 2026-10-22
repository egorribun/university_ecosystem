"""No-I/O contract for owner-scoped Compose inventory reads."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import replace

import pytest

from scripts import live_stand
from scripts import owned_nats_docker as docker
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline


@pytest.fixture(autouse=True)
def no_output_or_legacy_io(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("inventory contract must not invoke legacy I/O")

    for name in (
        "_owner_signing_key",
        "load_stand_owner",
        "docker_daemon_fingerprint",
        "stand_lifecycle_lock",
    ):
        monkeypatch.setattr(live_stand, name, forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    yield
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.fixture
def daemon_no_process(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("unexpected-process")
        raise AssertionError("pure inventory preparation must not execute")

    monkeypatch.setattr(process, "run_private_process", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    yield
    assert calls == []


@pytest.fixture
def no_direct_docker_execution(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("bounded transport tests must not execute Docker")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)


_DAEMON_ID = b"owned-daemon-fixture"
_DAEMON_FINGERPRINT = hashlib.sha256(_DAEMON_ID).hexdigest()


class _DaemonClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _daemon_pins():
    return docker.DockerReadPins(
        executable="/owned-tools/docker",
        endpoint="unix:///owned-runtime/docker.sock",
        config_directory="/owned-state/docker-config",
        cwd="/owned-source/repository",
        environment=(),
        daemon_fingerprint=_DAEMON_FINGERPRINT,
    )


def _daemon_result(**changes):
    result = process.PrivateProcessResult(
        outcome=process.ProcessOutcome.EXITED,
        returncode=0,
        stdout=_DAEMON_ID + b"\n",
        stderr=b"",
        local_cleanup=process.LocalCleanup.CONFIRMED,
    )
    return replace(result, **changes)


def _daemon_deadline():
    return Deadline.after(10, clock=_DaemonClock())


_COMPOSE_ROOTS = (
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb",
)
_COMPOSE_SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)
_COMPOSE_PORT_NAMES = (
    "BACKEND",
    "FRONTEND",
    "POSTGRES",
    "GATEWAY",
    "WS_HUB",
    "TEMPORAL_GRPC",
    "TEMPORAL_WEB",
    "IMGPROXY",
    "GRAFANA",
    "PROMETHEUS",
    "ALLOY",
    "PYROSCOPE",
    "CADDY_HTTP",
    "CADDY_HTTPS",
    "MINIO",
    "MAILPIT",
)


@pytest.fixture
def compose_case():
    project = "ue-live-0123456789abcdef"
    repository = "/owned-source/repository"
    state = "/owned-state/ue-live-acceptance/run-compose"
    ports = tuple(
        sorted((name, 20_000 + index) for index, name in enumerate(_COMPOSE_PORT_NAMES))
    )
    mount = {"type": "volume", "source": "app-data", "target": "/app/data"}
    services = {name: {} for name in _COMPOSE_SERVICES}
    services["caddy"]["depends_on"] = {
        name: {"condition": "service_started"}
        for name in _COMPOSE_SERVICES
        if name != "caddy"
    }
    services["backend"] = {
        "volumes": [mount],
        "environment": {"PRIVATE_CONFIG": "private-compose-config-fixture"},
        "labels": {"private.fixture.label": "private-compose-label-fixture"},
    }
    model = {
        "name": project,
        "services": services,
        "volumes": {"app-data": {}},
        "networks": {"default": {}},
    }
    projection = {
        "project_name": project,
        "volumes": {
            "app-data": {
                "external": False,
                "resolved_name": f"{project}_app-data",
            }
        },
        "networks": {
            "default": {
                "external": False,
                "resolved_name": f"{project}_default",
            }
        },
        "service_mounts": {
            name: {
                "volumes": [dict(mount)] if name == "backend" else [],
                "volumes_from": [],
                "networks": ["default"],
                "network_mode": None,
            }
            for name in _COMPOSE_SERVICES
        },
        "stack": "core",
        "service_roots": list(_COMPOSE_ROOTS),
        "selected_services": list(_COMPOSE_SERVICES),
        "published_port_names": [
            "BACKEND",
            "CADDY_HTTP",
            "CADDY_HTTPS",
            "FRONTEND",
            "GATEWAY",
            "IMGPROXY",
            "MAILPIT",
            "MINIO",
            "POSTGRES",
            "WS_HUB",
        ],
    }
    canonical = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    fingerprint = hashlib.sha256(canonical).hexdigest()
    owner = OwnerEvidence(
        repository=repository,
        worktree=state,
        project_name=project,
        published_ports=ports,
        schema_version=11,
        daemon_fingerprint=_DAEMON_FINGERPRINT,
        compose_resource_fingerprint=fingerprint,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha="a" * 40,
        stack="core",
        service_roots=_COMPOSE_ROOTS,
        selected_services=_COMPOSE_SERVICES,
    )
    pins = replace(
        _daemon_pins(),
        cwd=state,
        environment=(("LC_ALL", "C"),),
    )
    compose = docker.ComposeConfigPins(
        project_directory=repository,
        env_file=f"{state}/.env.docker",
        compose_files=(
            f"{repository}/docker-compose.full.yml",
            f"{repository}/docker-compose.live.yml",
            f"{state}/docker-compose.live-state.yml",
        ),
    )
    evidence = live_stand.ComposeResourceEvidence(
        fingerprint=fingerprint,
        managed_volumes=(("app-data", f"{project}_app-data"),),
        declared_volume_names=(f"{project}_app-data",),
        managed_networks=(("default", f"{project}_default"),),
        managed_services=_COMPOSE_SERVICES,
        stack="core",
        service_roots=_COMPOSE_ROOTS,
        selected_services=_COMPOSE_SERVICES,
        network_bindings=(("default", f"{project}_default", False),),
        service_networks=tuple((name, ("default",)) for name in _COMPOSE_SERVICES),
    )
    raw = json.dumps(model, separators=(",", ":")).encode("utf-8")
    return owner, pins, compose, model, raw, evidence


def _matched_runtime_metadata(owner, evidence):
    daemon = docker.DaemonMetadataResult(
        docker.DaemonMetadataStatus.MATCHED_METADATA,
        owner.daemon_fingerprint,
    )
    compose = docker.ComposeMetadataResult(
        docker.ComposeMetadataStatus.MATCHED_METADATA,
        evidence,
    )
    operation = getattr(docker, "compose_coordinator_metadata", None)
    assert callable(operation)
    return operation(owner, daemon, compose)


def _runtime_container_id(index):
    return f"{index:064x}"


def _runtime_inspect_record(pair, container_id, service, index):
    initializer = service in {
        "migrations",
        "minio-init",
        "postgres-databases-init",
        "spicedb-migrate",
    }
    return {
        "Id": container_id,
        "Name": f"/{pair.owner.project_name}-{service}-1",
        "Image": f"sha256:{index:064x}",
        "Config": {
            "Image": f"university/{service}:candidate",
            "Labels": {
                "com.docker.compose.project": pair.owner.project_name,
                "com.docker.compose.service": service,
                "com.docker.compose.oneoff": "False",
            },
        },
        "Mounts": [],
        "State": {
            "Running": not initializer,
            "Status": "exited" if initializer else "running",
            "Health": None
            if initializer
            or service
            not in {
                "backend",
                "outbox-worker",
                "postgres",
                "minio",
                "nats",
            }
            else {"Status": "healthy"},
            "ExitCode": 0,
            "OOMKilled": False,
        },
        "RestartCount": 0,
    }


def _runtime_process_result(stdout):
    return process.PrivateProcessResult(
        outcome=process.ProcessOutcome.EXITED,
        returncode=0,
        stdout=stdout,
        stderr=b"",
        local_cleanup=process.LocalCleanup.CONFIRMED,
    )


def _runtime_inspect_output(pair, container_ids, services=None):
    selected = pair.selected_services if services is None else services
    records = [
        _runtime_inspect_record(pair, container_id, service, index + 1)
        for index, (container_id, service) in enumerate(
            zip(container_ids, selected, strict=True)
        )
    ]
    return b"".join(
        json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n"
        for record in records
    )


def test_owned_project_container_id_request_includes_all_exact_project_containers(
    compose_case, daemon_no_process
):
    owner, pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    deadline = _daemon_deadline()
    operation = getattr(docker, "prepare_container_id_read", None)
    assert callable(operation), "bounded project inventory request is unavailable"

    request = operation(pair, pins, deadline=deadline)

    assert type(request) is process.PrivateProcessRequest
    assert request.argv == (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
        "ps",
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        f"label=com.docker.compose.project={owner.project_name}",
    )
    assert request.cwd == pins.cwd
    assert request.env == dict(pins.environment)
    assert request.stdin == b""
    assert request.input_limit == 0
    assert request.stdout_limit >= 10_000 * 66
    assert request.stderr_limit == 16_384
    assert owner.project_name not in repr(request)


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        (b"", ()),
        (b"1" * 64, ("1" * 64,)),
        (b"1" * 64 + b"\r\n" + b"2" * 64 + b"\n", ("1" * 64, "2" * 64)),
    ],
)
def test_owned_project_container_id_decoder_accepts_only_canonical_unique_ids(
    compose_case, daemon_no_process, stdout, expected
):
    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    operation = getattr(docker, "decode_container_id_read", None)
    assert callable(operation), "bounded project inventory decoding is unavailable"

    result = operation(
        _runtime_process_result(stdout),
        pair,
        deadline=_daemon_deadline(),
    )

    assert result == expected


@pytest.mark.parametrize(
    "stdout",
    [
        b"1" * 63,
        b"A" * 64,
        b"1" * 64 + b"\n\n",
        b"1" * 64 + b"\n" + b"1" * 64,
        b"1" * 64 + b" extra",
        b"1" * 64 + b"\n" + b"x" * 65,
        b"\xff",
    ],
)
def test_owned_project_container_id_decoder_refuses_ambiguous_results(
    compose_case, daemon_no_process, stdout
):
    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    operation = getattr(docker, "decode_container_id_read", None)
    assert callable(operation), "bounded project inventory decoding is unavailable"

    assert (
        operation(
            _runtime_process_result(stdout),
            pair,
            deadline=_daemon_deadline(),
        )
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"returncode": 1},
        {"returncode": False},
        {"local_cleanup": process.LocalCleanup.UNPROVEN},
        {"stderr": b"private diagnostic"},
        {"outcome": process.ProcessOutcome.TIMED_OUT},
    ],
)
def test_owned_project_container_id_decoder_requires_confirmed_private_success(
    compose_case, daemon_no_process, changes
):
    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    operation = getattr(docker, "decode_container_id_read", None)
    assert callable(operation), "bounded project inventory decoding is unavailable"

    result = operation(
        replace(_runtime_process_result(b"1" * 64), **changes),
        pair,
        deadline=_daemon_deadline(),
    )

    assert result is None


def test_owned_project_inspect_requests_use_only_captured_validated_ids(
    compose_case, daemon_no_process
):
    owner, pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(_runtime_container_id(index) for index in range(1, 66))
    operation = getattr(docker, "prepare_container_inspect_reads", None)
    assert callable(operation), "bounded captured-ID inspection is unavailable"

    requests = operation(pair, pins, ids, deadline=_daemon_deadline())

    assert len(requests) == 2
    assert all(type(request) is process.PrivateProcessRequest for request in requests)
    assert requests[0].argv[:5] == (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
    )
    assert requests[0].argv[5:9] == ("inspect", "--type", "container", "--format")
    assert requests[0].argv[9] == docker._RUNTIME_INSPECT_FORMAT
    assert requests[0].argv[10:] == ids[:64]
    assert requests[1].argv[10:] == ids[64:]
    assert all(request.cwd == pins.cwd for request in requests)
    assert all(request.env == dict(pins.environment) for request in requests)
    assert all(request.input_limit == 0 for request in requests)


@pytest.mark.parametrize(
    "ids",
    [
        ("1" * 63,),
        ("A" * 64,),
        ("1" * 64, "1" * 64),
        ("1" * 64, "2" * 64 + "x"),
    ],
)
def test_owned_project_inspect_preparation_refuses_noncanonical_ids(
    compose_case, daemon_no_process, ids
):
    owner, pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    operation = getattr(docker, "prepare_container_inspect_reads", None)
    assert callable(operation), "bounded captured-ID inspection is unavailable"

    assert operation(pair, pins, ids, deadline=_daemon_deadline()) is None


def test_owned_project_inspect_decoder_returns_canonical_runtime_snapshots(
    compose_case, daemon_no_process
):
    from scripts.owned_nats_coordinator import RuntimeEvidence
    from scripts.owned_nats_outage import (
        ContainerSnapshot,
        InventoryVerdict,
        validate_inventory,
    )

    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 1)
    )
    output = _runtime_inspect_output(pair, ids)
    operation = getattr(docker, "decode_container_inspect_reads", None)
    assert callable(operation), "bounded captured inventory decoding is unavailable"

    records = operation(
        pair,
        evidence,
        ids,
        (_runtime_process_result(output),),
        deadline=_daemon_deadline(),
    )

    assert type(records) is tuple
    assert len(records) == len(pair.selected_services)
    assert all(type(record) is ContainerSnapshot for record in records)
    assert records[0].container_id == ids[0]
    assert records[0].service == pair.selected_services[0]
    assert validate_inventory(pair.selected_services, records) is InventoryVerdict.VALID
    assert (
        RuntimeEvidence(
            daemon_fingerprint=pair.daemon_fingerprint,
            resource_fingerprint=pair.resource_fingerprint,
            containers=records,
        ).daemon_fingerprint
        == owner.daemon_fingerprint
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-id",
        "extra-id",
        "duplicate-id",
        "foreign-project",
        "unknown-service",
        "missing-state",
        "boolean-restart-count",
        "oneoff-true",
        "oneoff-missing",
        "oneoff-malformed",
    ],
)
def test_owned_project_inspect_decoder_refuses_unbound_or_malformed_inventory(
    compose_case, daemon_no_process, mutation
):
    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 1)
    )
    records = [
        _runtime_inspect_record(pair, container_id, service, index + 1)
        for index, (container_id, service) in enumerate(
            zip(ids, pair.selected_services, strict=True)
        )
    ]
    if mutation == "missing-id":
        records.pop()
    elif mutation == "extra-id":
        records[0]["Id"] = _runtime_container_id(len(ids) + 10)
    elif mutation == "duplicate-id":
        records[-1]["Id"] = records[0]["Id"]
    elif mutation == "foreign-project":
        records[0]["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    elif mutation == "unknown-service":
        records[0]["Config"]["Labels"]["com.docker.compose.service"] = "orphan"
    elif mutation == "missing-state":
        records[0].pop("State")
    elif mutation == "boolean-restart-count":
        records[0]["RestartCount"] = True
    elif mutation == "oneoff-true":
        records[0]["Config"]["Labels"]["com.docker.compose.oneoff"] = "True"
        records[0]["Name"] = (
            f"/{pair.owner.project_name}-"
            f"{records[0]['Config']['Labels']['com.docker.compose.service']}-run-candidate"
        )
    elif mutation == "oneoff-missing":
        records[0]["Config"]["Labels"].pop("com.docker.compose.oneoff")
    elif mutation == "oneoff-malformed":
        records[0]["Config"]["Labels"]["com.docker.compose.oneoff"] = "false"
    output = _runtime_process_result(
        b"".join(
            json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n"
            for record in records
        )
    )
    operation = getattr(docker, "decode_container_inspect_reads", None)
    assert callable(operation), "bounded captured inventory decoding is unavailable"

    assert (
        operation(pair, evidence, ids, (output,), deadline=_daemon_deadline()) is None
    )


def test_owned_project_inspect_decoder_leaves_runtime_verdict_to_coordinator(
    compose_case, daemon_no_process
):
    from scripts.owned_nats_outage import InventoryVerdict, validate_inventory

    owner, _pins, _compose, _model, _raw, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 1)
    )
    records = [
        _runtime_inspect_record(pair, container_id, service, index + 1)
        for index, (container_id, service) in enumerate(
            zip(ids, pair.selected_services, strict=True)
        )
    ]
    records[0]["State"]["ExitCode"] = 1
    output = _runtime_process_result(
        b"".join(
            json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n"
            for record in records
        )
    )
    operation = getattr(docker, "decode_container_inspect_reads", None)
    assert callable(operation), "bounded captured inventory decoding is unavailable"

    snapshots = operation(pair, evidence, ids, (output,), deadline=_daemon_deadline())

    assert snapshots is not None
    assert snapshots[0].exit_code == 1
    assert (
        validate_inventory(pair.selected_services, snapshots)
        is InventoryVerdict.INVALID_RUNTIME
    )


def test_owned_core_runtime_composes_exact_readonly_collections_once(
    monkeypatch, compose_case, no_direct_docker_execution
):
    from scripts.owned_nats_outage import InventoryVerdict, validate_inventory

    owner, pins, compose, _model, raw_compose, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 1)
    )
    inspect_output = _runtime_inspect_output(pair, ids)
    deadline = _daemon_deadline()
    calls = []
    monkeypatch.setattr(
        Deadline,
        "after",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime observation must retain the caller deadline")
        ),
    )

    def collect(request, *, deadline):
        calls.append((request, deadline))
        command = request.argv[5]
        if command == "info":
            return _daemon_result()
        if command == "compose":
            return _runtime_process_result(raw_compose)
        if command == "ps":
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        if command == "inspect":
            return _runtime_process_result(inspect_output)
        raise AssertionError(f"unexpected bounded command: {command}")

    monkeypatch.setattr(process, "run_private_process", collect)
    operation = getattr(docker, "observe_owned_core_runtime", None)
    assert callable(operation), "bounded owned Core runtime observation is unavailable"

    result = operation(owner, pins, compose, deadline=deadline)

    assert result is not None
    assert result.daemon_fingerprint == owner.daemon_fingerprint
    assert result.resource_fingerprint == owner.compose_resource_fingerprint
    assert (
        validate_inventory(owner.selected_services, result.containers)
        is InventoryVerdict.VALID
    )
    assert len(calls) == 8
    assert [request.argv[5] for request, _actual_deadline in calls] == [
        "info",
        "compose",
        "info",
        "ps",
        "info",
        "info",
        "inspect",
        "info",
    ]
    assert all(actual_deadline is deadline for _request, actual_deadline in calls)
    assert calls[3][0].argv[6:11] == (
        "--all",
        "--quiet",
        "--no-trunc",
        "--filter",
        f"label=com.docker.compose.project={owner.project_name}",
    )
    assert calls[6][0].argv[-len(ids) :] == ids


@pytest.mark.parametrize("rejected_stage", ["daemon", "compose", "ids", "inspect"])
def test_owned_core_runtime_stops_after_first_unmatched_read(
    monkeypatch, compose_case, no_direct_docker_execution, rejected_stage
):
    owner, pins, compose, _model, raw_compose, evidence = compose_case
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(owner.selected_services) + 1)
    )
    valid_inspect = _runtime_inspect_output(
        _matched_runtime_metadata(owner, evidence), ids
    )
    calls = []

    def collect(request, *, deadline):
        calls.append(request)
        command = request.argv[5]
        if command == "info":
            if rejected_stage == "daemon":
                return _daemon_result(stdout=b"different-daemon\n")
            return _daemon_result()
        if command == "compose":
            if rejected_stage == "compose":
                return _runtime_process_result(b"{}")
            return _runtime_process_result(raw_compose)
        if command == "ps":
            if rejected_stage == "ids":
                return _runtime_process_result(b"bad-id\n")
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        if command == "inspect":
            if rejected_stage == "inspect":
                return _runtime_process_result(b"{}\n")
            return _runtime_process_result(valid_inspect)
        raise AssertionError(f"unexpected bounded command: {command}")

    monkeypatch.setattr(process, "run_private_process", collect)
    operation = getattr(docker, "observe_owned_core_runtime", None)
    assert callable(operation), "bounded owned Core runtime observation is unavailable"

    result = operation(owner, pins, compose, deadline=_daemon_deadline())

    assert result is None
    expected_calls = {"daemon": 1, "compose": 2, "ids": 5, "inspect": 8}[rejected_stage]
    assert len(calls) == expected_calls


@pytest.mark.parametrize(
    ("drift_info_call", "expected_command_count"),
    [(2, 3), (3, 5), (4, 6), (5, 8)],
    ids=["before-list", "after-list", "before-inspect", "after-inspect"],
)
def test_owned_core_runtime_rechecks_pinned_daemon_around_inventory_reads(
    monkeypatch,
    compose_case,
    no_direct_docker_execution,
    drift_info_call,
    expected_command_count,
):
    owner, pins, compose, _model, raw_compose, evidence = compose_case
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(owner.selected_services) + 1)
    )
    valid_inspect = _runtime_inspect_output(
        _matched_runtime_metadata(owner, evidence), ids
    )
    calls = []
    info_calls = 0

    def collect(request, *, deadline):
        nonlocal info_calls
        calls.append(request)
        command = request.argv[5]
        if command == "info":
            info_calls += 1
            if info_calls == drift_info_call:
                return _daemon_result(stdout=b"different-daemon\n")
            return _daemon_result()
        if command == "compose":
            return _runtime_process_result(raw_compose)
        if command == "ps":
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        if command == "inspect":
            return _runtime_process_result(valid_inspect)
        raise AssertionError(f"unexpected bounded command: {command}")

    monkeypatch.setattr(process, "run_private_process", collect)
    operation = getattr(docker, "observe_owned_core_runtime", None)
    assert callable(operation), "bounded owned Core runtime observation is unavailable"

    result = operation(owner, pins, compose, deadline=_daemon_deadline())

    assert result is None
    assert len(calls) == expected_command_count
    assert calls[-1].argv[5] == "info"


def test_owned_core_runtime_retains_owner_and_docker_pins_across_collectors(
    monkeypatch, compose_case, no_direct_docker_execution
):
    owner, pins, compose, _model, raw_compose, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 1)
    )
    valid_inspect = _runtime_inspect_output(pair, ids)
    original_prefix = (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
    )
    original_project = owner.project_name
    calls = []

    def collect(request, *, deadline):
        calls.append(request)
        if request.argv[5] == "info":
            if len(calls) == 1:
                object.__setattr__(owner, "daemon_fingerprint", "3" * 64)
                object.__setattr__(owner, "compose_resource_fingerprint", "4" * 64)
                object.__setattr__(pins, "daemon_fingerprint", "3" * 64)
                object.__setattr__(pins, "endpoint", "unix:///changed/socket")
                object.__setattr__(compose, "compose_files", ("/changed/compose.yml",))
            return _daemon_result()
        if request.argv[5] == "compose":
            return _runtime_process_result(raw_compose)
        if request.argv[5] == "ps":
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        if request.argv[5] == "inspect":
            return _runtime_process_result(valid_inspect)
        raise AssertionError("unexpected bounded command")

    monkeypatch.setattr(process, "run_private_process", collect)
    result = docker.observe_owned_core_runtime(
        owner, pins, compose, deadline=_daemon_deadline()
    )

    assert result is not None
    assert result.daemon_fingerprint == pair.daemon_fingerprint
    assert result.resource_fingerprint == pair.resource_fingerprint
    assert owner.project_name == original_project
    assert owner.daemon_fingerprint == "3" * 64
    assert all(request.argv[:5] == original_prefix for request in calls)
    assert calls[3].argv[-1] == f"label=com.docker.compose.project={original_project}"
    assert calls[6].argv[-len(ids) :] == ids


def test_owned_core_runtime_preserves_private_collector_exception_identity(
    monkeypatch, compose_case, no_direct_docker_execution
):
    owner, pins, compose, _model, raw_compose, _evidence = compose_case
    failure = RuntimeError("private inventory collector diagnostic")
    calls = []

    def collect(request, *, deadline):
        calls.append(request)
        if request.argv[5] == "info":
            return _daemon_result()
        if request.argv[5] == "compose":
            return _runtime_process_result(raw_compose)
        if request.argv[5] == "ps":
            raise failure
        raise AssertionError("inventory must stop after the collector exception")

    monkeypatch.setattr(process, "run_private_process", collect)

    with pytest.raises(RuntimeError) as caught:
        docker.observe_owned_core_runtime(
            owner, pins, compose, deadline=_daemon_deadline()
        )

    assert caught.value is failure
    assert [request.argv[5] for request in calls] == [
        "info",
        "compose",
        "info",
        "ps",
    ]


def test_owned_core_runtime_refuses_expiry_after_project_wide_list(
    monkeypatch, compose_case, no_direct_docker_execution
):
    owner, pins, compose, _model, raw_compose, _evidence = compose_case
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(owner.selected_services) + 1)
    )
    clock = _DaemonClock()
    deadline = Deadline.after(10, clock=clock)
    calls = []

    def collect(request, *, deadline):
        calls.append(request)
        command = request.argv[5]
        if command == "info":
            return _daemon_result()
        if command == "compose":
            return _runtime_process_result(raw_compose)
        if command == "ps":
            clock.now = 10
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        raise AssertionError("expired inventory must not trigger inspect")

    monkeypatch.setattr(process, "run_private_process", collect)

    result = docker.observe_owned_core_runtime(owner, pins, compose, deadline=deadline)

    assert result is None
    assert [request.argv[5] for request in calls] == [
        "info",
        "compose",
        "info",
        "ps",
    ]


def test_owned_core_runtime_inspects_same_project_orphans_before_refusing(
    monkeypatch, compose_case, no_direct_docker_execution
):
    owner, pins, compose, _model, raw_compose, evidence = compose_case
    pair = _matched_runtime_metadata(owner, evidence)
    ids = tuple(
        _runtime_container_id(index)
        for index in range(1, len(pair.selected_services) + 2)
    )
    services = (*pair.selected_services, "orphaned-service")
    inspect_output = _runtime_inspect_output(pair, ids, services=services)
    calls = []

    def collect(request, *, deadline):
        calls.append((request, deadline))
        command = request.argv[5]
        if command == "info":
            return _daemon_result()
        if command == "compose":
            return _runtime_process_result(raw_compose)
        if command == "ps":
            return _runtime_process_result(
                b"\n".join(value.encode() for value in ids) + b"\n"
            )
        if command == "inspect":
            return _runtime_process_result(inspect_output)
        raise AssertionError("unexpected bounded command")

    monkeypatch.setattr(process, "run_private_process", collect)

    result = docker.observe_owned_core_runtime(
        owner, pins, compose, deadline=_daemon_deadline()
    )

    assert result is None
    assert [request.argv[5] for request, _deadline in calls] == [
        "info",
        "compose",
        "info",
        "ps",
        "info",
        "info",
        "inspect",
        "info",
    ]
    assert calls[3][0].argv[6] == "--all"
    assert (
        calls[3][0].argv[-1] == f"label=com.docker.compose.project={owner.project_name}"
    )
    assert calls[6][0].argv[-len(ids) :] == ids


@pytest.mark.parametrize(
    ("phase", "commands", "decoders"),
    [
        (
            "owner_pins",
            [],
            [],
        ),
        (
            "daemon",
            ["info"],
            ["daemon"],
        ),
        (
            "compose_prepare",
            ["info"],
            ["daemon"],
        ),
        (
            "compose_process",
            ["info", "compose"],
            ["daemon", "compose"],
        ),
        (
            "compose_decode",
            ["info", "compose"],
            ["daemon", "compose"],
        ),
        (
            "compose_binding",
            ["info", "compose"],
            ["daemon", "compose"],
        ),
        (
            "container_ids_prepare",
            ["info", "compose"],
            ["daemon", "compose"],
        ),
        (
            "container_ids_process",
            ["info", "compose", "info", "ps", "info"],
            ["daemon", "compose", "daemon", "daemon", "ids"],
        ),
        (
            "container_ids_decode",
            ["info", "compose", "info", "ps", "info"],
            ["daemon", "compose", "daemon", "daemon", "ids"],
        ),
        (
            "inspect_prepare",
            ["info", "compose", "info", "ps", "info"],
            ["daemon", "compose", "daemon", "daemon", "ids"],
        ),
        (
            "inspect_process",
            ["info", "compose", "info", "ps", "info", "info", "inspect", "info"],
            [
                "daemon",
                "compose",
                "daemon",
                "daemon",
                "ids",
                "daemon",
                "daemon",
                "inspect",
            ],
        ),
        (
            "inspect_decode",
            ["info", "compose", "info", "ps", "info", "info", "inspect", "info"],
            [
                "daemon",
                "compose",
                "daemon",
                "daemon",
                "ids",
                "daemon",
                "daemon",
                "inspect",
            ],
        ),
        (
            "runtime_binding",
            ["info", "compose", "info", "ps", "info", "info", "inspect", "info"],
            [
                "daemon",
                "compose",
                "daemon",
                "daemon",
                "ids",
                "daemon",
                "daemon",
                "inspect",
            ],
        ),
    ],
)
def test_owned_core_runtime_records_one_finite_failure_gate(
    monkeypatch, compose_case, no_direct_docker_execution, phase, commands, decoders
):
    from scripts.owned_nats_coordinator import (
        RuntimeObservationPhase,
        RuntimeObservationRecorder,
    )

    phase_by_name = {item.value: item for item in RuntimeObservationPhase}
    owner, pins, compose, _model, raw_compose, evidence = compose_case
    ids = tuple(
        _runtime_container_id(i) for i in range(1, len(owner.selected_services) + 1)
    )
    pair = _matched_runtime_metadata(owner, evidence)
    inspect_output = _runtime_inspect_output(pair, ids)
    clock = _DaemonClock()
    deadline = Deadline.after(10, clock=clock)
    recorder = RuntimeObservationRecorder()
    process_calls = []
    decoder_calls = []

    for name, attr in (
        ("daemon", "decode_daemon_read"),
        ("compose", "decode_compose_config"),
        ("ids", "decode_container_id_read"),
        ("inspect", "decode_container_inspect_reads"),
    ):
        real = getattr(docker, attr)

        def tracked(*args, _real=real, _name=name, **kwargs):
            decoder_calls.append(_name)
            result = _real(*args, **kwargs)
            if phase == "runtime_binding" and _name == "inspect":
                clock.now = 10
            return result

        monkeypatch.setattr(docker, attr, tracked)

    if phase == "owner_pins":
        pins = replace(pins, cwd="/not-the-owned-worktree")
    elif phase == "compose_prepare":
        monkeypatch.setattr(docker, "prepare_compose_config", lambda *_a, **_k: None)
    elif phase == "compose_binding":
        monkeypatch.setattr(docker, "compose_coordinator_metadata", lambda *_a: None)
    elif phase == "container_ids_prepare":
        monkeypatch.setattr(docker, "prepare_container_id_read", lambda *_a, **_k: None)
    elif phase == "inspect_prepare":
        monkeypatch.setattr(
            docker, "prepare_container_inspect_reads", lambda *_a, **_k: None
        )

    def collect(request, *, deadline):
        command = request.argv[5]
        process_calls.append(command)
        if command == "info":
            if phase == "daemon":
                return _daemon_result(stdout=b"different-daemon\n")
            return _daemon_result()
        if command == "compose":
            stdout = b"not-json" if phase == "compose_decode" else raw_compose
            result = _runtime_process_result(stdout)
            return (
                replace(result, returncode=1) if phase == "compose_process" else result
            )
        if command == "ps":
            stdout = (
                b"not-a-container-id\n"
                if phase == "container_ids_decode"
                else b"\n".join(value.encode() for value in ids) + b"\n"
            )
            result = _runtime_process_result(stdout)
            return (
                replace(result, returncode=1)
                if phase == "container_ids_process"
                else result
            )
        if command == "inspect":
            stdout = b"{}\n" if phase == "inspect_decode" else inspect_output
            result = _runtime_process_result(stdout)
            return (
                replace(result, returncode=1) if phase == "inspect_process" else result
            )
        raise AssertionError("unexpected private command")

    monkeypatch.setattr(process, "run_private_process", collect)
    result = docker.observe_owned_core_runtime(
        owner, pins, compose, deadline=deadline, diagnostic=recorder
    )

    assert result is None
    assert recorder.phase is phase_by_name[phase]
    assert process_calls == commands
    assert decoder_calls == decoders


def test_runtime_diagnostic_recorder_is_finite_private_and_resettable():
    from enum import StrEnum

    from scripts.owned_nats_coordinator import (
        RuntimeObservationPhase,
        RuntimeObservationRecorder,
    )

    assert issubclass(RuntimeObservationPhase, StrEnum)
    assert {phase.value for phase in RuntimeObservationPhase} == {
        "owner_pins",
        "daemon",
        "compose_prepare",
        "compose_process",
        "compose_decode",
        "compose_binding",
        "container_ids_prepare",
        "container_ids_process",
        "container_ids_decode",
        "inspect_prepare",
        "inspect_process",
        "inspect_decode",
        "runtime_binding",
        "inventory_invalid_selection",
        "inventory_invalid_identity",
        "inventory_invalid_runtime",
        "inventory_unhealthy",
    }
    recorder = RuntimeObservationRecorder()
    assert recorder.phase is None
    recorder.record(RuntimeObservationPhase.INSPECT_DECODE)
    assert recorder.phase is RuntimeObservationPhase.INSPECT_DECODE
    assert "inspect_decode" not in repr(recorder)
    recorder.reset()
    assert recorder.phase is None

    class OtherPhase(StrEnum):
        DAEMON = "daemon"

    class Hostile:
        def __str__(self):
            raise AssertionError("private value must not be formatted")

        def __repr__(self):
            raise AssertionError("private value must not be represented")

    for invalid in ("daemon", OtherPhase.DAEMON, 1, True, Hostile()):
        with pytest.raises(TypeError, match=r"^invalid runtime observation phase$"):
            recorder.record(invalid)
        assert recorder.phase is None
