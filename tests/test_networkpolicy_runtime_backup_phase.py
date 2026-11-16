"""Offline contracts for the disposable real backup and restore phase."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "k8s"))


def test_backup_phase_controller_is_available() -> None:
    assert importlib.util.find_spec("networkpolicy_runtime_backup_phase") is not None


@pytest.fixture
def proof() -> Any:
    return importlib.import_module("networkpolicy_runtime_backup_phase")


@pytest.fixture
def simulated(proof: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Simulate only the external Kubernetes boundary; keep orchestration real."""
    namespace = "probe-a"
    image = "example.invalid/postgres@sha256:" + "a" * 64
    rclone = "example.invalid/rclone@sha256:" + "b" * 64
    labels = {"app.kubernetes.io/component": "backup"}

    def reference(name: str, key: str) -> dict[str, Any]:
        return {"secretKeyRef": {"name": name, "key": key}}

    backup = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": "probe-a-db-backup-proof",
            "namespace": namespace,
            "labels": labels,
        },
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "serviceAccountName": "probe-a-backup",
                    "initContainers": [
                        {
                            "name": "database-dump",
                            "image": image,
                            "env": [
                                {
                                    "name": "DATABASE_URL",
                                    "valueFrom": reference("source-db", "url"),
                                },
                            ],
                        }
                    ],
                    "containers": [
                        {
                            "name": "upload",
                            "image": rclone,
                            "env": [
                                {
                                    "name": "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID",
                                    "valueFrom": reference("store", "access"),
                                },
                                {
                                    "name": "RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY",
                                    "valueFrom": reference("store", "secret"),
                                },
                            ],
                        }
                    ],
                },
            }
        },
    }
    restore = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "netpol-backup-restore", "namespace": namespace},
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "initContainers": [{"name": "readback", "image": rclone}],
                    "containers": [{"name": "restore", "image": image}],
                },
            }
        },
    }
    postgres = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "netpol-backup-postgres", "namespace": namespace},
        "spec": {"containers": [{"name": "postgres", "image": image}]},
    }
    fixture = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "source-db", "namespace": namespace},
            "stringData": {"url": "fixture database url"},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "netpol-backup-restore", "namespace": namespace},
            "stringData": {"database-url": "fixture restore url"},
        },
        postgres,
    ]

    monkeypatch.setattr(
        proof, "build_backup_job", lambda *_args, **_kwargs: copy.deepcopy(backup)
    )
    monkeypatch.setattr(
        proof, "build_restore_job", lambda *_args, **_kwargs: copy.deepcopy(restore)
    )
    monkeypatch.setattr(
        proof, "fixture_objects", lambda *_args, **_kwargs: copy.deepcopy(fixture)
    )

    class Cluster:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], dict[str, Any]]] = []
            self.created: list[dict[str, Any]] = []
            self.uids: dict[str, str] = {}
            self.pods: dict[str, dict[str, Any]] = {}
            self.marker = "AUD189_BACKUP_RESTORE_OK\n"
            self.fault = ""
            self.logs_read = False

        def __call__(self, args: list[str], **kwargs: Any) -> SimpleNamespace:
            self.calls.append((args, kwargs))
            assert args[0] == "kubectl" and args[args.index("-n") + 1] == namespace
            assert 0 < kwargs["timeout"] <= 300
            if "create" in args:
                obj = json.loads(kwargs["stdin"])
                if self.fault == "oversized-output":
                    return SimpleNamespace(stdout="x" * (proof.MAX_RESPONSE + 1))
                if self.fault == "create-backup" and obj["kind"] == "Job":
                    raise subprocess.CalledProcessError(
                        1,
                        args,
                        output="temporary-access",
                        stderr="temporary-passphrase",
                    )
                self.created.append(obj)
                if obj["kind"] in {"Job", "Pod"}:
                    if self.fault == "non-object-output":
                        return SimpleNamespace(stdout="[]")
                    name = obj["metadata"]["name"]
                    uid = f"00000000-0000-4000-8000-{len(self.created):012d}"
                    self.uids[name] = uid
                    obj = copy.deepcopy(obj)
                    obj["metadata"]["uid"] = (
                        "invalid" if self.fault == "invalid-uid" else uid
                    )
                    if self.fault == "wrong-kind":
                        obj["kind"] = "Service"
                    return SimpleNamespace(stdout=json.dumps(obj))
                return SimpleNamespace(stdout="created\n")
            if "wait" in args:
                return SimpleNamespace(stdout="ready\n")
            if "get" in args and "job" in args:
                name = args[args.index("job") + 1]
                uid = self.uids[name]
                if self.fault == "job-uid":
                    uid = "00000000-0000-4000-8000-999999999999"
                return SimpleNamespace(
                    stdout=json.dumps(
                        {
                            "apiVersion": "batch/v1",
                            "kind": "Job",
                            "metadata": {
                                "name": name,
                                "namespace": namespace,
                                "uid": uid,
                            },
                            "status": {
                                "succeeded": 1,
                                "conditions": [{"type": "Complete", "status": "True"}],
                            },
                        }
                    )
                )
            if "get" in args and "pods" in args:
                selector = args[args.index("-l") + 1]
                uid = selector.split("=", 1)[1]
                name = next(name for name, value in self.uids.items() if value == uid)
                job = next(
                    item
                    for item in self.created
                    if item["kind"] == "Job" and item["metadata"]["name"] == name
                )
                pod = self.pod_for(job, uid)
                self.pods[pod["metadata"]["name"]] = copy.deepcopy(pod)
                if self.fault == "pod-list-no-kind":
                    pod.pop("kind")
                if self.fault == "listed-namespace":
                    pod["metadata"]["namespace"] = "other"
                if self.fault == "listed-uid":
                    pod["metadata"]["uid"] = "00000000-0000-4000-8000-999999999999"
                pods = (
                    [pod, copy.deepcopy(pod)]
                    if self.fault == "multiple-pods"
                    else [pod]
                )
                return SimpleNamespace(stdout=json.dumps({"items": pods}))
            if "get" in args and "pod" in args:
                requested = args[args.index("pod") + 1]
                if requested in self.pods:
                    obj = copy.deepcopy(self.pods[requested])
                    if self.logs_read and self.fault == "pod-replaced-after-logs":
                        obj["metadata"]["uid"] = "00000000-0000-4000-8000-999999999999"
                    return SimpleNamespace(stdout=json.dumps(obj))
                obj = copy.deepcopy(
                    next(item for item in self.created if item["kind"] == "Pod")
                )
                if obj["spec"].get("hostNetwork") is False:
                    obj["spec"].pop("hostNetwork")
                obj["metadata"]["uid"] = self.uids[obj["metadata"]["name"]]
                if self.fault == "postgres-uid":
                    obj["metadata"]["uid"] = "00000000-0000-4000-8000-999999999999"
                obj["status"] = {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "containerStatuses": [
                        {
                            "name": "postgres",
                            "imageID": "sha256:" + "c" * 64,
                            "restartCount": 0,
                            "ready": True,
                        }
                    ],
                }
                if self.fault == "postgres-not-ready":
                    obj["status"]["phase"] = "Pending"
                if self.fault == "postgres-container-not-ready":
                    obj["status"]["containerStatuses"][0]["ready"] = False
                if self.fault == "host-network":
                    obj["spec"]["hostNetwork"] = True
                return SimpleNamespace(stdout=json.dumps(obj))
            if "logs" in args:
                self.logs_read = True
                return SimpleNamespace(stdout=self.marker)
            raise AssertionError(f"unexpected Kubernetes command: {args!r}")

        def pod_for(self, job: dict[str, Any], uid: str) -> dict[str, Any]:
            name = job["metadata"]["name"]
            spec = copy.deepcopy(job["spec"]["template"]["spec"])
            if spec.get("hostNetwork") is False:
                spec.pop("hostNetwork")
            owner_uid = (
                "00000000-0000-4000-8000-999999999999"
                if self.fault == "pod-owner"
                else uid
            )

            def statuses(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
                return [
                    {
                        "name": item["name"],
                        "imageID": "example.invalid/image@sha256:" + "d" * 64,
                        "restartCount": 0,
                        "state": {"terminated": {"exitCode": 0}},
                    }
                    for item in containers
                ]

            result = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": name + "-abcde",
                    "namespace": namespace,
                    "uid": "00000000-0000-4000-8000-888888888888",
                    "labels": copy.deepcopy(
                        job["spec"]["template"]["metadata"]["labels"]
                    ),
                    "ownerReferences": [
                        {
                            "apiVersion": "batch/v1",
                            "kind": "Job",
                            "name": name,
                            "uid": owner_uid,
                            "controller": True,
                        }
                    ],
                },
                "spec": spec,
                "status": {
                    "phase": "Succeeded",
                    "initContainerStatuses": statuses(spec["initContainers"]),
                    "containerStatuses": statuses(spec["containers"]),
                },
            }
            if self.fault == "missing-image":
                result["status"]["containerStatuses"][0]["imageID"] = ""
            if self.fault == "wrong-image":
                result["spec"]["containers"][0]["image"] = "unexpected"
            if self.fault == "restart":
                result["status"]["containerStatuses"][0]["restartCount"] = 1
            if self.fault == "added-privilege":
                result["spec"]["containers"][0]["securityContext"] = {
                    "privileged": True
                }
            if self.fault == "extra-container":
                result["spec"]["containers"].append({"name": "other"})
            if self.fault == "added-env":
                result["spec"]["containers"][0]["envFrom"] = [
                    {"configMapRef": {"name": "other"}}
                ]
            if self.fault == "exit-failed":
                result["status"]["containerStatuses"][0]["state"]["terminated"][
                    "exitCode"
                ] = 1
            if self.fault == "wrong-service-account":
                result["spec"]["serviceAccountName"] = "other"
            if self.fault == "wrong-label":
                result["metadata"]["labels"]["app.kubernetes.io/component"] = "other"
            return result

    cluster = Cluster()
    monkeypatch.setattr(proof, "run_command", cluster)
    cluster.backup = backup
    cluster.restore = restore
    cluster.fixture = fixture
    return cluster


