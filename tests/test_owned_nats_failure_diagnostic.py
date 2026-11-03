from __future__ import annotations

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from scripts import owned_nats_failure_diagnostic as diagnostic
from scripts.owned_nats_coordinator import (
    BackendFailureCategory,
    BackendFailureDiagnostic,
    BackendFailureKind,
    RuntimeEvidence,
)
from scripts.owned_nats_process import PrivateProcessRequest, ProcessOutcome
from tests.test_owned_nats_transport_port import (
    _OWNER,
    _WORKER,
    _deadline,
    _port,
    _successful_process,
)


def _record(request_id: str, **changes: object) -> bytes:
    row = {
        "message": "request_failure_diagnostic",
        "logger": "app.core.request_failure_diagnostic",
        "diagnostic_request_id": request_id,
        "diagnostic_category": "database",
        "diagnostic_kind": "programming",
        "diagnostic_sqlstate": "42501",
    }
    row.update(changes)
    return json.dumps(row).encode() + b"\n"


def test_exact_projection_never_returns_correlation_or_other_fields() -> None:
    request_id = str(uuid4())
    private = "synthetic-private-request-and-exception"
    raw = _record(request_id)
    projected = diagnostic.project_backend_failure(raw, b"", request_id)
    assert projected == BackendFailureDiagnostic(
        BackendFailureCategory.DATABASE, BackendFailureKind.PROGRAMMING, "42501"
    )
    assert request_id not in repr(projected)
    assert private not in repr(projected)


@pytest.mark.parametrize(
    "changes",
    [
        {"exception": "synthetic-private"},
        {"headers": {"cookie": "synthetic-private"}},
        {"extra": None},
        {"message": "foreign"},
        {"logger": "foreign"},
        {"diagnostic_request_id": str(uuid4())},
        {"diagnostic_category": "synthetic-private"},
        {"diagnostic_kind": "synthetic-private"},
        {"diagnostic_kind": "response_validation"},
        {"diagnostic_sqlstate": "42501\nsynthetic-private"},
        {"diagnostic_sqlstate": {"private": "nested"}},
        {"diagnostic_category": ["database"]},
    ],
)
def test_untrusted_projection_is_unknown(changes: dict[str, object]) -> None:
    request_id = str(uuid4())
    assert (
        diagnostic.project_backend_failure(
            _record(request_id, **changes), b"", request_id
        )
        is None
    )


@pytest.mark.parametrize(
    "mode", ["duplicate", "truncated", "oversize", "duplicate-key", "nested"]
)
def test_ambiguous_or_unbounded_logs_are_unknown(mode: str) -> None:
    request_id = str(uuid4())
    raw = _record(request_id)
    if mode == "duplicate":
        raw += raw
    elif mode == "truncated":
        raw = raw[:-1]
    elif mode == "oversize":
        raw += b"x" * diagnostic._MAX_BYTES + b"\n"
    elif mode == "duplicate-key":
        raw += b'{"message": "x", "message": "y"}\n'
    else:
        raw += b'{"x":' + b"[" * 2000 + b"]" * 2000 + b"}\n"
    assert diagnostic.project_backend_failure(raw, b"", request_id) is None


def _collector(monkeypatch: pytest.MonkeyPatch, request_id: str):
    port = _port()
    backend = replace(_WORKER, service="backend")
    runtime = RuntimeEvidence(
        _OWNER.daemon_fingerprint, _OWNER.compose_resource_fingerprint, (backend,)
    )
    reads = []
    monkeypatch.setattr(
        diagnostic.docker, "observe_owned_core_runtime", lambda *args, **kwargs: runtime
    )
    prepared = PrivateProcessRequest(
        argv=("docker", "--config", "private", "--host", "private"),
        cwd="private",
        env={},
    )
    monkeypatch.setattr(
        diagnostic.docker, "prepare_daemon_read", lambda *args, **kwargs: prepared
    )

    def read(pins, request, *, deadline):
        reads.append(request)
        return _successful_process(_record(request_id))

    monkeypatch.setattr(diagnostic.docker, "_run_pinned_docker_process", read)
    return port, runtime, reads


