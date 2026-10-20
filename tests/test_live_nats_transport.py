"""No-I/O marker and daemon claims, not provenance or runtime admission."""

from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts import owned_nats_docker as docker
from scripts import owned_nats_process as process
from scripts.owned_nats_coordinator import OwnerEvidence
from scripts.owned_nats_outage import Deadline

_SIGNING_BYTES = bytes(range(32))


@pytest.fixture(autouse=True)
def no_output_or_legacy_io(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("pure marker parsing must not invoke legacy I/O")

    for name in (
        "_owner_signing_key",
        "load_stand_owner",
        "docker_daemon_fingerprint",
        "stand_lifecycle_lock",
    ):
        monkeypatch.setattr(live_stand, name, forbidden)
    yield
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.fixture
def owner_case(tmp_path):
    pins = {
        "pinned_repository": str(tmp_path / "repository"),
        "pinned_state_root": str(tmp_path / "ue-live-acceptance" / "run-parser"),
        "pinned_source_sha": "a" * 40,
    }
    ports = {
        name: 20_000 + index
        for index, (name, _service, _target) in enumerate(live_stand.LIVE_PORT_SPECS)
    }
    payload = {
        "version": 11,
        "repository": pins["pinned_repository"],
        "worktree": pins["pinned_state_root"],
        "project_name": "ue-live-0123456789abcdef",
        "published_ports": dict(live_stand._validate_published_ports(ports)),
        "daemon_fingerprint": "1" * 64,
        "compose_resource_fingerprint": "2" * 64,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": "core",
        "service_roots": list(live_stand.LIVE_CORE_SERVICE_ROOTS),
        "selected_services": list(live_stand.LIVE_CORE_EXPECTED_SERVICES),
        "source_sha": pins["pinned_source_sha"],
    }
    return payload, pins


def _legacy_marker(payload, signing_bytes=_SIGNING_BYTES):
    # The existing writer's canonical signer, independent of the new parser.
    data = {
        **payload,
        "signature": live_stand._owner_signature(payload, signing_bytes),
    }
    return json.dumps(data, indent=2).encode("utf-8")


def _parse(raw, pins, signing_bytes=_SIGNING_BYTES):
    attempted_io = []

    def forbidden(*_args, **_kwargs):
        attempted_io.append(True)
        raise AssertionError("pure marker parsing must not perform I/O")

    # Restore before pytest formats any failure or tears down temporary paths.
    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(io, "open", forbidden)
        for name in ("open", "stat", "lstat", "listdir", "scandir", "readlink"):
            guard.setattr(os, name, forbidden)
        for name in (
            "open",
            "read_bytes",
            "read_text",
            "resolve",
            "stat",
            "lstat",
            "exists",
            "is_file",
            "is_dir",
        ):
            guard.setattr(Path, name, forbidden)
        guard.setattr(subprocess, "run", forbidden)
        guard.setattr(subprocess, "Popen", forbidden)
        result = transport.parse_signed_owner_v11(raw, signing_bytes, **pins)

    # A production catch must not conceal an attempted I/O operation.
    assert attempted_io == []
    return result


def _assert_not_ready(result):
    assert result.status is transport.OwnerParseStatus.NOT_READY
    assert result.owner is None


@pytest.mark.parametrize("unicode_repository", [False, True])
def test_current_v11_payload_returns_only_signed_metadata(
    owner_case, unicode_repository
):
    payload, pins = owner_case
    if unicode_repository:
        payload["repository"] += "-проект"
        pins["pinned_repository"] = payload["repository"]
    raw = _legacy_marker(payload)

    result = _parse(raw, pins)

    assert result.status is transport.OwnerParseStatus.SIGNED_METADATA
    assert result.owner == OwnerEvidence(
        repository=pins["pinned_repository"],
        worktree=pins["pinned_state_root"],
        project_name=payload["project_name"],
        published_ports=live_stand._validate_published_ports(
            payload["published_ports"]
        ),
        schema_version=11,
        daemon_fingerprint="1" * 64,
        compose_resource_fingerprint="2" * 64,
        resume_compose_resource_fingerprint=None,
        resume_compose_resource_schema_version=None,
        source_sha=pins["pinned_source_sha"],
        stack="core",
        service_roots=live_stand.LIVE_CORE_SERVICE_ROOTS,
        selected_services=live_stand.LIVE_CORE_EXPECTED_SERVICES,
    )
    shown = repr(result)
    for private_value in (
        pins["pinned_repository"],
        pins["pinned_state_root"],
        payload["project_name"],
        json.loads(raw)["signature"],
        _SIGNING_BYTES.hex(),
    ):
        assert private_value not in shown


_SEMANTIC_MUTATIONS = (
    "old-schema",
    "bool-schema",
    "float-schema",
    "extra-field",
    "missing-field",
    "wrong-repository",
    "wrong-state",
    "wrong-source",
    "bad-project",
    "missing-port",
    "bool-port",
    "missing-daemon",
    "bad-daemon",
    "unbound-resources",
    "resume-fingerprint",
    "resume-schema",
    "full-stack",
    "missing-root",
    "missing-service",
    "duplicate-service",
)


@pytest.mark.parametrize("mutation", _SEMANTIC_MUTATIONS)
def test_resigned_invalid_metadata_is_rejected(owner_case, mutation):
    original, pins = owner_case
    payload = copy.deepcopy(original)
    first_port = live_stand.LIVE_PORT_SPECS[0][0]
    changes = {
        "old-schema": lambda: payload.update(version=10),
        "bool-schema": lambda: payload.update(version=True),
        "float-schema": lambda: payload.update(version=11.0),
        "extra-field": lambda: payload.update(unreviewed=True),
        "missing-field": lambda: payload.pop("stack"),
        "wrong-repository": lambda: payload.update(
            repository=pins["pinned_repository"] + "-other"
        ),
        "wrong-state": lambda: payload.update(
            worktree=pins["pinned_state_root"] + "-other"
        ),
        "wrong-source": lambda: payload.update(source_sha="b" * 40),
        "bad-project": lambda: payload.update(project_name="-invalid"),
        "missing-port": lambda: payload["published_ports"].pop(first_port),
        "bool-port": lambda: payload["published_ports"].update({first_port: True}),
        "missing-daemon": lambda: payload.update(daemon_fingerprint=None),
        "bad-daemon": lambda: payload.update(daemon_fingerprint="z" * 64),
        "unbound-resources": lambda: payload.update(compose_resource_fingerprint=None),
        "resume-fingerprint": lambda: payload.update(
            resume_compose_resource_fingerprint="3" * 64
        ),
        "resume-schema": lambda: payload.update(
            resume_compose_resource_schema_version=11
        ),
        "full-stack": lambda: payload.update(stack="full"),
        "missing-root": lambda: payload["service_roots"].pop(),
        "missing-service": lambda: payload["selected_services"].remove("nats"),
        "duplicate-service": lambda: payload["selected_services"].append("nats"),
    }
    changes[mutation]()

    _assert_not_ready(_parse(_legacy_marker(payload), pins))


@pytest.mark.parametrize(
    "signing_bytes",
    [b"x" * 31, b"x" * 33, b"x" * 32, "not-bytes"],
    ids=["short", "long", "wrong-key", "wrong-type"],
)
def test_wrong_supplied_key_is_rejected(owner_case, signing_bytes):
    payload, pins = owner_case
    _assert_not_ready(_parse(_legacy_marker(payload), pins, signing_bytes))


@pytest.mark.parametrize("kind", ["utf8", "json", "duplicate", "oversize", "type"])
def test_bad_marker_encoding_or_size_is_rejected(owner_case, kind):
    payload, pins = owner_case
    raw = _legacy_marker(payload)
    candidates = {
        "utf8": b"\xff",
        "json": b"{",
        "duplicate": b'{"version":11,' + raw[1:],
        "oversize": raw + b" " * (transport.MAX_OWNER_MARKER_BYTES + 1),
        "type": raw.decode("utf-8"),
    }
    _assert_not_ready(_parse(candidates[kind], pins))


def test_wrong_signature_is_rejected(owner_case):
    payload, pins = owner_case
    data = json.loads(_legacy_marker(payload))
    signature = data["signature"]
    data["signature"] = ("0" if signature[0] != "0" else "1") + signature[1:]
    _assert_not_ready(_parse(json.dumps(data).encode("utf-8"), pins))


@pytest.mark.parametrize(
    "pin, field, value",
    [
        ("pinned_repository", "repository", ""),
        ("pinned_repository", "repository", "relative/repository"),
        ("pinned_state_root", "worktree", "relative/state"),
        ("pinned_source_sha", "source_sha", "A" * 40),
    ],
    ids=[
        "empty-repository",
        "relative-repository",
        "relative-state",
        "uppercase-source",
    ],
)
def test_even_resigned_malformed_caller_pins_are_rejected(
    owner_case, pin, field, value
):
    payload, pins = owner_case
    payload[field] = value
    pins[pin] = value
    _assert_not_ready(_parse(_legacy_marker(payload), pins))


def test_nested_duplicate_published_port_key_is_rejected(owner_case):
    payload, pins = owner_case
    raw = _legacy_marker(payload)
    first_port = live_stand.LIVE_PORT_SPECS[0][0]
    needle = b'"published_ports": {'
    assert raw.count(needle) == 1
    duplicate = (
        needle
        + json.dumps(first_port).encode("utf-8")
        + b": "
        + str(payload["published_ports"][first_port]).encode("ascii")
        + b","
    )
    raw = raw.replace(needle, duplicate, 1)
    _assert_not_ready(_parse(raw, pins))


def test_valid_marker_at_exact_size_limit_is_accepted(owner_case):
    payload, pins = owner_case
    raw = _legacy_marker(payload)
    assert len(raw) < transport.MAX_OWNER_MARKER_BYTES
    bounded = raw + b" " * (transport.MAX_OWNER_MARKER_BYTES - len(raw))
    assert len(bounded) == transport.MAX_OWNER_MARKER_BYTES

    result = _parse(bounded, pins)

    assert result.status is transport.OwnerParseStatus.SIGNED_METADATA
    assert result.owner is not None
    assert result.owner.project_name == payload["project_name"]


@pytest.mark.parametrize("root", [b"[]", b"null", b"17", b'"marker"'])
def test_json_root_must_be_an_object(owner_case, root):
    _payload, pins = owner_case
    _assert_not_ready(_parse(root, pins))


@pytest.mark.parametrize(
    "field, value",
    [
        ("published_ports", []),
        ("published_ports", None),
        ("service_roots", {}),
        ("service_roots", "core"),
        ("selected_services", {}),
        ("selected_services", None),
    ],
    ids=[
        "ports-list",
        "ports-null",
        "roots-object",
        "roots-string",
        "services-object",
        "services-null",
    ],
)
def test_resigned_wrong_container_values_are_rejected(owner_case, field, value):
    payload, pins = owner_case
    payload[field] = value
    _assert_not_ready(_parse(_legacy_marker(payload), pins))


@pytest.mark.parametrize(
    "field, value",
    [
        ("repository", None),
        ("worktree", 17),
        ("project_name", []),
        ("daemon_fingerprint", {}),
        ("compose_resource_fingerprint", False),
        ("stack", None),
        ("source_sha", 42),
        ("signature", 3),
    ],
    ids=[
        "repository-null",
        "worktree-int",
        "project-list",
        "daemon-object",
        "resource-bool",
        "stack-null",
        "source-int",
        "signature-int",
    ],
)
def test_wrong_string_field_types_are_rejected(owner_case, field, value):
    payload, pins = owner_case
    if field == "signature":
        data = json.loads(_legacy_marker(payload))
        data["signature"] = value
        raw = json.dumps(data).encode("utf-8")
    else:
        payload[field] = value
        raw = _legacy_marker(payload)
    _assert_not_ready(_parse(raw, pins))


@pytest.mark.parametrize(
    "pin, value",
    [
        ("pinned_repository", None),
        ("pinned_repository", 17),
        ("pinned_state_root", []),
        ("pinned_state_root", False),
        ("pinned_source_sha", None),
        ("pinned_source_sha", 42),
    ],
    ids=[
        "repository-null",
        "repository-int",
        "state-list",
        "state-bool",
        "source-null",
        "source-int",
    ],
)
def test_wrong_caller_pin_types_are_rejected(owner_case, pin, value):
    payload, pins = owner_case
    raw = _legacy_marker(payload)
    pins[pin] = value
    _assert_not_ready(_parse(raw, pins))


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_json_numbers_are_rejected(owner_case, constant):
    payload, pins = owner_case
    raw = _legacy_marker(payload)
    first_port = live_stand.LIVE_PORT_SPECS[0][0]
    needle = (
        json.dumps(first_port).encode("utf-8")
        + b": "
        + str(payload["published_ports"][first_port]).encode("ascii")
    )
    replacement = json.dumps(first_port).encode("utf-8") + b": " + constant
    assert needle in raw
    raw = raw.replace(needle, replacement, 1)
    _assert_not_ready(_parse(raw, pins))


def test_deeply_nested_invalid_json_within_size_limit_is_rejected(owner_case):
    _payload, pins = owner_case
    raw = b"[" * 2_000 + b"0"
    assert len(raw) < transport.MAX_OWNER_MARKER_BYTES
    _assert_not_ready(_parse(raw, pins))


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


def _assert_daemon_not_ready(result):
    assert result == docker.DaemonMetadataResult(docker.DaemonMetadataStatus.NOT_READY)


@pytest.fixture
def daemon_no_process(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append("unexpected-process")
        raise AssertionError("daemon preparation and decoding must not execute")

    monkeypatch.setattr(process, "run_private_process", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    yield
    assert calls == []


@pytest.mark.parametrize("environment", [(), (("LC_ALL", "C"), ("LANG", "C.UTF-8"))])
def test_daemon_request_uses_only_explicit_pins(
    monkeypatch, daemon_no_process, environment
):
    monkeypatch.setenv("DOCKER_CONTEXT", "ambient-context")
    monkeypatch.setenv("DOCKER_HOST", "unix:///ambient-runtime/docker.sock")
    monkeypatch.setenv("COMPOSE_FILE", "/ambient-source/compose.yml")
    pins = replace(_daemon_pins(), environment=environment)

    request = docker.prepare_daemon_read(pins, deadline=_daemon_deadline())

    assert type(request) is process.PrivateProcessRequest
    assert request.argv == (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
        "info",
        "--format",
        "{{.ID}}",
    )
    assert request.cwd == pins.cwd
    assert type(request.env) is dict
    assert request.env == dict(environment)
    assert request.stdin == b""
    assert request.stdout_limit == 256
    assert request.stderr_limit == 1024
    assert request.input_limit == 0
    assert pins == replace(_daemon_pins(), environment=environment)
    request.env["LOCAL_TEST_CHANGE"] = "not-in-pins"
    assert pins.environment == environment


@pytest.mark.parametrize(
    "changes",
    [
        {"executable": "docker"},
        {"executable": "/owned-tools/../docker"},
        {"cwd": "relative-source"},
        {"config_directory": "/owned-state/\x00config"},
        {"endpoint": "ssh://host"},
        {"endpoint": "tcp://host:2375"},
        {"endpoint": "unix:///owned-runtime/../docker.sock"},
        {"daemon_fingerprint": "not-a-fingerprint"},
        {"environment": (("DOCKER_CONTEXT", "other"),)},
        {"environment": (("PATH", "/owned-tools"),)},
        {"environment": (("LANG", "unsupported-locale"),)},
        {"environment": (("LANG", "C"), ("LANG", "C"))},
        {"environment": [("LANG", "C")]},
    ],
)
def test_daemon_request_refuses_unsupported_pins(daemon_no_process, changes):
    pins = replace(_daemon_pins(), **changes)

    assert docker.prepare_daemon_read(pins, deadline=_daemon_deadline()) is None


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"], ids=["none", "lf", "crlf"])
def test_daemon_decode_matches_exact_private_metadata(daemon_no_process, ending):
    supplied = _daemon_result(stdout=_DAEMON_ID + ending)

    result = docker.decode_daemon_read(
        supplied,
        pinned_daemon=_DAEMON_FINGERPRINT,
        deadline=_daemon_deadline(),
    )

    assert result.status is docker.DaemonMetadataStatus.MATCHED_METADATA
    assert result.fingerprint == _DAEMON_FINGERPRINT
    assert _DAEMON_FINGERPRINT not in repr(result)
    assert _DAEMON_ID.decode() not in repr(result)


@pytest.mark.parametrize(
    "outcome",
    [
        process.ProcessOutcome.NOT_READY,
        process.ProcessOutcome.INVALID,
        process.ProcessOutcome.TIMED_OUT,
        process.ProcessOutcome.OUTPUT_LIMIT,
        process.ProcessOutcome.START_FAILED,
        process.ProcessOutcome.CONTAINMENT_UNAVAILABLE,
        process.ProcessOutcome.CLEANUP_UNCERTAIN,
    ],
)
def test_daemon_decode_refuses_nonexit_outcomes(daemon_no_process, outcome):
    result = docker.decode_daemon_read(
        _daemon_result(outcome=outcome),
        pinned_daemon=_DAEMON_FINGERPRINT,
        deadline=_daemon_deadline(),
    )

    _assert_daemon_not_ready(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"returncode": 1},
        {"returncode": None},
        {"returncode": False},
        {"local_cleanup": process.LocalCleanup.NOT_STARTED},
        {"local_cleanup": process.LocalCleanup.UNPROVEN},
        {"stderr": b"private-diagnostic"},
        {"stderr": b"x" * 1025},
        {"stdout": b"x" * 257},
        {"stdout": ""},
        {"stdout": b""},
        {"stdout": b"\xff"},
        {"stdout": _DAEMON_ID + b"\nextra"},
        {"stdout": b" " + _DAEMON_ID},
        {"stdout": _DAEMON_ID + b" "},
        {"stdout": _DAEMON_ID + b"\n\n"},
        {"stdout": _DAEMON_ID + b"\x00"},
    ],
)
def test_daemon_decode_refuses_process_or_payload_ambiguity(daemon_no_process, changes):
    result = docker.decode_daemon_read(
        _daemon_result(**changes),
        pinned_daemon=_DAEMON_FINGERPRINT,
        deadline=_daemon_deadline(),
    )

    _assert_daemon_not_ready(result)


@pytest.mark.parametrize("pin", ["f" * 64, "A" * 64, "", None])
def test_daemon_decode_refuses_missing_or_different_pin(daemon_no_process, pin):
    result = docker.decode_daemon_read(
        _daemon_result(), pinned_daemon=pin, deadline=_daemon_deadline()
    )

    _assert_daemon_not_ready(result)


@pytest.mark.parametrize("state", ["expired", "invalid", "regressed"])
def test_daemon_boundaries_refuse_unusable_deadline(daemon_no_process, state):
    clock = _DaemonClock()
    deadline = Deadline.after(0 if state == "invalid" else 10, clock=clock)
    if state == "expired":
        clock.now = 10
    elif state == "regressed":
        clock.now = -1

    assert docker.prepare_daemon_read(_daemon_pins(), deadline=deadline) is None
    result = docker.decode_daemon_read(
        _daemon_result(),
        pinned_daemon=_DAEMON_FINGERPRINT,
        deadline=deadline,
    )
    _assert_daemon_not_ready(result)


@pytest.mark.parametrize("operation", ["prepare", "decode"])
def test_daemon_boundaries_refuse_postcheck_expiry(daemon_no_process, operation):
    samples = iter((0.0, 0.0, 10.0))
    deadline = Deadline.after(10, clock=lambda: next(samples, 10.0))

    if operation == "prepare":
        assert docker.prepare_daemon_read(_daemon_pins(), deadline=deadline) is None
    else:
        result = docker.decode_daemon_read(
            _daemon_result(),
            pinned_daemon=_DAEMON_FINGERPRINT,
            deadline=deadline,
        )
        _assert_daemon_not_ready(result)


def test_daemon_boundaries_share_original_deadline(monkeypatch, daemon_no_process):
    clock = _DaemonClock()
    deadline = Deadline.after(10, clock=clock)

    def forbidden_deadline(*_args, **_kwargs):
        raise AssertionError("daemon boundaries must not create a fresh deadline")

    monkeypatch.setattr(Deadline, "after", forbidden_deadline)
    request = docker.prepare_daemon_read(_daemon_pins(), deadline=deadline)
    assert type(request) is process.PrivateProcessRequest

    clock.now = 10
    result = docker.decode_daemon_read(
        _daemon_result(),
        pinned_daemon=_DAEMON_FINGERPRINT,
        deadline=deadline,
    )
    _assert_daemon_not_ready(result)


def test_daemon_private_fields_are_not_represented():
    pins = _daemon_pins()
    rendered = repr(pins)
    for value in (
        pins.executable,
        pins.endpoint,
        pins.config_directory,
        pins.cwd,
        pins.daemon_fingerprint,
    ):
        assert value not in rendered
    result = docker.DaemonMetadataResult(
        docker.DaemonMetadataStatus.MATCHED_METADATA,
        _DAEMON_FINGERPRINT,
    )
    assert _DAEMON_FINGERPRINT not in repr(result)


def _mock_daemon_collection(monkeypatch, supplied, *, action=None):
    calls = []

    def collect(request, *, deadline):
        calls.append((request, deadline))
        if action is not None:
            action()
        return supplied

    monkeypatch.setattr(process, "run_private_process", collect)
    return calls


def _assert_one_daemon_collection(calls, deadline):
    pins = _daemon_pins()
    expected = process.PrivateProcessRequest(
        argv=(
            pins.executable,
            "--config",
            pins.config_directory,
            "--host",
            pins.endpoint,
            "info",
            "--format",
            "{{.ID}}",
        ),
        cwd=pins.cwd,
        env={},
        stdin=b"",
        stdout_limit=256,
        stderr_limit=1024,
        input_limit=0,
    )
    assert len(calls) == 1
    request, actual_deadline = calls[0]
    assert type(request) is process.PrivateProcessRequest
    assert request == expected
    assert actual_deadline is deadline


def test_daemon_observation_collects_exact_request_once(monkeypatch, daemon_no_process):
    deadline = _daemon_deadline()
    calls = _mock_daemon_collection(monkeypatch, _daemon_result())

    result = docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    _assert_one_daemon_collection(calls, deadline)
    assert result == docker.DaemonMetadataResult(
        docker.DaemonMetadataStatus.MATCHED_METADATA,
        _DAEMON_FINGERPRINT,
    )


@pytest.mark.parametrize(
    "pins",
    [
        pytest.param(None, id="none"),
        pytest.param(object(), id="wrong-class"),
        pytest.param(
            replace(_daemon_pins(), endpoint="ssh://host"),
            id="unsupported-endpoint",
        ),
        pytest.param(
            replace(_daemon_pins(), environment=(("DOCKER_CONTEXT", "other"),)),
            id="steering-environment",
        ),
    ],
)
def test_daemon_observation_refuses_pins_before_collection(
    monkeypatch, daemon_no_process, pins
):
    deadline = _daemon_deadline()
    calls = _mock_daemon_collection(monkeypatch, _daemon_result())

    result = docker.observe_daemon_metadata(pins, deadline=deadline)

    _assert_daemon_not_ready(result)
    assert calls == []


@pytest.mark.parametrize("state", ["expired", "invalid", "regressed"])
def test_daemon_observation_refuses_deadline_before_collection(
    monkeypatch, daemon_no_process, state
):
    clock = _DaemonClock()
    deadline = Deadline.after(0 if state == "invalid" else 10, clock=clock)
    if state == "expired":
        clock.now = 10
    elif state == "regressed":
        clock.now = -1
    calls = _mock_daemon_collection(monkeypatch, _daemon_result())

    result = docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    _assert_daemon_not_ready(result)
    assert calls == []


@pytest.mark.parametrize(
    "supplied",
    [
        pytest.param(None, id="wrong-result-class"),
        pytest.param(
            _daemon_result(outcome=process.ProcessOutcome.TIMED_OUT),
            id="timed-out",
        ),
        pytest.param(_daemon_result(returncode=False), id="boolean-returncode"),
        pytest.param(
            _daemon_result(local_cleanup=process.LocalCleanup.UNPROVEN),
            id="unproven-cleanup",
        ),
        pytest.param(_daemon_result(stdout=b"\xff"), id="invalid-utf8"),
        pytest.param(_daemon_result(stderr=b"private-diagnostic"), id="stderr"),
    ],
)
def test_daemon_observation_decodes_collected_result_fail_closed(
    monkeypatch, daemon_no_process, supplied
):
    deadline = _daemon_deadline()
    calls = _mock_daemon_collection(monkeypatch, supplied)

    result = docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    _assert_one_daemon_collection(calls, deadline)
    _assert_daemon_not_ready(result)


def test_daemon_observation_rejects_postcollection_expiry(
    monkeypatch, daemon_no_process
):
    clock = _DaemonClock()
    deadline = Deadline.after(10, clock=clock)

    def expire():
        clock.now = 10

    calls = _mock_daemon_collection(monkeypatch, _daemon_result(), action=expire)

    result = docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    _assert_one_daemon_collection(calls, deadline)
    _assert_daemon_not_ready(result)


@pytest.mark.parametrize("failure_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_daemon_observation_preserves_collector_exception_identity(
    monkeypatch, daemon_no_process, failure_type
):
    deadline = _daemon_deadline()
    failure = failure_type("private-collector-failure")

    def fail():
        raise failure

    calls = _mock_daemon_collection(monkeypatch, _daemon_result(), action=fail)

    with pytest.raises(failure_type) as caught:
        docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    assert caught.value is failure
    _assert_one_daemon_collection(calls, deadline)


@pytest.mark.parametrize(
    "return_original", [True, False], ids=["original", "substituted"]
)
def test_daemon_observation_retains_precollection_fingerprint(
    monkeypatch, daemon_no_process, return_original
):
    pins = _daemon_pins()
    deadline = _daemon_deadline()
    substituted_id = b"substituted-daemon-fixture"
    substituted_fingerprint = hashlib.sha256(substituted_id).hexdigest()
    supplied_id = _DAEMON_ID if return_original else substituted_id

    def mutate_pin():
        object.__setattr__(pins, "daemon_fingerprint", substituted_fingerprint)

    calls = _mock_daemon_collection(
        monkeypatch,
        _daemon_result(stdout=supplied_id + b"\n"),
        action=mutate_pin,
    )

    result = docker.observe_daemon_metadata(pins, deadline=deadline)

    _assert_one_daemon_collection(calls, deadline)
    assert pins.daemon_fingerprint == substituted_fingerprint
    if return_original:
        assert result == docker.DaemonMetadataResult(
            docker.DaemonMetadataStatus.MATCHED_METADATA,
            _DAEMON_FINGERPRINT,
        )
    else:
        _assert_daemon_not_ready(result)


def test_daemon_observation_never_refreshes_deadline(monkeypatch, daemon_no_process):
    deadline = _daemon_deadline()
    calls = _mock_daemon_collection(monkeypatch, _daemon_result())
    fresh_deadlines = []

    def forbidden_deadline(*_args, **_kwargs):
        fresh_deadlines.append("unexpected-fresh-deadline")
        raise AssertionError("daemon observation must retain its caller deadline")

    monkeypatch.setattr(Deadline, "after", forbidden_deadline)

    result = docker.observe_daemon_metadata(_daemon_pins(), deadline=deadline)

    assert fresh_deadlines == []
    _assert_one_daemon_collection(calls, deadline)
    assert result.status is docker.DaemonMetadataStatus.MATCHED_METADATA
    assert result.fingerprint == _DAEMON_FINGERPRINT


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


def _compose_call(function, *args, **kwargs):
    attempted = []

    def forbidden(*_args, **_kwargs):
        attempted.append(True)
        raise AssertionError("Compose preparation and decoding must perform no I/O")

    class ForbiddenEnvironment:
        __getitem__ = forbidden
        __iter__ = forbidden
        __len__ = forbidden
        __contains__ = forbidden
        get = forbidden
        keys = forbidden
        items = forbidden
        values = forbidden
        copy = forbidden

    try:
        with pytest.MonkeyPatch.context() as guard:
            guard.setattr(builtins, "open", forbidden)
            guard.setattr(io, "open", forbidden)
            guard.setattr(os, "environ", ForbiddenEnvironment())
            guard.setattr(os, "getenv", forbidden)
            for name in (
                "open",
                "stat",
                "lstat",
                "listdir",
                "scandir",
                "readlink",
                "system",
                "mkdir",
                "makedirs",
                "remove",
                "unlink",
                "rename",
                "replace",
            ):
                guard.setattr(os, name, forbidden)
            for name in (
                "open",
                "read_bytes",
                "read_text",
                "write_bytes",
                "write_text",
                "resolve",
                "stat",
                "lstat",
                "exists",
                "is_file",
                "is_dir",
                "mkdir",
                "unlink",
            ):
                guard.setattr(Path, name, forbidden)
            guard.setattr(subprocess, "run", forbidden)
            guard.setattr(subprocess, "Popen", forbidden)
            guard.setattr(process, "run_private_process", forbidden)
            guard.setattr(Deadline, "after", forbidden)
            guard.setattr(Deadline, "child", forbidden)
            for name in (
                "compose_command",
                "compose_control_environment",
                "_compose_resource_evidence",
                "docker_daemon_fingerprint",
                "load_stand_owner",
                "stand_lifecycle_lock",
            ):
                guard.setattr(live_stand, name, forbidden)
            return function(*args, **kwargs)
    finally:
        assert attempted == []


def _assert_compose_not_ready(result):
    assert result == docker.ComposeMetadataResult(
        docker.ComposeMetadataStatus.NOT_READY
    )


def test_compose_request_uses_exact_in_place_pins_and_private_environment(compose_case):
    owner, pins, compose, _model, _raw, _evidence = compose_case
    deadline = _daemon_deadline()

    request = _compose_call(
        docker.prepare_compose_config, owner, pins, compose, deadline=deadline
    )

    assert type(request) is process.PrivateProcessRequest
    assert request.argv == (
        pins.executable,
        "--config",
        pins.config_directory,
        "--host",
        pins.endpoint,
        "compose",
        "--project-directory",
        owner.repository,
        "-p",
        owner.project_name,
        "--env-file",
        compose.env_file,
        "-f",
        compose.compose_files[0],
        "-f",
        compose.compose_files[1],
        "-f",
        compose.compose_files[2],
        "config",
        "--format",
        "json",
    )
    expected_env = {
        "LC_ALL": "C",
        "COMPOSE_PROJECT_NAME": owner.project_name,
        "LIVE_BASE_URL": "http://localhost:20012",
        "LIVE_VAPID_PUBLIC_KEY": "live-stand-inspection-placeholder",
        "LIVE_VAPID_PRIVATE_KEY": "live-stand-inspection-placeholder",
        "TRUSTED_PROXIES": "",
        "GATEWAY_TRUSTED_PROXIES": "",
        "WS_HUB_TRUSTED_PROXIES": "",
        "LIVE_STAND_STATE_ROOT": owner.worktree,
        "LIVE_STAND_SOURCE_SHA": "a" * 40,
    }
    for name, port in owner.published_ports:
        key = "LIVE_MAILPIT_PORT" if name == "MAILPIT" else f"LIVE_HOST_PORT_{name}"
        expected_env[key] = str(port)
    assert type(request.env) is dict
    assert request.env == expected_env
    assert request.cwd == owner.worktree
    assert request.stdin == b""
    assert request.stdout_limit == 1_048_576
    assert request.stderr_limit == 16_384
    assert request.input_limit == 0
    assert pins.environment == (("LC_ALL", "C"),)
    assert deadline.expires_at == 10
    assert owner.worktree not in repr(compose)


def test_compose_decode_matches_independent_resource_projection(compose_case):
    owner, _pins, _compose, model, raw, evidence = compose_case
    before = copy.deepcopy(model)
    supplied = _daemon_result(stdout=raw)
    deadline = _daemon_deadline()

    result = _compose_call(
        docker.decode_compose_config, supplied, owner=owner, deadline=deadline
    )

    assert result.status is docker.ComposeMetadataStatus.MATCHED_METADATA
    assert result.evidence == evidence
    assert model == before
    assert supplied.stdout == raw
    assert deadline.expires_at == 10
    for private_value in (
        owner.project_name,
        owner.compose_resource_fingerprint,
        "private-compose-config-fixture",
        "private-compose-label-fixture",
    ):
        assert private_value not in repr(result)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-class",
        "bool-schema",
        "full-stack",
        "resume",
        "selection",
        "bool-port",
        "duplicate-port-name",
        "privileged-port",
    ],
)
def test_compose_boundaries_refuse_unadmitted_owner(compose_case, mutation):
    owner, pins, compose, _model, raw, _evidence = compose_case
    first_name, _first_port = owner.published_ports[0]
    changes = {
        "bool-schema": {"schema_version": True},
        "full-stack": {"stack": "full"},
        "resume": {"resume_compose_resource_fingerprint": "b" * 64},
        "selection": {"selected_services": owner.selected_services[:-1]},
        "bool-port": {
            "published_ports": ((first_name, True), *owner.published_ports[1:])
        },
        "duplicate-port-name": {
            "published_ports": (*owner.published_ports, owner.published_ports[0])
        },
        "privileged-port": {
            "published_ports": ((first_name, 80), *owner.published_ports[1:])
        },
    }
    invalid = (
        object() if mutation == "wrong-class" else replace(owner, **changes[mutation])
    )

    assert (
        _compose_call(
            docker.prepare_compose_config,
            invalid,
            pins,
            compose,
            deadline=_daemon_deadline(),
        )
        is None
    )
    result = _compose_call(
        docker.decode_compose_config,
        _daemon_result(stdout=raw),
        owner=invalid,
        deadline=_daemon_deadline(),
    )
    _assert_compose_not_ready(result)