def run_phase(proof: Any) -> dict[str, Any]:
    return proof.run_backup_phase(
        {},
        ca_certificate="fixture certificate",
        access_key="temporary-access",
        secret_key="temporary-passphrase",
    )


def test_creates_owned_prerequisites_then_completed_jobs_and_receipt(
    proof: Any, simulated: Any
) -> None:
    result = run_phase(proof)
    assert result["verdict"] == "pass"
    assert result["stage"] == "complete"
    assert result["backup_job_attempted"] is True
    assert result["restore_receipt"] == "AUD189_BACKUP_RESTORE_OK"
    assert result["namespace"] == "probe-a"
    assert result["postgres"]["uid"] == simulated.uids["netpol-backup-postgres"]
    assert (
        result["backup_job"]["uid"]
        == simulated.uids[simulated.backup["metadata"]["name"]]
    )
    assert (
        result["restore_job"]["uid"]
        == simulated.uids[simulated.restore["metadata"]["name"]]
    )
    assert result["backup_job"]["pod"]["image_ids"] == {
        "database-dump": "sha256:" + "d" * 64,
        "upload": "sha256:" + "d" * 64,
    }
    kinds = [item["kind"] for item in simulated.created]
    assert kinds[-2:] == ["Job", "Job"]
    assert "ServiceAccount" in kinds and "ConfigMap" in kinds
    store = next(
        item
        for item in simulated.created
        if item["kind"] == "Secret" and item["metadata"]["name"] == "store"
    )
    assert store["stringData"] == {
        "access": "temporary-access",
        "secret": "temporary-passphrase",
    }
    call_text = json.dumps([args for args, _ in simulated.calls])
    assert (
        "temporary-access" not in call_text and "temporary-passphrase" not in call_text
    )
    receipt = json.dumps(result)
    assert "temporary-access" not in receipt and "temporary-passphrase" not in receipt