def test_owned_collector_bounds_read_and_pins_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_id = str(uuid4())
    port, runtime, reads = _collector(monkeypatch, request_id)
    result = diagnostic.capture_backend_failure(
        _OWNER, port._docker_pins, port._compose_pins, request_id, deadline=_deadline()
    )
    assert result is not None
    assert len(reads) == 1
    assert reads[0].argv[-4:] == (
        "logs",
        "--tail",
        "64",
        runtime.containers[0].container_id,
    )
    assert reads[0].stdout_limit == reads[0].stderr_limit == diagnostic._MAX_BYTES
    assert request_id not in repr(result)


@pytest.mark.parametrize("mode", ["identity", "daemon", "timeout", "cleanup"])
def test_collector_failure_does_not_claim_root_cause(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    request_id = str(uuid4())
    port, runtime, _reads = _collector(monkeypatch, request_id)
    if mode in {"identity", "daemon"}:
        after = (
            replace(runtime, daemon_fingerprint="foreign")
            if mode == "daemon"
            else replace(
                runtime,
                containers=(replace(runtime.containers[0], identity="foreign"),),
            )
        )
        snapshots = iter((runtime, after))
        monkeypatch.setattr(
            diagnostic.docker,
            "observe_owned_core_runtime",
            lambda *args, **kwargs: next(snapshots),
        )
    else:
        result = _successful_process(_record(request_id))
        if mode == "timeout":
            result = replace(result, outcome=ProcessOutcome.TIMED_OUT)
        else:
            from scripts.owned_nats_process import LocalCleanup

            result = replace(result, local_cleanup=LocalCleanup.UNPROVEN)
        monkeypatch.setattr(
            diagnostic.docker,
            "_run_pinned_docker_process",
            lambda *args, **kwargs: result,
        )
    assert (
        diagnostic.capture_backend_failure(
            _OWNER,
            port._docker_pins,
            port._compose_pins,
            request_id,
            deadline=_deadline(),
        )
        is None
    )


@pytest.mark.parametrize("split", [False, True])
def test_combined_log_line_limit_is_enforced(split: bool) -> None:
    request_id = str(uuid4())
    raw = _record(request_id)
    unrelated = b"unrelated\n"
    if split:
        stdout, stderr = raw + unrelated * 31, unrelated * 32
    else:
        stdout, stderr = raw + unrelated * 63, b""
    assert diagnostic.project_backend_failure(stdout, stderr, request_id) is not None
    assert (
        diagnostic.project_backend_failure(stdout, stderr + unrelated, request_id)
        is None
    )


def test_missing_schema_field_is_unknown() -> None:
    request_id = str(uuid4())
    record = json.loads(_record(request_id))
    for key in tuple(record):
        incomplete = {name: value for name, value in record.items() if name != key}
        assert (
            diagnostic.project_backend_failure(
                json.dumps(incomplete).encode() + b"\n", b"", request_id
            )
            is None
        )


@pytest.mark.parametrize("depth", [31, 32, 33])
@pytest.mark.parametrize("top_level", ["object", "array"])
def test_json_depth_boundary_preserves_bounded_unrelated_logs(
    depth: int, top_level: str
) -> None:
    request_id = str(uuid4())
    if top_level == "object":
        unrelated = b'{"unrelated":' + b"[" * (depth - 1) + b"]" * (depth - 1) + b"}\n"
    else:
        unrelated = b"[" * depth + b"]" * depth + b"\n"
    projected = diagnostic.project_backend_failure(
        _record(request_id) + unrelated, b"", request_id
    )
    assert (projected is not None) is (depth <= 32)


@pytest.mark.parametrize("depth", [33, 2001])
def test_overdepth_is_rejected_before_decoder_regardless_of_recursion_limit(
    monkeypatch: pytest.MonkeyPatch, depth: int
) -> None:
    request_id = str(uuid4())

    # A decoder that never recurses must still never receive an overdepth row.
    def permissive_decoder(*args, **kwargs):
        pytest.fail("overdepth input reached the JSON decoder")

    monkeypatch.setattr(diagnostic.json, "loads", permissive_decoder)
    raw = b'{"unrelated":' + b"[" * (depth - 1) + b"]" * (depth - 1) + b"}\n"
    assert diagnostic.project_backend_failure(raw, b"", request_id) is None


@pytest.mark.parametrize(
    "text", ["[" * 2000, "]}" * 1000, '\\"' + "[" * 2000, "\\" * 4 + '"' + "[" * 2000]
)
def test_quoted_brackets_and_escapes_do_not_count_as_json_depth(text: str) -> None:
    request_id = str(uuid4())
    unrelated = json.dumps({"unrelated": text}).encode() + b"\n"
    assert (
        diagnostic.project_backend_failure(
            _record(request_id) + unrelated, b"", request_id
        )
        is not None
    )


def test_non_json_text_does_not_gain_json_depth_semantics() -> None:
    request_id = str(uuid4())
    unrelated = b"ordinary unrelated log: " + b"[" * 2000 + b"\n"
    assert (
        diagnostic.project_backend_failure(
            _record(request_id) + unrelated, b"", request_id
        )
        is not None
    )


@pytest.mark.parametrize(
    "encoding",
    [
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
    ],
)
@pytest.mark.parametrize("payload_kind", ["producer", "deep"])
def test_non_wire_encodings_fail_closed_before_json_decode(
    monkeypatch: pytest.MonkeyPatch, encoding: str, payload_kind: str
) -> None:
    request_id = str(uuid4())
    payload = (
        _record(request_id).decode().rstrip("\n")
        if payload_kind == "producer"
        else '{"unrelated":' + "[" * 2000 + "]" * 2000 + "}"
    )
    encoded = payload.encode(encoding) + b"\n"

    def forbidden_decoder(*args, **kwargs):
        pytest.fail("unsupported wire encoding reached JSON decoder")

    monkeypatch.setattr(diagnostic.json, "loads", forbidden_decoder)
    assert diagnostic.project_backend_failure(encoded, b"", request_id) is None


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16-be", "utf-32-le"])
def test_encoded_junk_cannot_leave_a_prior_correlated_claim(encoding: str) -> None:
    request_id = str(uuid4())
    raw = (
        _record(request_id)
        + ('{"unrelated":' + "[" * 2000 + "]" * 2000 + "}").encode(encoding)
        + b"\n"
    )
    assert diagnostic.project_backend_failure(raw, b"", request_id) is None


@pytest.mark.parametrize("key", ["diagnostic_request_id", "diagnostic_sqlstate"])
def test_duplicate_correlated_keys_are_rejected_in_both_orders(key: str) -> None:
    request_id = str(uuid4())
    raw = _record(request_id).rstrip(b"\n")
    original = request_id if key == "diagnostic_request_id" else "42501"
    wrong = str(uuid4()) if key == "diagnostic_request_id" else "UNKNOWN"
    for value in (original, wrong):
        extra = json.dumps(key).encode() + b":" + json.dumps(value).encode()
        for duplicated in (
            b"{" + extra + b"," + raw[1:],
            raw[:-1] + b"," + extra + b"}",
        ):
            assert (
                diagnostic.project_backend_failure(duplicated + b"\n", b"", request_id)
                is None
            )


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("framing", "projection_framing"),
        ("invalid", "projection_invalid"),
        ("unmatched", "projection_unmatched"),
        ("duplicate", "projection_ambiguous"),
    ],
)
def test_projection_failure_stage_is_finite_and_has_no_raw_evidence(mode, expected):
    from scripts.owned_nats_coordinator import BackendCaptureRecorder

    request_id = str(uuid4())
    raw = _record(request_id)
    if mode == "framing":
        raw = raw[:-1]
    elif mode == "invalid":
        raw += b'{"private": "synthetic-private"}\x00\n'
    elif mode == "unmatched":
        raw = _record(str(uuid4()))
    else:
        raw += raw
    recorder = BackendCaptureRecorder()
    assert (
        diagnostic.project_backend_failure(raw, b"", request_id, recorder=recorder)
        is None
    )
    assert recorder.stage.value == expected
    assert request_id not in repr(recorder)
    assert "synthetic-private" not in repr(recorder)