@pytest.mark.parametrize(
    "mutation",
    ["project-directory", "env-file", "file-order", "missing-file", "cwd", "daemon"],
)
def test_compose_prepare_refuses_unreviewed_layout(compose_case, mutation):
    owner, pins, compose, _model, _raw, _evidence = compose_case
    if mutation == "project-directory":
        compose = replace(compose, project_directory="/another-repository")
    elif mutation == "env-file":
        compose = replace(compose, env_file=f"{owner.repository}/.env.docker")
    elif mutation == "file-order":
        compose = replace(compose, compose_files=tuple(reversed(compose.compose_files)))
    elif mutation == "missing-file":
        compose = replace(compose, compose_files=compose.compose_files[:-1])
    elif mutation == "cwd":
        pins = replace(pins, cwd=owner.repository)
    else:
        pins = replace(pins, daemon_fingerprint="b" * 64)

    assert (
        _compose_call(
            docker.prepare_compose_config,
            owner,
            pins,
            compose,
            deadline=_daemon_deadline(),
        )
        is None
    )


@pytest.mark.parametrize("mutation", ["nonexit", "cleanup", "stderr", "oversize"])
def test_compose_decode_refuses_process_evidence(compose_case, mutation):
    owner, _pins, _compose, _model, raw, _evidence = compose_case
    changes = {
        "nonexit": {"outcome": process.ProcessOutcome.TIMED_OUT},
        "cleanup": {"local_cleanup": process.LocalCleanup.UNPROVEN},
        "stderr": {"stderr": b"private-compose-error"},
        "oversize": {"stdout": b" " * 1_048_577},
    }
    supplied = replace(_daemon_result(stdout=raw), **changes[mutation])

    result = _compose_call(
        docker.decode_compose_config,
        supplied,
        owner=owner,
        deadline=_daemon_deadline(),
    )

    _assert_compose_not_ready(result)