@pytest.mark.parametrize(
    "fault",
    [
        "postgres-uid",
        "job-uid",
        "pod-owner",
        "multiple-pods",
        "missing-image",
        "wrong-image",
        "restart",
        "added-privilege",
        "extra-container",
        "added-env",
        "exit-failed",
        "wrong-service-account",
        "wrong-label",
        "listed-namespace",
        "listed-uid",
    ],
)
def test_rejects_ambiguous_or_unbound_runtime_evidence(
    proof: Any, simulated: Any, fault: str
) -> None:
    simulated.fault = fault
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["backup_job_attempted"] is (fault != "postgres-uid")
    assert not any(
        item["metadata"]["name"] == "netpol-backup-restore" and item["kind"] == "Job"
        for item in simulated.created
    )


@pytest.mark.parametrize(
    "marker",
    [
        "",
        "AUD189_BACKUP_RESTORE_OK\nextra",
        "unexpected",
        "AUD189_BACKUP_RESTORE_OK\n\n",
    ],
)
def test_restore_requires_only_exact_bounded_marker(
    proof: Any, simulated: Any, marker: str
) -> None:
    simulated.marker = marker
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["stage"] == "restore_receipt"


def test_command_errors_cannot_leak_credentials(
    proof: Any, simulated: Any, capsys: Any
) -> None:
    simulated.fault = "create-backup"
    result = run_phase(proof)
    captured = capsys.readouterr()
    assert result["verdict"] == "fail" and result["backup_job_attempted"] is True
    assert "temporary-access" not in json.dumps(result) + captured.out + captured.err
    assert (
        "temporary-passphrase" not in json.dumps(result) + captured.out + captured.err
    )


