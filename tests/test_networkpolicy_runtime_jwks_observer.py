"""Offline contracts for the optional positive JWKS observer."""

from __future__ import annotations

import importlib
import io
import json
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/k8s"))

EPOCH = "0123456789abcdef"
UIDS = [
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002",
]
PEERS = {"10.244.0.1": UIDS[0], "10.244.0.2": UIDS[1]}
KIDS = ["primary", "netpol-rotated"]
REQUEST = b"GET /.well-known/jwks.json HTTP/1.1\r\nAuthorization: secret-canary\r\n\r\n"
DOCUMENT = json.dumps(
    {"keys": [{"kid": kid, "n": "public-key-canary"} for kid in KIDS]}
).encode()


def load_program(source, path):
    path.write_text(source, encoding="utf-8")
    namespace = runpy.run_path(str(path))
    return namespace["arm_jwks_witness"].__globals__


def test_positive_witness_program_is_available():
    standins = importlib.import_module("networkpolicy_runtime_standins")
    assert hasattr(standins, "JWKS_WITNESS_COMMON_SRC")


@pytest.fixture
def witness(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    assert namespace["arm_jwks_witness"](
        {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    )
    return namespace


def test_records_two_known_positive_responses_without_sensitive_contents(witness):
    for peer in PEERS:
        witness["record_jwks_witness"](REQUEST, DOCUMENT, peer, 8000)
    result = witness["read_jwks_witness"](EPOCH, UIDS)
    assert result["result"] == "observed"
    assert {event["pod_uid"] for event in result["events"]} == set(UIDS)
    assert all(
        event["status"] == 200 and event["key_ids"] == KIDS
        for event in result["events"]
    )
    assert "secret-canary" not in json.dumps(result)
    assert "public-key-canary" not in json.dumps(result)
    assert all(peer not in json.dumps(result) for peer in PEERS)


def test_each_uid_keeps_only_its_first_positive_event(witness):
    witness["record_jwks_witness"](REQUEST, DOCUMENT, "10.244.0.1", 8000)
    path = Path(witness["_WITNESS_DIR"]) / EPOCH / f"{UIDS[0]}.json"
    first = path.read_bytes()
    witness["record_jwks_witness"](REQUEST, DOCUMENT, "10.244.0.1", 8000)
    assert path.read_bytes() == first


def test_exact_read_program_returns_only_sanitized_two_event_snapshot(
    witness, monkeypatch
):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    for peer in PEERS:
        witness["record_jwks_witness"](REQUEST, DOCUMENT, peer, 8000)
    code = standins.JWKS_WITNESS_READ_SRC.replace(
        '"/tmp/netpol-jwks-witness"', repr(witness["_WITNESS_DIR"])
    )
    incoming = json.dumps({"epoch": EPOCH, "uids": UIDS}).encode()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(incoming)))
    output = io.StringIO()
    script = Path(witness["_WITNESS_DIR"]).parent / "reader.py"
    script.write_text(code, encoding="utf-8")
    with redirect_stdout(output):
        runpy.run_path(str(script))
    result = json.loads(output.getvalue())
    assert result["result"] == "observed"
    assert {event["pod_uid"] for event in result["events"]} == set(UIDS)
    assert "secret-canary" not in output.getvalue()
    assert "public-key-canary" not in output.getvalue()
    assert all(peer not in output.getvalue() for peer in PEERS)


@pytest.mark.parametrize(
    "raw_request,document,peer,port",
    [
        (b"GET /other HTTP/1.1\r\n\r\n", DOCUMENT, "10.244.0.1", 8000),
        (b"POST /.well-known/jwks.json HTTP/1.1\r\n\r\n", DOCUMENT, "10.244.0.1", 8000),
        (REQUEST, DOCUMENT, "10.244.0.99", 8000),
        (REQUEST, DOCUMENT, "10.244.0.1", 9000),
        (REQUEST, b'{"keys":[{"kid":"primary"}]}', "10.244.0.1", 8000),
        (REQUEST, b"not-json", "10.244.0.1", 8000),
    ],
)
def test_other_traffic_is_not_recorded(witness, raw_request, document, peer, port):
    witness["record_jwks_witness"](raw_request, document, peer, port)
    assert witness["read_jwks_witness"](EPOCH, UIDS) == {"result": "unavailable"}