@pytest.mark.parametrize(
    "boundary", ["runtime_before", "log_prepare", "log_process", "runtime_after"]
)
def test_collector_records_exact_failed_boundary(monkeypatch, boundary):
    from scripts.owned_nats_coordinator import BackendCaptureRecorder

    request_id = str(uuid4())
    port, runtime, _reads = _collector(monkeypatch, request_id)
    if boundary == "runtime_before":
        monkeypatch.setattr(
            diagnostic.docker,
            "observe_owned_core_runtime",
            lambda *args, **kwargs: None,
        )
    elif boundary == "runtime_after":
        snapshots = iter((runtime, None))
        monkeypatch.setattr(
            diagnostic.docker,
            "observe_owned_core_runtime",
            lambda *args, **kwargs: next(snapshots),
        )
    elif boundary == "log_prepare":
        monkeypatch.setattr(
            diagnostic.docker, "prepare_daemon_read", lambda *args, **kwargs: None
        )
    else:
        result = replace(_successful_process(b""), outcome=ProcessOutcome.TIMED_OUT)
        monkeypatch.setattr(
            diagnostic.docker,
            "_run_pinned_docker_process",
            lambda *args, **kwargs: result,
        )
    recorder = BackendCaptureRecorder()
    assert (
        diagnostic.capture_backend_failure(
            _OWNER,
            port._docker_pins,
            port._compose_pins,
            request_id,
            deadline=_deadline(),
            recorder=recorder,
        )
        is None
    )
    assert recorder.stage.value == boundary