def test_binds_a_list_item_without_typemeta_to_its_fetched_pod(
    proof: Any, simulated: Any
) -> None:
    simulated.fault = "pod-list-no-kind"
    assert run_phase(proof)["verdict"] == "pass"


def test_restore_pod_must_keep_its_uid_across_marker_read(
    proof: Any, simulated: Any
) -> None:
    simulated.fault = "pod-replaced-after-logs"
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["stage"] == "restore_receipt"


@pytest.mark.parametrize(
    "fault",
    [
        "oversized-output",
        "non-object-output",
        "invalid-uid",
        "wrong-kind",
        "postgres-not-ready",
        "postgres-container-not-ready",
        "host-network",
    ],
)
def test_prerequisite_failure_never_launches_backup(
    proof: Any, simulated: Any, fault: str
) -> None:
    simulated.fault = fault
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["backup_job_attempted"] is False


@pytest.mark.parametrize("layout", ["separate", "shared-source"])
def test_secret_references_create_only_the_rendered_names(
    proof: Any, simulated: Any, layout: str
) -> None:
    env = simulated.backup["spec"]["template"]["spec"]["containers"][0]["env"]
    access_ref = env[0]["valueFrom"]["secretKeyRef"]
    secret_ref = env[1]["valueFrom"]["secretKeyRef"]
    if layout == "separate":
        secret_ref["name"] = "other-store"
    else:
        access_ref["name"] = secret_ref["name"] = "source-db"
    result = run_phase(proof)
    assert result["verdict"] == "pass"
    store_secrets = {
        item["metadata"]["name"]: item["stringData"]
        for item in simulated.created
        if item["kind"] == "Secret"
    }
    if layout == "separate":
        assert store_secrets["store"] == {"access": "temporary-access"}
        assert store_secrets["other-store"] == {"secret": "temporary-passphrase"}
    else:
        assert store_secrets["source-db"] == {
            "url": "fixture database url",
            "access": "temporary-access",
            "secret": "temporary-passphrase",
        }


@pytest.mark.parametrize("collision", ["same-key", "database-key", "restore-secret"])
def test_rejects_secret_collisions_before_any_resource_is_created(
    proof: Any, simulated: Any, collision: str
) -> None:
    env = simulated.backup["spec"]["template"]["spec"]["containers"][0]["env"]
    access_ref = env[0]["valueFrom"]["secretKeyRef"]
    secret_ref = env[1]["valueFrom"]["secretKeyRef"]
    if collision == "same-key":
        secret_ref.update(access_ref)
    elif collision == "database-key":
        access_ref.update(name="source-db", key="url")
    else:
        access_ref["name"] = "netpol-backup-restore"
    result = run_phase(proof)
    assert result == {
        "verdict": "fail",
        "stage": "input",
        "backup_job_attempted": False,
    }
    assert simulated.calls == []