def test_ambiguous_peer_mapping_is_never_armed(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    assert not namespace["arm_jwks_witness"](
        {
            "epoch": EPOCH,
            "peers": {"10.244.0.1": UIDS[0], "10.244.0.2": UIDS[0]},
            "key_ids": KIDS,
        }
    )


def test_publisher_failure_to_arm_does_not_change_publication(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    namespace["_JWKS_PATH"] = str(tmp_path / "jwks.json")
    (tmp_path / "jwks.json").write_text(json.dumps({"keys": [{"kid": "primary"}]}))
    observer = {
        "epoch": EPOCH,
        "peers": {"10.244.0.1": UIDS[0], "10.244.0.2": UIDS[0]},
        "key_ids": KIDS,
    }
    result = namespace["publish_jwks_document"](DOCUMENT, observer)
    assert result == {"result": "published", "observer": {"status": "unavailable"}}
    assert (tmp_path / "jwks.json").read_bytes() == DOCUMENT


def test_publisher_exception_while_arming_does_not_change_publication(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_JWKS_PATH"] = str(tmp_path / "jwks.json")
    (tmp_path / "jwks.json").write_text(json.dumps({"keys": [{"kid": "primary"}]}))

    def failed_arm(observer):
        raise OSError("sensitive-canary")

    namespace["arm_jwks_witness"] = failed_arm
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    result = namespace["publish_jwks_document"](DOCUMENT, observer)
    assert result == {"result": "published", "observer": {"status": "unavailable"}}
    assert (tmp_path / "jwks.json").read_bytes() == DOCUMENT


def test_publisher_clock_failure_does_not_change_publication(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    namespace["_JWKS_PATH"] = str(tmp_path / "jwks.json")
    (tmp_path / "jwks.json").write_text(json.dumps({"keys": [{"kid": "primary"}]}))

    def failed_clock():
        raise OSError("sensitive-canary")

    namespace["time"] = SimpleNamespace(monotonic_ns=failed_clock)
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    result = namespace["publish_jwks_document"](DOCUMENT, observer)
    assert result == {"result": "published", "observer": {"status": "unavailable"}}
    assert (tmp_path / "jwks.json").read_bytes() == DOCUMENT


def test_observer_publication_marker_precedes_an_immediate_positive_response(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    namespace["_JWKS_PATH"] = str(tmp_path / "jwks.json")
    (tmp_path / "jwks.json").write_text(json.dumps({"keys": [{"kid": "primary"}]}))
    original_atomic = namespace["_witness_publish_bytes"]

    def immediate_response(path, value):
        original_atomic(path, value)
        if path == namespace["_JWKS_PATH"]:
            for peer in PEERS:
                namespace["record_jwks_witness"](REQUEST, DOCUMENT, peer, 8000)

    namespace["_witness_publish_bytes"] = immediate_response
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    result = namespace["publish_jwks_document"](DOCUMENT, observer)
    events = namespace["read_jwks_witness"](EPOCH, UIDS)["events"]
    assert all(
        result["observer"]["publication_lower_bound_ns"] < event["monotonic_ns"]
        for event in events
    )


def test_existing_overlap_document_cannot_arm_an_observer(tmp_path):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(standins.JWKS_WITNESS_COMMON_SRC, tmp_path / "common.py")
    namespace["_WITNESS_DIR"] = str(tmp_path / "witness")
    namespace["_JWKS_PATH"] = str(tmp_path / "jwks.json")
    (tmp_path / "jwks.json").write_bytes(DOCUMENT)
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    result = namespace["publish_jwks_document"](DOCUMENT, observer)
    assert result == {"result": "published", "observer": {"status": "unavailable"}}


def test_exact_publisher_program_arms_and_publishes_without_echoing_input(
    tmp_path, monkeypatch
):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    directory = str(tmp_path / "witness")
    jwks_path = str(tmp_path / "jwks.json")
    Path(jwks_path).write_text(json.dumps({"keys": [{"kid": "primary"}]}))
    code = standins.PUBLISH_SRC.replace('"/tmp/netpol-jwks-witness"', repr(directory))
    code = code.replace('"/tmp/jwks.json"', repr(jwks_path))
    payload = {
        "document": DOCUMENT.decode(),
        "observer": {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS},
    }
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    monkeypatch.setattr(sys, "argv", ["publisher", "observe"])
    output = io.StringIO()
    script = tmp_path / "publisher.py"
    script.write_text(code, encoding="utf-8")
    with redirect_stdout(output):
        runpy.run_path(str(script))
    result = json.loads(output.getvalue())
    assert result["result"] == "published"
    assert result["observer"]["status"] == "armed"
    assert Path(jwks_path).read_bytes() == DOCUMENT
    assert "public-key-canary" not in output.getvalue()
    assert all(peer not in output.getvalue() for peer in PEERS)


def test_unobserved_publisher_preserves_original_document_bytes(tmp_path, monkeypatch):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    path = tmp_path / "jwks.json"
    code = standins.PUBLISH_SRC.replace('"/tmp/jwks.json"', repr(str(path)))
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(DOCUMENT)))
    monkeypatch.setattr(sys, "argv", ["publisher"])
    output = io.StringIO()
    script = tmp_path / "publisher.py"
    script.write_text(code, encoding="utf-8")
    with redirect_stdout(output):
        runpy.run_path(str(script))
    assert json.loads(output.getvalue()) == {"result": "published"}
    assert path.read_bytes() == DOCUMENT


def test_observed_publication_uses_the_existing_single_publisher_call(monkeypatch):
    app = importlib.import_module("networkpolicy_runtime_app")
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return {"result": "published"}

    monkeypatch.setattr(app, "run_in_pod", fake_run)
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    assert app.publish_jwks(object(), DOCUMENT.decode(), observer=observer) == {
        "result": "published"
    }
    assert len(calls) == 1
    payload = json.loads(calls[0][1]["stdin"])
    assert payload["document"] == DOCUMENT.decode()
    assert payload["observer"] == observer


def test_unserializable_observer_falls_back_to_one_normal_publication(monkeypatch):
    app = importlib.import_module("networkpolicy_runtime_app")
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return {"result": "published"}

    monkeypatch.setattr(app, "run_in_pod", fake_run)
    assert app.publish_jwks(
        object(), DOCUMENT.decode(), observer={"invalid": object()}
    ) == {"result": "published"}
    assert len(calls) == 1
    assert calls[0][0][2] == []
    assert calls[0][1]["stdin"] == DOCUMENT.decode()


def test_listener_does_not_record_failed_send(witness):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    prefix = standins.LISTENER_SRC.split("for port in [int(p)", 1)[0]
    namespace = load_program(
        prefix, Path(witness["_WITNESS_DIR"]).parent / "listener.py"
    )
    namespace["_WITNESS_DIR"] = witness["_WITNESS_DIR"]
    namespace["document"] = lambda: DOCUMENT

    class FailedConnection:
        def settimeout(self, timeout):
            pass

        def recv(self, limit):
            return REQUEST

        def sendall(self, data):
            raise OSError("sensitive-canary")

        def close(self):
            pass

    namespace["handle"](FailedConnection(), "10.244.0.1", 8000)
    assert witness["read_jwks_witness"](EPOCH, UIDS) == {"result": "unavailable"}


def test_listener_does_not_expose_observer_errors_after_success(witness, capsys):
    standins = importlib.import_module("networkpolicy_runtime_standins")
    namespace = load_program(
        standins.LISTENER_SRC.split("for port in [int(p)", 1)[0],
        Path(witness["_WITNESS_DIR"]).parent / "listener.py",
    )
    namespace["document"] = lambda: DOCUMENT

    def broken_observer(*args):
        raise RuntimeError("secret-canary")

    namespace["record_jwks_witness"] = broken_observer

    class SentConnection:
        def settimeout(self, timeout):
            pass

        def recv(self, limit):
            return REQUEST

        def sendall(self, data):
            assert data.startswith(b"HTTP/1.1 200 OK")

        def close(self):
            pass

    namespace["handle"](SentConnection(), "10.244.0.1", 8000)
    assert "secret-canary" not in capsys.readouterr().err


def auth_checks():
    return [
        {
            "check_id": check_id,
            "pod_uid": uid,
            "verdict": "pass",
            "expected": code,
            "observed": {"result": "grpc-status", "code": code},
        }
        for check_id, code in (
            ("unpublished-new-rejected", "Unauthenticated"),
            ("overlap-old-accepted", "InvalidArgument"),
            ("overlap-new-accepted", "InvalidArgument"),
        )
        for uid in UIDS
    ]


def observed_events():
    return {
        "result": "observed",
        "events": [
            {
                "pod_uid": uid,
                "epoch": EPOCH,
                "status": 200,
                "key_ids": KIDS,
                "monotonic_ns": 101,
            }
            for uid in UIDS
        ],
        "collected_monotonic_ns": 102,
    }


def test_observation_binds_publication_before_both_successful_authentications():
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    published = {"status": "armed", "publication_lower_bound_ns": 100}
    result = real_fp.jwks_observer_verdict(
        observer, published, observed_events(), auth_checks(), True
    )
    assert result["verdict"] == "pass"
    assert "before/after" in result["scope"]
    assert {event["pod_uid"] for event in result["events"]} == set(UIDS)
    assert all(peer not in json.dumps(result) for peer in PEERS)


@pytest.mark.parametrize(
    "fault",
    [
        "unpublished",
        "auth",
        "old_control",
        "uid",
        "epoch",
        "status",
        "kid",
        "ordering",
        "restart",
        "extra",
        "extra_top_level",
    ],
)
def test_observation_is_inconclusive_for_unmatched_or_unordered_evidence(fault):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    published = {"status": "armed", "publication_lower_bound_ns": 100}
    observation, checks, unchanged = observed_events(), auth_checks(), True
    if fault == "unpublished":
        checks[0]["verdict"] = "fail"
    elif fault == "auth":
        checks[-1]["observed"]["code"] = "Unauthenticated"
    elif fault == "old_control":
        checks[2]["verdict"] = "fail"
    elif fault == "uid":
        observation["events"][0]["pod_uid"] = UIDS[1]
    elif fault == "epoch":
        observation["events"][0]["epoch"] = "ffffffffffffffff"
    elif fault == "status":
        observation["events"][0]["status"] = 403
    elif fault == "kid":
        observation["events"][0]["key_ids"] = ["primary"]
    elif fault == "ordering":
        observation["events"][0]["monotonic_ns"] = 100
    elif fault == "restart":
        unchanged = False
    elif fault == "extra_top_level":
        observation["raw"] = "secret-canary"
    else:
        observation["events"][0]["raw"] = "secret-canary"
    result = real_fp.jwks_observer_verdict(
        observer, published, observation, checks, unchanged
    )
    assert result == {"verdict": "inconclusive"}


def test_observer_read_is_one_bounded_control_plane_call():
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    calls = []

    def fake_command(command, *, stdin, timeout):
        calls.append((command, stdin, timeout))
        return SimpleNamespace(stdout=json.dumps(observed_events()))

    pod = SimpleNamespace(namespace="probe-a", name="probe-a-backend", uid=UIDS[0])
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    assert (
        real_fp.read_jwks_observation(pod, observer, command_runner=fake_command)
        == observed_events()
    )
    assert len(calls) == 1 and 0 < calls[0][2] <= 10
    assert calls[0][0][:5] == ["kubectl", "-n", "probe-a", "exec", "-i"]
    assert json.loads(calls[0][1]) == {"epoch": EPOCH, "uids": UIDS}


@pytest.mark.parametrize(
    "output", ["not-json", "[]", "x" * 4097, '{"result":"observed"}']
)
def test_malformed_or_oversized_reader_output_cannot_establish_evidence(output):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    pod = SimpleNamespace(namespace="probe-a", name="probe-a-backend", uid=UIDS[0])
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}

    def fake_command(*args, **kwargs):
        return SimpleNamespace(stdout=output)

    observation = real_fp.read_jwks_observation(
        pod, observer, command_runner=fake_command
    )
    result = real_fp.jwks_observer_verdict(
        observer,
        {"status": "armed", "publication_lower_bound_ns": 100},
        observation,
        auth_checks(),
        True,
    )
    assert result == {"verdict": "inconclusive"}


def test_reader_command_exception_is_sanitized():
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    pod = SimpleNamespace(namespace="probe-a", name="probe-a-backend", uid=UIDS[0])
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}

    def failed_command(*args, **kwargs):
        raise OSError("secret-canary")

    assert real_fp.read_jwks_observation(
        pod, observer, command_runner=failed_command
    ) == {"result": "unavailable"}


@pytest.mark.parametrize("fault", ["backend", "zero_timeout", "large_timeout"])
def test_reader_rejects_wrong_backend_or_unbounded_timeout_without_exec(fault):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    pod = SimpleNamespace(namespace="probe-a", name="probe-a-backend", uid=UIDS[0])
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    timeout = 5
    if fault == "backend":
        pod.name = "other"
    elif fault == "zero_timeout":
        timeout = 0
    else:
        timeout = 6

    def forbidden(*args, **kwargs):
        pytest.fail("invalid input must not issue an API read")

    assert real_fp.read_jwks_observation(
        pod, observer, command_runner=forbidden, timeout=timeout
    ) == {"result": "unavailable"}


@pytest.mark.parametrize(
    "fault",
    [
        "collected_type",
        "collected_not_after",
        "publication_zero",
        "events_type",
        "events_count",
    ],
)
def test_observer_rejects_invalid_collection_bounds_or_event_sets(fault):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    observer = {"epoch": EPOCH, "peers": PEERS, "key_ids": KIDS}
    published = {"status": "armed", "publication_lower_bound_ns": 100}
    observation = observed_events()
    if fault == "collected_type":
        observation["collected_monotonic_ns"] = "102"
    elif fault == "collected_not_after":
        observation["collected_monotonic_ns"] = 100
    elif fault == "publication_zero":
        published["publication_lower_bound_ns"] = 0
    elif fault == "events_type":
        observation["events"] = None
    else:
        observation["events"].pop()
    assert real_fp.jwks_observer_verdict(
        observer, published, observation, auth_checks(), True
    ) == {"verdict": "inconclusive"}


@pytest.mark.parametrize(
    "fault",
    [
        "publisher",
        "publisher_uid",
        "count",
        "uid",
        "ip",
        "duplicate_ip",
        "duplicate_uid",
        "precheck",
    ],
)
def test_invalid_or_ambiguous_replica_identities_are_not_armed(fault):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    publisher = SimpleNamespace(
        namespace="probe-a",
        name="probe-a-backend",
        uid="00000000-0000-4000-8000-000000000010",
    )
    replicas = [{"uid": uid, "ip": ip} for ip, uid in PEERS.items()]
    checks = auth_checks()
    if fault == "publisher":
        publisher.name = "other"
    elif fault == "publisher_uid":
        publisher.uid = "invalid"
    elif fault == "count":
        replicas.pop()
    elif fault == "uid":
        replicas[0]["uid"] = "invalid"
    elif fault == "ip":
        replicas[0]["ip"] = "invalid"
    elif fault == "duplicate_ip":
        replicas[1]["ip"] = replicas[0]["ip"]
    elif fault == "duplicate_uid":
        replicas[1]["uid"] = replicas[0]["uid"]
    else:
        checks = []
    assert real_fp.jwks_observer_config(replicas, publisher, checks) is None


@pytest.mark.parametrize(
    "mode",
    [
        "observed",
        "unavailable",
        "malformed",
        "read_exception",
        "arm_unavailable",
        "late",
        "narrow_grace",
    ],
)
def test_existing_rotation_collects_before_auth_without_changing_checks(
    monkeypatch, mode
):
    real_fp = importlib.import_module("networkpolicy_runtime_real_fp")
    replicas = [
        {
            "uid": uid,
            "ip": ip,
            "name": f"processor-{index}",
            "container_id": str(index),
            "image_id": "image",
            "restarts": 0,
        }
        for index, (ip, uid) in enumerate(PEERS.items())
    ]
    publisher = SimpleNamespace(
        namespace="probe-a",
        name="probe-a-backend",
        uid="00000000-0000-4000-8000-000000000010",
    )
    pods = {"a-backend": publisher, "a-fp": object()}
    old, new = SimpleNamespace(kid="primary"), SimpleNamespace(kid="netpol-rotated")
    fixture = SimpleNamespace(
        env={
            "FP_JWT_ISSUER": "issuer",
            "FP_JWT_AUDIENCE": "audience",
            "FP_JWKS_REFRESH_INTERVAL": "300",
        },
        server_name="processor",
        redis_host="redis",
        deployment={"spec": {"selector": {"matchLabels": {"app": "fp"}}}},
    )
    state = {"published": {"primary"}, "revoked": set(), "timeline": [], "now": 0.0}

    def token(key, *, session_id, **kwargs):
        return f"{key.kid}:{session_id}"

    def call_processor(release, replica, server_name, bearer):
        kid, session_id = bearer.split(":", 1)
        state["timeline"].append(f"auth:{kid}")
        if "publish" in state["timeline"] and "post_publish_auth_at" not in state:
            state["post_publish_auth_at"] = state["now"]
        if "read" in state["timeline"] and "auth_after_read" not in state:
            state["auth_after_read"] = state["now"]
        denied = kid not in state["published"] or session_id in state["revoked"]
        return {
            "result": "grpc-status",
            "code": "Unauthenticated" if denied else "InvalidArgument",
        }

    def redis(*args, **kwargs):
        value = json.loads(kwargs["stdin"])
        if value.get("action") == "check":
            return {"result": "unrevoked"}
        state["revoked"].add(value["jti"])
        return {"result": "revoked"}

    def publish(pod, document, *, observer=None):
        state["published"] = set(json.loads(document)["keys"])
        state["timeline"].append("publish")
        result = {"result": "published"}
        if observer is not None:
            result["observer"] = (
                {"status": "unavailable"}
                if mode == "arm_unavailable"
                else {"status": "armed", "publication_lower_bound_ns": 100}
            )
        return result

    def read(pod, observer, *, command_runner, timeout):
        assert 0 < timeout <= 5
        state["read_at"] = state["now"]
        state["now"] += 2
        state["timeline"].append("read")
        if mode == "read_exception":
            raise OSError("secret-canary")
        if mode == "unavailable":
            return {"result": "unavailable"}
        result = observed_events()
        if mode == "malformed":
            result["raw"] = "secret-canary"
        for event in result["events"]:
            event["epoch"] = observer["epoch"]
        return result

    monkeypatch.setattr(real_fp, "processor_token", token)
    monkeypatch.setattr(real_fp, "call_processor", call_processor)
    monkeypatch.setattr(real_fp, "run_in_pod", redis)
    monkeypatch.setattr(
        real_fp,
        "jwks_document",
        lambda keys: json.dumps({"keys": [key.kid for key in keys]}),
    )
    monkeypatch.setattr(real_fp, "publish_jwks", publish)
    monkeypatch.setattr(real_fp, "read_jwks_observation", read)
    monkeypatch.setattr(real_fp, "validate_fixture_token", lambda *args: None)
    monkeypatch.setattr(real_fp, "replica_state", lambda *args: replicas)
    monkeypatch.setattr(real_fp.time, "monotonic", lambda: state["now"])

    def sleep(seconds):
        if mode == "late" and seconds == 300:
            state["now"] += 311
        elif mode == "narrow_grace" and seconds == 300:
            state["now"] += 306
        else:
            state["now"] += seconds

    monkeypatch.setattr(real_fp.time, "sleep", sleep)
    checks, rotations = [], []
    real_fp.verify_processor_authentication(
        fixture, "probe-a", pods, "password", old, new, replicas, checks, rotations
    )
    assert all(check["verdict"] == "pass" for check in checks)
    assert len(checks) == 16
    assert rotations[0]["jwks_witness"]["verdict"] == (
        "pass" if mode == "observed" else "inconclusive"
    )
    assert "secret-canary" not in json.dumps(rotations)
    if mode != "late":
        assert state["post_publish_auth_at"] == 310
    timeline = state["timeline"]
    if mode in {"late", "narrow_grace", "arm_unavailable"}:
        assert "read" not in timeline
    else:
        assert timeline.index("publish") < timeline.index("read")
        assert timeline[timeline.index("read") + 1] == "auth:primary"
        assert state["read_at"] == 300
        assert state["auth_after_read"] == 310