def test_capture_recorder_rejects_untrusted_stage_without_mutation() -> None:
    from scripts.owned_nats_coordinator import (
        BackendCaptureRecorder,
        BackendCaptureStage,
    )

    class Hostile:
        def __str__(self):
            pytest.fail("private object stringified")

        def __repr__(self):
            pytest.fail("private object rendered")

    recorder = BackendCaptureRecorder()
    recorder.record(BackendCaptureStage.LOG_PROCESS)
    for value in ("log_process", Hostile()):
        with pytest.raises(TypeError, match=r"^invalid backend capture stage$"):
            recorder.record(value)
        assert recorder.stage is BackendCaptureStage.LOG_PROCESS


def test_capture_stage_is_private_nonsemantic_constructor_extension() -> None:
    from dataclasses import fields

    from scripts.owned_nats_coordinator import (
        BackendCaptureStage,
        BackendFailureCategory,
        BackendFailureDiagnostic,
        BackendFailureKind,
    )

    original = BackendFailureDiagnostic(
        BackendFailureCategory.UNKNOWN, BackendFailureKind.UNKNOWN
    )
    three_arguments = BackendFailureDiagnostic(
        BackendFailureCategory.UNKNOWN, BackendFailureKind.UNKNOWN, "UNKNOWN"
    )
    annotated = replace(original, capture_stage=BackendCaptureStage.OWNER_AFTER)
    field = next(item for item in fields(original) if item.name == "capture_stage")
    assert field.repr is False
    assert field.compare is False
    assert original.capture_stage is None
    assert three_arguments.capture_stage is None
    assert original == three_arguments == annotated
    assert repr(original) == repr(annotated)
    assert "owner_after" not in repr(annotated)