@pytest.mark.parametrize(
    "fault",
    [
        "invalid-name",
        "invalid-key",
        "duplicate-reference",
        "wrong-namespace",
        "wrong-account",
    ],
)
def test_rejects_invalid_rendered_inputs_before_creating_anything(
    proof: Any, simulated: Any, fault: str
) -> None:
    pod = simulated.backup["spec"]["template"]["spec"]
    ref = pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"]
    if fault == "invalid-name":
        ref["name"] = "BAD_NAME"
    elif fault == "invalid-key":
        ref["key"] = "/invalid"
    elif fault == "duplicate-reference":
        pod["initContainers"][0]["env"].append(
            copy.deepcopy(pod["initContainers"][0]["env"][0])
        )
    elif fault == "wrong-namespace":
        simulated.backup["metadata"]["namespace"] = "other"
    else:
        pod["serviceAccountName"] = "other"
    result = run_phase(proof)
    assert result == {
        "verdict": "fail",
        "stage": "input",
        "backup_job_attempted": False,
    }
    assert simulated.calls == []


@pytest.mark.parametrize("invalid", ["", "a\x00b", "x" * 1025])
def test_rejects_invalid_credential_values_without_logging(
    proof: Any, simulated: Any, invalid: str, capsys: Any
) -> None:
    result = proof.run_backup_phase(
        {},
        ca_certificate="fixture certificate",
        access_key=invalid,
        secret_key="temporary-passphrase",
    )
    captured = capsys.readouterr()
    assert result == {
        "verdict": "fail",
        "stage": "input",
        "backup_job_attempted": False,
    }
    assert simulated.calls == []
    assert "temporary-passphrase" not in captured.out + captured.err


