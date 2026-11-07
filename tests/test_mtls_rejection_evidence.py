"""Behavioral negative controls for private server-correlated mTLS evidence.

No test contacts Kubernetes, changes TLS enforcement, or runs a scanner.
The standard-library test runner also supports isolated execution without the
repository-wide database fixtures.
"""

from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from scripts.kind import mtls_rejection_evidence as evidence

NAMESPACE = "proof"
DEPLOYMENT = "proof-backend"
POD = "proof-backend-abc-123"
REPLICA_SET = "proof-backend-abc"
IMAGE = "registry.example/backend@sha256:" + "a" * 64
START = "2026-11-07T12:00:00Z"
EVENT_TIME = "2026-11-07T12:00:01.123456789Z"
END = "2026-11-07T12:00:02.000000Z"
NONCE = bytes(range(16)).hex()
TAG = str(UUID(hex=NONCE))
LABELS = {"app.kubernetes.io/component": "backend", "app": "proof"}
DEPLOY_UID = "11111111-1111-1111-1111-111111111111"
SET_UID = "22222222-2222-2222-2222-222222222222"
POD_UID = "33333333-3333-3333-3333-333333333333"
SERVICE_UID = "44444444-4444-4444-4444-444444444444"
SLICE_UID = "55555555-5555-5555-5555-555555555555"


def meta(name: str, uid: str, owner: tuple[str, str, str] | None = None) -> dict:
    result = {"name": name, "uid": uid, "namespace": NAMESPACE, "labels": LABELS.copy()}
    if owner is not None:
        kind, owner_name, owner_uid = owner
        result["ownerReferences"] = [
            {"kind": kind, "name": owner_name, "uid": owner_uid, "controller": True}
        ]
    return result


def fixtures() -> dict:
    container = {
        "name": "backend",
        "image": IMAGE,
        "ports": [{"name": "http", "containerPort": 8000, "protocol": "TCP"}],
    }
    deployment = {
        "kind": "Deployment",
        "metadata": {**meta(DEPLOYMENT, DEPLOY_UID), "generation": 4},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": LABELS.copy()},
            "template": {"spec": {"containers": [copy.deepcopy(container)]}},
        },
        "status": {
            "observedGeneration": 4,
            "replicas": 1,
            "updatedReplicas": 1,
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    }
    replica_set = {
        "kind": "ReplicaSet",
        "metadata": meta(REPLICA_SET, SET_UID, ("Deployment", DEPLOYMENT, DEPLOY_UID)),
    }
    pod = {
        "kind": "Pod",
        "metadata": meta(POD, POD_UID, ("ReplicaSet", REPLICA_SET, SET_UID)),
        "spec": {"containers": [copy.deepcopy(container)]},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True"}],
            "podIPs": [{"ip": "10.244.0.3"}],
            "containerStatuses": [
                {
                    "name": "backend",
                    "image": IMAGE,
                    "imageID": "registry.example/backend@sha256:" + "a" * 64,
                    "restartCount": 0,
                    "ready": True,
                    "state": {"running": {"startedAt": "2026-11-07T11:59:00Z"}},
                }
            ],
        },
    }
    service = {
        "kind": "Service",
        "metadata": meta(DEPLOYMENT, SERVICE_UID),
        "spec": {
            "selector": LABELS.copy(),
            "clusterIP": "10.96.0.5",
            "ports": [
                {"name": "http", "port": 8000, "targetPort": "http", "protocol": "TCP"}
            ],
        },
    }
    endpoint_slice = {
        "kind": "EndpointSlice",
        "metadata": {
            **meta(
                "proof-backend-slice", SLICE_UID, ("Service", DEPLOYMENT, SERVICE_UID)
            ),
            "labels": {"kubernetes.io/service-name": DEPLOYMENT},
        },
        "addressType": "IPv4",
        "ports": [{"name": "http", "port": 8000, "protocol": "TCP"}],
        "endpoints": [
            {
                "addresses": ["10.244.0.3"],
                "conditions": {"ready": True, "serving": True, "terminating": False},
                "targetRef": {
                    "kind": "Pod",
                    "name": POD,
                    "namespace": NAMESPACE,
                    "uid": POD_UID,
                },
            }
        ],
    }
    return {
        "deployment": deployment,
        "replicasets": {"items": [replica_set]},
        "pods": {"items": [pod]},
        "service": service,
        "endpointslices": {"items": [endpoint_slice]},
    }


