"""Pure signed-marker claims, not file provenance or runtime admission."""

from __future__ import annotations

import builtins
import copy
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts import live_nats_transport as transport
from scripts import live_stand
from scripts.owned_nats_coordinator import OwnerEvidence

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