@pytest.mark.parametrize(
    "fault", ["too-many", "duplicate", "missing-pod", "wrong-object-namespace"]
)
def test_rejects_invalid_fixture_manifests(
    proof: Any, simulated: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    if fault == "too-many":
        monkeypatch.setattr(
            proof, "fixture_objects", lambda *_args, **_kwargs: [{}] * 16
        )
    elif fault == "duplicate":
        simulated.fixture.append(copy.deepcopy(simulated.fixture[0]))
    elif fault == "missing-pod":
        simulated.fixture.pop()
    else:
        simulated.fixture[0]["metadata"]["namespace"] = "other"
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["backup_job_attempted"] is False


def test_actual_builders_compose_at_the_mocked_kubernetes_boundary(
    proof: Any, simulated: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_builder = importlib.import_module("networkpolicy_runtime_backup_job")
    restore_builder = importlib.import_module("networkpolicy_runtime_backup_restore")
    postgres_builder = importlib.import_module("networkpolicy_runtime_backup_postgres")
    monkeypatch.setattr(proof, "build_backup_job", job_builder.build_backup_job)
    monkeypatch.setattr(proof, "build_restore_job", restore_builder.build_restore_job)
    monkeypatch.setattr(proof, "fixture_objects", postgres_builder.fixture_objects)

    values = yaml.safe_load(
        (ROOT / "charts/university-ecosystem/values.yaml").read_text(encoding="utf-8")
    )["backup"]
    labels = {
        "app.kubernetes.io/name": "university-ecosystem",
        "app.kubernetes.io/instance": "probe-a",
        "app.kubernetes.io/component": "backup",
    }
    restriction = {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    temporary_directory = str(PurePosixPath("/", "tmp"))

    def ref(variable: str, name: str, key: str) -> dict[str, Any]:
        return {
            "name": variable,
            "valueFrom": {"secretKeyRef": {"name": name, "key": key}},
        }

    common = {
        "imagePullPolicy": "Always",
        "command": ["/bin/sh", "-ec"],
        "securityContext": restriction,
        "resources": {"limits": {"memory": "256Mi"}},
    }
    dump = {
        **common,
        "name": "database-dump",
        "image": values["postgresImage"],
        "args": [
            "pg_dump --format=custom --no-owner --no-privileges "
            '--file=/backup/database.dump "$DATABASE_URL"'
        ],
        "env": [
            ref("DATABASE_URL", "source-db", "url"),
            {"name": "HOME", "value": temporary_directory},
        ],
        "volumeMounts": [
            {"name": "backup-data", "mountPath": "/backup"},
            {"name": "tmp", "mountPath": temporary_directory},
        ],
    }
    upload = {
        **common,
        "name": "upload",
        "image": values["s3ClientImage"],
        "args": [
            'rclone mkdir "backup:$BACKUP_BUCKET"\n'
            'object="university-$(date -u +%Y%m%dT%H%M%SZ).dump"\n'
            'rclone copyto /backup/database.dump "backup:$BACKUP_BUCKET/$object"\n'
        ],
        "env": [
            {"name": "BACKUP_BUCKET", "value": "fixture"},
            {"name": "RCLONE_CONFIG_BACKUP_TYPE", "value": "s3"},
            {"name": "RCLONE_CONFIG_BACKUP_PROVIDER", "value": "Other"},
            {"name": "RCLONE_CONFIG_BACKUP_ENDPOINT", "value": "https://198.18.0.2"},
            ref("RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID", "store", "access"),
            ref("RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY", "store", "secret"),
            {"name": "HOME", "value": temporary_directory},
        ],
        "volumeMounts": [
            {"name": "backup-data", "mountPath": "/backup", "readOnly": True},
            {"name": "tmp", "mountPath": temporary_directory},
        ],
    }
    pod = {
        "serviceAccountName": "probe-a-backup",
        "automountServiceAccountToken": False,
        "restartPolicy": "OnFailure",
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "runAsGroup": 1000,
            "fsGroup": 1000,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "initContainers": [dump],
        "containers": [upload],
        "volumes": [
            {"name": "backup-data", "emptyDir": {}},
            {"name": "tmp", "emptyDir": {}},
        ],
    }
    cronjob = {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {
            "name": "probe-a-db-backup",
            "namespace": "probe-a",
            "labels": labels,
        },
        "spec": {
            "jobTemplate": {
                "spec": {
                    "backoffLimit": 3,
                    "ttlSecondsAfterFinished": 86400,
                    "template": {"metadata": {"labels": labels}, "spec": pod},
                }
            }
        },
    }
    result = proof.run_backup_phase(
        cronjob,
        ca_certificate="fixture certificate",
        access_key="temporary-access",
        secret_key="temporary-passphrase",
    )
    assert result["verdict"] == "pass"
    assert result["restore_receipt"] == restore_builder.RESTORE_RECEIPT
    assert result["backup_job"]["pod"]["image_ids"]["upload"].startswith("sha256:")


@pytest.mark.parametrize(
    ("job_name", "phase", "statuses", "expected"),
    [
        (
            "probe-a-db-backup-proof",
            "Pending",
            {
                "initContainerStatuses": [
                    {
                        "name": "database-dump",
                        "state": {"waiting": {"reason": "temporary-passphrase"}},
                    }
                ],
                "containerStatuses": [
                    {
                        "name": "upload",
                        "state": {"running": {"message": "temporary-access"}},
                    }
                ],
            },
            {"database-dump": {"state": "waiting"}, "upload": {"state": "running"}},
        ),
        (
            "netpol-backup-restore",
            "Failed",
            {
                "initContainerStatuses": [
                    {
                        "name": "readback",
                        "state": {
                            "terminated": {
                                "exitCode": 12,
                                "reason": "temporary-passphrase",
                            }
                        },
                    }
                ],
                "containerStatuses": [{"name": "restore", "state": {"waiting": {}}}],
            },
            {
                "readback": {"state": "terminated", "exit_code": 12},
                "restore": {"state": "waiting"},
            },
        ),
        (
            "probe-a-db-backup-proof",
            "Unknown",
            {},
            {
                "database-dump": {"state": "unavailable"},
                "upload": {"state": "unavailable"},
            },
        ),
        (
            "probe-a-db-backup-proof",
            "Running",
            {
                "initContainerStatuses": [{"name": "database-dump", "state": {}}],
                "containerStatuses": [
                    {"name": "upload", "state": {"terminated": {"exitCode": 0}}}
                ],
            },
            {
                "database-dump": {"state": "unavailable"},
                "upload": {"state": "terminated", "exit_code": 0},
            },
        ),
    ],
)
def test_failed_job_wait_reports_only_owned_fixed_status(
    proof: Any,
    simulated: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
    job_name: str,
    phase: str,
    statuses: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    failed = False

    def command(args: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal failed
        result = simulated(args, **kwargs)
        if "wait" in args and f"job/{job_name}" in args:
            failed = True
            raise subprocess.TimeoutExpired(
                args, 240, output="temporary-access", stderr="temporary-passphrase"
            )
        if failed and "get" in args and "pods" in args:
            document = json.loads(result.stdout)
            document["items"][0]["status"] = {"phase": phase, **statuses}
            result.stdout = json.dumps(document)
        return result

    monkeypatch.setattr(proof, "run_command", command)
    result = run_phase(proof)
    captured = capsys.readouterr()
    assert result["verdict"] == "fail"
    assert result["stage"] == (
        "restore_completion"
        if job_name == "netpol-backup-restore"
        else "backup_completion"
    )
    assert result["diagnostic"] == {
        "result": "observed",
        "pod_phase": phase.lower(),
        "containers": expected,
    }
    assert "temporary-access" not in json.dumps(result) + captured.out + captured.err
    assert (
        "temporary-passphrase" not in json.dumps(result) + captured.out + captured.err
    )
    calls = [args for args, _ in simulated.calls]
    failed_index = next(
        index
        for index, args in enumerate(calls)
        if "wait" in args and f"job/{job_name}" in args
    )
    after_failure = calls[failed_index + 1 :]
    assert len(after_failure) == 2
    assert "job" in after_failure[0] and "pods" in after_failure[1]
    assert all("--request-timeout=3s" in args for args in after_failure)
    assert all(
        kwargs["timeout"] == 5 for _, kwargs in simulated.calls[failed_index + 1 :]
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong-job-uid",
        "missing-pod",
        "duplicate-pods",
        "wrong-pod-owner",
        "invalid-phase",
        "invalid-state",
        "invalid-exit",
        "read-error",
        "duplicate-status",
        "wrong-status-name",
        "invalid-status-state",
        "multiple-states",
    ],
)
def test_failed_wait_diagnostics_fail_closed_when_status_or_ownership_is_unknown(
    proof: Any, simulated: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    failed = False

    def command(args: list[str], **kwargs: Any) -> SimpleNamespace:
        nonlocal failed
        result = simulated(args, **kwargs)
        if "wait" in args and "job/probe-a-db-backup-proof" in args:
            failed = True
            raise subprocess.CalledProcessError(1, args, stderr="temporary-passphrase")
        if failed and "get" in args and "job" in args and fault == "wrong-job-uid":
            document = json.loads(result.stdout)
            document["metadata"]["uid"] = "00000000-0000-4000-8000-999999999999"
            result.stdout = json.dumps(document)
        if failed and "get" in args and "pods" in args:
            if fault == "read-error":
                raise subprocess.TimeoutExpired(args, 5, stderr="temporary-passphrase")
            document = json.loads(result.stdout)
            pod = document["items"][0]
            if fault == "missing-pod":
                document["items"] = []
            elif fault == "duplicate-pods":
                document["items"].append(copy.deepcopy(pod))
            elif fault == "wrong-pod-owner":
                pod["metadata"]["ownerReferences"][0]["uid"] = (
                    "00000000-0000-4000-8000-999999999999"
                )
            elif fault == "invalid-phase":
                pod["status"]["phase"] = "temporary-passphrase"
            elif fault == "invalid-state":
                pod["status"]["containerStatuses"][0]["state"] = {
                    "unexpected": {"reason": "temporary-passphrase"}
                }
            elif fault == "invalid-exit":
                pod["status"]["containerStatuses"][0]["state"]["terminated"][
                    "exitCode"
                ] = "temporary-passphrase"
            elif fault == "duplicate-status":
                pod["status"]["containerStatuses"].append(
                    copy.deepcopy(pod["status"]["containerStatuses"][0])
                )
            elif fault == "wrong-status-name":
                pod["status"]["containerStatuses"][0]["name"] = "unexpected"
            elif fault == "invalid-status-state":
                pod["status"]["containerStatuses"][0]["state"] = "temporary-passphrase"
            elif fault == "multiple-states":
                pod["status"]["containerStatuses"][0]["state"]["running"] = {}
            result.stdout = json.dumps(document)
        return result

    monkeypatch.setattr(proof, "run_command", command)
    result = run_phase(proof)
    assert result["verdict"] == "fail"
    assert result["diagnostic"] == {"result": "unavailable"}
    assert "temporary-passphrase" not in json.dumps(result)