def event_line(**updates: str) -> bytes:
    event = {
        "event": evidence.EVENT,
        "logger": evidence.LOGGER,
        "probe_id": TAG,
        "reason": evidence.REASON,
    }
    event.update(updates)
    return (EVENT_TIME + " " + json.dumps(event) + "\n").encode()


def probe_output(**updates: str) -> bytes:
    fields = {
        "NO_SVID_PROBE_ID": NONCE,
        "NO_SVID_TCP": "CONNECTED",
        "NO_SVID_STAGE": "READ_ALERT",
        "NO_SVID_EVENT": "EOF",
        "NO_SVID_TLS": "ERROR",
        "PROBE_OUTPUT": "VALID",
        "PROBE_EXIT": "0",
    }
    fields.update(updates)
    return "".join(f"{key}={value}\n" for key, value in fields.items()).encode()


class FakeKubectl:
    def __init__(self) -> None:
        self.resources = fixtures()
        self.logs = {POD: event_line()}
        self.commands: list[tuple[list[str], int]] = []
        self.identity = {
            "status": {
                "userInfo": {
                    "username": "kind-admin",
                    "groups": ["system:masters", "system:authenticated"],
                }
            }
        }
        self.fail: str | None = None

    def __call__(self, arguments: list[str], limit: int) -> bytes:
        self.commands.append((arguments, limit))
        if arguments == ["kubectl", "config", "current-context"]:
            return b"kind-aud373\n"
        assert arguments[:4] == [
            "kubectl",
            "--context=kind-aud373",
            "--namespace=proof",
            "--request-timeout=15s",
        ]
        action = arguments[4]
        if action == self.fail:
            raise evidence.EvidenceError("private raw error must never escape")
        if action == "auth":
            return json.dumps(self.identity).encode()
        if action == "get":
            return json.dumps(self.resources[arguments[5]]).encode()
        if action == "logs":
            return self.logs[arguments[5]]
        raise AssertionError(arguments)


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state = self.root / "private-state.json"
        self.probe = self.root / "probe.txt"
        self.output = self.root / "safe-evidence.txt"
        self.fake = FakeKubectl()
        self.probe.write_bytes(probe_output())

    def prepare(self) -> None:
        evidence.prepare(
            NAMESPACE,
            DEPLOYMENT,
            DEPLOYMENT,
            IMAGE,
            self.state,
            runner=self.fake,
            now=lambda: START,
        )

    def verify(self) -> str:
        return evidence.verify(
            self.state, self.probe, runner=self.fake, now=lambda: END
        )

    def test_exact_server_evidence_accepts_preserving_all_128_bits(self) -> None:
        self.prepare()
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)
        self.assertEqual(evidence.validate_probe(probe_output()), TAG)
        self.assertEqual(UUID(TAG).bytes, bytes(range(16)))
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(NONCE, evidence.VALID_SUMMARY)
        self.assertNotIn(DEPLOYMENT, evidence.VALID_SUMMARY)

    def test_prepare_uses_kubernetes_whole_second_log_boundary(self) -> None:
        evidence.prepare(
            NAMESPACE,
            DEPLOYMENT,
            DEPLOYMENT,
            IMAGE,
            self.state,
            runner=self.fake,
            now=lambda: "2026-11-07T12:00:00.900000Z",
        )
        state = json.loads(self.state.read_text())
        self.assertEqual(state["started"], START)
        self.fake.logs[POD] = (
            START + ' {"event":"health_ready"}\n'
        ).encode() + event_line()
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)

    def test_missing_endpoint_uids_fail_closed(self) -> None:
        for target in ("slice", "pod"):
            with self.subTest(target=target):
                self.fake = FakeKubectl()
                if target == "slice":
                    del self.fake.resources["endpointslices"]["items"][0]["metadata"][
                        "uid"
                    ]
                else:
                    del self.fake.resources["endpointslices"]["items"][0]["endpoints"][
                        0
                    ]["targetRef"]["uid"]
                with self.assertRaises(evidence.EvidenceError):
                    self.prepare()
                self.assertFalse(self.state.exists())

    def test_pinned_spec_accepts_and_freezes_cri_reported_repository_tag(self) -> None:
        runtime = self.fake.resources["pods"]["items"][0]["status"][
            "containerStatuses"
        ][0]
        runtime["image"] = "registry.example/backend:source-sha"
        self.prepare()
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)
        runtime["image"] = "registry.example/backend:another-tag"
        with self.assertRaises(evidence.EvidenceError):
            self.verify()

    def test_runtime_repository_digest_must_match_requested_manifest(self) -> None:
        self.fake.resources["pods"]["items"][0]["status"]["containerStatuses"][0][
            "imageID"
        ] = "registry.example/backend@sha256:" + "c" * 64
        with self.assertRaises(evidence.EvidenceError):
            self.prepare()

    def test_runtime_image_reference_and_id_require_safe_bounded_values(self) -> None:
        for field, values in {
            "image": ("", "x" * 513, "tag;command", "bad reference"),
            "imageID": ("", "sha256:invalid", "registry/backend@@sha256:" + "a" * 64),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.fake = FakeKubectl()
                    self.fake.resources["pods"]["items"][0]["status"][
                        "containerStatuses"
                    ][0][field] = value
                    with self.assertRaises(evidence.EvidenceError):
                        self.prepare()

    def test_runtime_repository_alias_preserves_manifest_binding_and_freeze(
        self,
    ) -> None:
        runtime = self.fake.resources["pods"]["items"][0]["status"][
            "containerStatuses"
        ][0]
        runtime["imageID"] = "aud373/fixture/backend@sha256:" + "a" * 64
        self.prepare()
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)
        runtime["imageID"] = "another/alias/backend@sha256:" + "a" * 64
        with self.assertRaises(evidence.EvidenceError):
            self.verify()

    def test_bare_configuration_and_unknown_runtime_ids_fail_closed(self) -> None:
        for prefix in (
            "sha256:",
            "containerd://sha256:",
            "unknown://sha256:",
            "unknown://registry.example/backend@sha256:",
        ):
            with self.subTest(prefix=prefix):
                self.fake.resources["pods"]["items"][0]["status"]["containerStatuses"][
                    0
                ]["imageID"] = prefix + "a" * 64
                with self.assertRaises(evidence.EvidenceError):
                    self.prepare()
                self.assertFalse(self.state.exists())

    def test_runtime_repository_alias_cannot_substitute_manifest_content(self) -> None:
        self.fake.resources["pods"]["items"][0]["status"]["containerStatuses"][0][
            "imageID"
        ] = "aud373/fixture/backend@sha256:" + "b" * 64
        with self.assertRaises(evidence.EvidenceError):
            self.prepare()

    def test_collection_is_context_pinned_read_only_bounded_backend_only(self) -> None:
        self.prepare()
        self.verify()
        logs = [command for command, _ in self.fake.commands if "logs" in command]
        self.assertEqual(len(logs), 1)
        self.assertIn("--container=backend", logs[0])
        self.assertIn(f"--since-time={START}", logs[0])
        self.assertIn("--timestamps=true", logs[0])
        self.assertIn("--tail=-1", logs[0])
        self.assertFalse(
            any(argument.startswith("--limit-bytes") for argument in logs[0])
        )
        self.assertNotIn("--all-containers", logs[0])
        self.assertNotIn("--previous", logs[0])
        self.assertTrue(
            all(limit <= evidence.MAX_BYTES for _, limit in self.fake.commands)
        )

    def test_no_event_mismatched_event_and_duplicates_rejected(self) -> None:
        self.prepare()
        for raw in (
            b"",
            event_line(probe_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            event_line() * 2,
        ):
            with self.subTest(raw=raw):
                self.fake.logs[POD] = raw
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_malformed_unknown_duplicate_and_noncanonical_server_fields(self) -> None:
        raws = [
            event_line(extra="unexpected"),
            event_line(probe_id=TAG.upper()),
            event_line(probe_id=NONCE),
            event_line(reason="OTHER"),
            event_line(logger="untrusted"),
            event_line(event="internal_mtls_peer_authorized"),
            (
                EVENT_TIME
                + ' {"event":"'
                + evidence.EVENT
                + '","probe_id":"'
                + TAG
                + '"\n'
            ).encode(),
            event_line().replace(b'"event":', b'"event":"duplicate", "event":'),
            event_line().rstrip(b"\n"),
            b"\xff\n",
            b"no timestamp\n",
        ]
        self.prepare()
        for raw in raws:
            with self.subTest(raw=raw):
                self.fake.logs[POD] = raw
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_contradictory_event_even_after_valid_event_rejected(self) -> None:
        self.prepare()
        for event in (
            event_line(event="internal_mtls_peer_authorized"),
            event_line(reason="CERTIFICATE_VERIFY_FAILED"),
            (EVENT_TIME + " probe unexpectedly accepted " + TAG + "\n").encode(),
        ):
            with self.subTest(event=event):
                self.fake.logs[POD] = event_line() + event
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_unrelated_bounded_logs_and_other_valid_probe_are_not_matches(self) -> None:
        self.prepare()
        self.fake.logs[POD] = (
            (
                EVENT_TIME
                + ' {"event":"health_ready"}\n'
                + EVENT_TIME
                + " unrelated startup note\n"
            ).encode()
            + event_line(probe_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            + event_line()
        )
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)

    def test_stale_future_and_bad_timestamps_rejected(self) -> None:
        self.prepare()
        for clock in (
            "2026-11-07T11:59:59.999999999Z",
            "2026-11-07T12:00:02.000000001Z",
            "2026-11-07T12:00:03Z",
            "2026-99-07T12:00:01Z",
            "2026-11-07T12:00:01+00:00",
        ):
            with self.subTest(clock=clock):
                self.fake.logs[POD] = event_line().replace(
                    EVENT_TIME.encode(), clock.encode()
                )
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_wrong_client_states_and_command_failures_rejected(self) -> None:
        self.prepare()
        for key, values in {
            "NO_SVID_TCP": ("ERROR",),
            "NO_SVID_STAGE": (
                "TCP_CONNECT",
                "TLS_HANDSHAKE",
                "WRITE_REQUEST",
                "READ_RESPONSE",
            ),
            "NO_SVID_EVENT": (
                "RESET",
                "TIMEOUT",
                "SSL_ERROR",
                "OS_ERROR",
                "DATA",
                "CERTIFICATE_REQUIRED",
            ),
            "NO_SVID_TLS": ("REJECTED", "ANSWERED"),
            "PROBE_OUTPUT": ("INVALID",),
            "PROBE_EXIT": ("1", "125", "00"),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.probe.write_bytes(probe_output(**{key: value}))
                    with self.assertRaises(evidence.EvidenceError):
                        self.verify()

    def test_probe_duplicate_unknown_missing_noncanonical_and_corrupt_rejected(
        self,
    ) -> None:
        self.prepare()
        raw = probe_output()
        for value in (
            raw + b"PROBE_EXIT=0\n",
            raw + b"EXTRA=0\n",
            raw.replace(b"PROBE_EXIT=0\n", b""),
            raw.rstrip(b"\n"),
            raw.replace(NONCE.encode(), NONCE.upper().encode()),
            raw.replace(NONCE.encode(), TAG.encode()),
            raw + b"\xff\n",
            raw.replace(b"\n", b"\r\n"),
            raw.replace(b"\n", b"\v") + b"\n",
        ):
            with self.subTest(raw=value):
                self.probe.write_bytes(value)
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_read_failure_is_not_converted_to_empty_success(self) -> None:
        self.prepare()
        for action in ("logs", "get", "auth"):
            with self.subTest(action=action):
                self.fake.fail = action
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_missing_or_corrupt_state_and_probe_fail(self) -> None:
        with self.assertRaises(evidence.EvidenceError):
            self.verify()
        self.state.write_bytes(b"{corrupt")
        with self.assertRaises(evidence.EvidenceError):
            self.verify()
        self.probe.unlink()
        with self.assertRaises(evidence.EvidenceError):
            self.verify()

    def test_snapshot_mutations_fail(self) -> None:
        self.prepare()
        original = copy.deepcopy(self.fake.resources)
        mutations = [
            (
                "deployment uid",
                lambda r: r["deployment"]["metadata"].update(
                    uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            ),
            (
                "deployment generation",
                lambda r: r["deployment"]["metadata"].update(generation=5),
            ),
            (
                "deployment image",
                lambda r: r["deployment"]["spec"]["template"]["spec"]["containers"][
                    0
                ].update(image=IMAGE.replace("a" * 64, "c" * 64)),
            ),
            (
                "replicaset uid",
                lambda r: r["replicasets"]["items"][0]["metadata"].update(
                    uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            ),
            (
                "pod uid",
                lambda r: r["pods"]["items"][0]["metadata"].update(
                    uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            ),
            (
                "pod image",
                lambda r: r["pods"]["items"][0]["spec"]["containers"][0].update(
                    image=IMAGE.replace("a" * 64, "c" * 64)
                ),
            ),
            (
                "imageID",
                lambda r: r["pods"]["items"][0]["status"]["containerStatuses"][
                    0
                ].update(imageID="sha256:" + "c" * 64),
            ),
            (
                "restart",
                lambda r: r["pods"]["items"][0]["status"]["containerStatuses"][
                    0
                ].update(restartCount=1),
            ),
            (
                "endpoint uid",
                lambda r: r["endpointslices"]["items"][0]["metadata"].update(
                    uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            ),
            (
                "endpoint ready",
                lambda r: r["endpointslices"]["items"][0]["endpoints"][0][
                    "conditions"
                ].update(ready=False),
            ),
            (
                "endpoint address",
                lambda r: r["endpointslices"]["items"][0]["endpoints"][0].update(
                    addresses=["10.244.0.9"]
                ),
            ),
            (
                "endpoint target",
                lambda r: r["endpointslices"]["items"][0]["endpoints"][0][
                    "targetRef"
                ].update(uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            ),
            (
                "endpoint port",
                lambda r: r["endpointslices"]["items"][0]["ports"][0].update(port=8080),
            ),
            (
                "service uid",
                lambda r: r["service"]["metadata"].update(
                    uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
                ),
            ),
            (
                "service selector",
                lambda r: r["service"]["spec"].update(selector={"app": "another"}),
            ),
            ("missing pods", lambda r: r["pods"].update(items=[])),
            (
                "pod deletion",
                lambda r: r["pods"]["items"][0]["metadata"].update(
                    deletionTimestamp=END
                ),
            ),
            (
                "wrong owner",
                lambda r: r["pods"]["items"][0]["metadata"]["ownerReferences"][
                    0
                ].update(uid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            ),
            (
                "unready pod",
                lambda r: r["pods"]["items"][0]["status"]["containerStatuses"][
                    0
                ].update(ready=False),
            ),
        ]
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                self.fake.resources = copy.deepcopy(original)
                mutate(self.fake.resources)
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_authentication_change_or_anonymous_identity_rejected(self) -> None:
        self.prepare()
        for identity in (
            {"username": "system:anonymous", "groups": ["system:unauthenticated"]},
            {"username": "another-user", "groups": ["system:authenticated"]},
            {"username": "kind-admin", "groups": []},
        ):
            with self.subTest(identity=identity):
                self.fake.identity["status"]["userInfo"] = identity
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_bounded_window_and_backward_clock_rejected(self) -> None:
        self.prepare()
        for end in ("2026-11-07T12:03:00.000001Z", "2026-11-07T11:59:59Z"):
            with self.subTest(end=end), self.assertRaises(evidence.EvidenceError):
                evidence.verify(
                    self.state, self.probe, runner=self.fake, now=lambda end=end: end
                )

    def test_all_backend_pods_collected_and_cross_pod_duplicate_rejected(self) -> None:
        resources = self.fake.resources
        resources["deployment"]["spec"]["replicas"] = 2
        for field in (
            "replicas",
            "updatedReplicas",
            "readyReplicas",
            "availableReplicas",
        ):
            resources["deployment"]["status"][field] = 2
        second = copy.deepcopy(resources["pods"]["items"][0])
        second["metadata"].update(
            name="proof-backend-abc-456", uid="66666666-6666-6666-6666-666666666666"
        )
        second["status"]["podIPs"] = [{"ip": "10.244.0.4"}]
        resources["pods"]["items"].append(second)
        endpoint = copy.deepcopy(
            resources["endpointslices"]["items"][0]["endpoints"][0]
        )
        endpoint["addresses"] = ["10.244.0.4"]
        endpoint["targetRef"].update(
            name=second["metadata"]["name"], uid=second["metadata"]["uid"]
        )
        resources["endpointslices"]["items"][0]["endpoints"].append(endpoint)
        self.fake.logs[second["metadata"]["name"]] = b""
        self.prepare()
        self.assertEqual(self.verify(), evidence.VALID_SUMMARY)
        self.fake.logs[second["metadata"]["name"]] = event_line()
        with self.assertRaises(evidence.EvidenceError):
            self.verify()

    def test_bounds_reject_truncated_or_oversized_inputs(self) -> None:
        self.prepare()
        for raw in (
            b"x" * (evidence.MAX_LOG_BYTES + 1),
            (EVENT_TIME + " " + "x" * 8192 + "\n").encode(),
            ((EVENT_TIME + " note\n") * 4097).encode(),
        ):
            with self.subTest(length=len(raw)):
                self.fake.logs[POD] = raw
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()
        self.probe.write_bytes(b"x" * 1025)
        with self.assertRaises(evidence.EvidenceError):
            self.verify()

    def test_nonfinite_json_is_rejected_even_in_unrelated_logs(self) -> None:
        self.prepare()
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.fake.logs[POD] = (
                    event_line()
                    + (EVENT_TIME + ' {"unrelated":' + constant + "}\n").encode()
                )
                with self.assertRaises(evidence.EvidenceError):
                    self.verify()

    def test_no_overwrite_existing_private_state_or_mutable_images(self) -> None:
        self.prepare()
        with self.assertRaises(FileExistsError):
            self.prepare()
        with self.assertRaises(evidence.EvidenceError):
            evidence.prepare(
                NAMESPACE,
                DEPLOYMENT,
                DEPLOYMENT,
                "registry.example/backend:latest",
                self.state,
                runner=self.fake,
            )

    def test_cli_failure_artifact_is_finite_and_does_not_leak_errors(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = evidence.main(
                [
                    "verify",
                    "--state",
                    str(self.state),
                    "--probe",
                    str(self.probe),
                    "--output",
                    str(self.output),
                ]
            )
        self.assertEqual(status, 1)
        self.assertEqual(
            self.output.read_text(),
            evidence.INVALID_SUMMARY + "SERVER_EVIDENCE_PHASE=STATE\n",
        )
        self.assertEqual(
            output.getvalue(),
            "SERVER_EVIDENCE_COLLECTION=INVALID\nSERVER_EVIDENCE_PHASE=STATE\n",
        )

    def test_cli_failure_phase_is_allowlisted_without_raw_error(self) -> None:
        argv = [
            "verify",
            "--state",
            str(self.state),
            "--probe",
            str(self.probe),
            "--output",
            str(self.output),
        ]
        for phase, expected in (("LOGS", "LOGS"), ("private raw value", "VERIFY")):
            with (
                self.subTest(phase=phase),
                patch.object(
                    evidence,
                    "verify",
                    side_effect=evidence.EvidenceError("secret raw error", phase=phase),
                ),
                redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(evidence.main(argv), 1)
                self.assertEqual(
                    self.output.read_text(),
                    evidence.INVALID_SUMMARY + f"SERVER_EVIDENCE_PHASE={expected}\n",
                )
                self.assertNotIn("secret", output.getvalue())
                self.assertNotIn("private", output.getvalue())

    def test_cli_success_artifact_and_failed_output_write(self) -> None:
        argv = [
            "verify",
            "--state",
            str(self.state),
            "--probe",
            str(self.probe),
            "--output",
            str(self.output),
        ]
        with (
            patch.object(evidence, "verify", return_value=evidence.VALID_SUMMARY),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(evidence.main(argv), 0)
            self.assertEqual(self.output.read_text(), evidence.VALID_SUMMARY)
            self.output.unlink()
            self.output.mkdir()
            self.assertEqual(evidence.main(argv), 1)

    def test_subprocess_output_limit_timeout_and_nonzero_exit(self) -> None:
        # A local Python process replaces kubectl; no API/network call is made.
        python = os.sys.executable

        def invoke(code: str, limit: int = 100) -> bytes:
            with patch.object(evidence.shutil, "which", return_value=python):
                return evidence.bounded_command(["kubectl", "-c", code], limit)

        self.assertEqual(invoke("print('okay')"), b"okay\n")
        for code in (
            "print('x'*101)",
            "import sys; sys.stderr.write('x'*101)",
            "import sys; sys.exit(1)",
        ):
            with self.subTest(code=code), self.assertRaises(evidence.EvidenceError):
                invoke(code)
        with (
            patch.object(evidence, "COMMAND_TIMEOUT", 0.05),
            self.assertRaises(evidence.EvidenceError),
        ):
            invoke("import time; time.sleep(5)  # bound: 50ms parent deadline")
        with (
            patch.object(evidence.shutil, "which", return_value=None),
            self.assertRaises(evidence.EvidenceError),
        ):
            evidence.bounded_command(["kubectl", "config", "current-context"], 100)


if __name__ == "__main__":
    unittest.main()