@pytest.mark.parametrize(
    "mutation",
    [
        "root",
        "duplicate-root",
        "duplicate-nested",
        "nan",
        "overflow",
        "utf8",
        "trailing",
        "resource-drift",
    ],
)
def test_compose_decode_refuses_ambiguous_or_different_json(compose_case, mutation):
    owner, _pins, _compose, model, raw, _evidence = compose_case
    if mutation == "root":
        raw = b"[]"
    elif mutation == "duplicate-root":
        raw = b'{"name":"other",' + raw[1:]
    elif mutation == "duplicate-nested":
        raw = raw.replace(
            b'"PRIVATE_CONFIG":',
            b'"PRIVATE_CONFIG":"duplicate","PRIVATE_CONFIG":',
            1,
        )
    elif mutation == "nan":
        raw = b'{"unselected_private_number":NaN,' + raw[1:]
    elif mutation == "overflow":
        raw = b'{"unselected_private_number":1e999,' + raw[1:]
    elif mutation == "utf8":
        raw = b"\xff" + raw
    elif mutation == "trailing":
        raw += b"{}"
    else:
        model["services"]["backend"]["volumes"][0]["target"] = "/other/data"
        raw = json.dumps(model).encode("utf-8")

    result = _compose_call(
        docker.decode_compose_config,
        _daemon_result(stdout=raw),
        owner=owner,
        deadline=_daemon_deadline(),
    )

    _assert_compose_not_ready(result)


@pytest.mark.parametrize("operation", ["prepare", "decode"])
@pytest.mark.parametrize("expiry", ["before", "during"])
def test_compose_boundaries_keep_the_shared_deadline(compose_case, operation, expiry):
    owner, pins, compose, _model, raw, _evidence = compose_case
    samples = iter((0.0, 11.0) if expiry == "before" else (0.0, 0.0, 11.0))
    deadline = Deadline.after(10, clock=samples.__next__)

    if operation == "prepare":
        result = _compose_call(
            docker.prepare_compose_config, owner, pins, compose, deadline=deadline
        )
        assert result is None
    else:
        result = _compose_call(
            docker.decode_compose_config,
            _daemon_result(stdout=raw),
            owner=owner,
            deadline=deadline,
        )
        _assert_compose_not_ready(result)
