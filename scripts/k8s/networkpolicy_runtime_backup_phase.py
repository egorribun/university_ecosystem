"""Positive backup/restore proof inside the caller's disposable Kind cluster.

The caller must already have applied the rendered policy and provisioned a
dedicated S3 endpoint with fresh storage. The test bucket may be absent or
empty when the backup starts. The caller owns the disposable namespace and its
teardown. Raw command output, Secrets and credentials are excluded from receipts.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from networkpolicy_runtime_backup_job import build_backup_job
from networkpolicy_runtime_backup_postgres import (
    POSTGRES_NAME,
    RESTORE_NAME,
    fixture_objects,
)
from networkpolicy_runtime_backup_restore import RESTORE_RECEIPT, build_restore_job
from networkpolicy_runtime_kube import run_command

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = "probe-a"
CA_CONFIGMAP = "netpol-backup-ca"
RESTORE_JOB = "netpol-backup-restore"
MAX_RESPONSE = 262144
_UID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_NAME = re.compile(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?")
_SECRET_KEY = re.compile(r"[-._a-zA-Z0-9]+")
_DIGEST = re.compile(r"(?:[^\s]*@)?(sha256:[0-9a-f]{64})")


def _name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value) <= 253
        or any(not _NAME.fullmatch(part) or len(part) > 63 for part in value.split("."))
    ):
        raise ValueError("invalid resource name")
    return value


def _uid(value: Any) -> str:
    if not isinstance(value, str) or not _UID.fullmatch(value):
        raise ValueError("invalid resource identity")
    return value


def _reference(container: dict[str, Any], name: str) -> tuple[str, str]:
    entries = [item for item in container["env"] if item["name"] == name]
    if len(entries) != 1:
        raise ValueError("ambiguous Secret reference")
    ref = entries[0]["valueFrom"]["secretKeyRef"]
    secret_name, key = _name(ref["name"]), ref["key"]
    if (
        not isinstance(key, str)
        or len(key) > 253
        or not _SECRET_KEY.fullmatch(key)
        or key in {".", ".."}
    ):
        raise ValueError("invalid Secret key")
    return secret_name, key


def _command(*args: str, stdin: str | None = None, timeout: float = 15) -> str:
    result = run_command(
        ["kubectl", "-n", NAMESPACE, *args], stdin=stdin, timeout=timeout
    )
    output = result.stdout
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_RESPONSE:
        raise ValueError("oversized response")
    return output


def _json_command(
    *args: str, stdin: str | None = None, timeout: float = 15
) -> dict[str, Any]:
    result = json.loads(_command(*args, stdin=stdin, timeout=timeout))
    if not isinstance(result, dict):
        raise ValueError("invalid response")
    return result


def _matches(expected: Any, observed: Any) -> bool:
    """Match submitted fields while allowing Kubernetes to add default fields."""
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _matches(value, observed[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(
                _matches(left, right)
                for left, right in zip(expected, observed, strict=True)
            )
        )
    return expected == observed


def _metadata(document: dict[str, Any], *, kind: str, name: str) -> str:
    metadata = document["metadata"]
    if (
        document["kind"] != kind
        or document.get("apiVersion") != ("batch/v1" if kind == "Job" else "v1")
        or metadata["namespace"] != NAMESPACE
        or metadata["name"] != name
    ):
        raise ValueError("resource identity differs")
    return _uid(metadata["uid"])


def _create(obj: dict[str, Any], *, identity: bool = False) -> str:
    metadata = obj["metadata"]
    name = _name(metadata["name"])
    if metadata["namespace"] != NAMESPACE or len(json.dumps(obj)) > MAX_RESPONSE:
        raise ValueError("invalid fixture object")
    payload = json.dumps(obj, separators=(",", ":"))
    if identity:
        result = _json_command("create", "-f", "-", "-o", "json", stdin=payload)
        return _metadata(result, kind=obj["kind"], name=name)
    # Avoid asking the API to echo the body of any Secret.
    _command("create", "-f", "-", "-o", "name", stdin=payload)
    return ""


def _image_id(status: dict[str, Any]) -> str:
    value = status.get("imageID")
    match = _DIGEST.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError("missing resolved image")
    # Only the immutable digest is retained; never expose arbitrary runtime text.
    return match.group(1)


def _containers(
    pod: dict[str, Any], expected: dict[str, Any], *, completed: bool
) -> dict[str, str]:
    images: dict[str, str] = {}
    for spec_key, status_key in (
        ("initContainers", "initContainerStatuses"),
        ("containers", "containerStatuses"),
    ):
        wanted = expected.get(spec_key, [])
        actual = pod["spec"].get(spec_key, [])
        statuses = pod["status"].get(status_key, [])
        if len(wanted) != len(actual) or len(wanted) != len(statuses):
            raise ValueError("container set differs")
        for desired, observed in zip(wanted, actual, strict=True):
            for key in (
                "name",
                "image",
                "command",
                "args",
                "env",
                "envFrom",
                "volumeMounts",
                "imagePullPolicy",
                "resources",
                "readinessProbe",
            ):
                if key in desired:
                    if not _matches(desired[key], observed.get(key)):
                        raise ValueError("container configuration differs")
                elif key in {
                    "command",
                    "args",
                    "env",
                    "envFrom",
                    "volumeMounts",
                } and observed.get(key):
                    raise ValueError("unexpected container configuration")
            if observed.get("securityContext", {}) != desired.get(
                "securityContext", {}
            ):
                raise ValueError("container security context differs")
            name = desired["name"]
            matches = [item for item in statuses if item.get("name") == name]
            if (
                len(matches) != 1
                or type(matches[0].get("restartCount")) is not int
                or matches[0]["restartCount"] != 0
            ):
                raise ValueError("container status differs")
            status = matches[0]
            if completed:
                exit_code = (
                    status.get("state", {}).get("terminated", {}).get("exitCode")
                )
                if type(exit_code) is not int or exit_code != 0:
                    raise ValueError("container did not succeed")
            elif status.get("ready") is not True:
                raise ValueError("container is not ready")
            images[name] = _image_id(status)
    return images


def _pod_spec(pod: dict[str, Any], template: dict[str, Any]) -> None:
    expected = template["spec"]
    actual = pod["spec"]
    for key in (
        "serviceAccountName",
        "automountServiceAccountToken",
        "restartPolicy",
        "securityContext",
        "volumes",
        "enableServiceLinks",
    ):
        if key in expected and not _matches(expected[key], actual.get(key)):
            raise ValueError("pod configuration differs")
    # Kubernetes omits hostNetwork when its non-pointer value is false.
    if actual.get("hostNetwork", False) is not False:
        raise ValueError("unexpected host network")
    labels = template.get("metadata", {}).get("labels", {})
    if not _matches(labels, pod["metadata"].get("labels", {})):
        raise ValueError("pod labels differ")


def _postgres(pod: dict[str, Any], created_uid: str) -> dict[str, Any]:
    _command(
        "wait",
        "--for=condition=Ready",
        f"pod/{POSTGRES_NAME}",
        "--timeout=120s",
        timeout=130,
    )
    observed = _json_command("get", "pod", POSTGRES_NAME, "-o", "json")
    if _metadata(observed, kind="Pod", name=POSTGRES_NAME) != created_uid:
        raise ValueError("PostgreSQL identity changed")
    if observed["status"].get("phase") != "Running" or not any(
        item.get("type") == "Ready" and item.get("status") == "True"
        for item in observed["status"].get("conditions", [])
    ):
        raise ValueError("PostgreSQL is not ready")
    _pod_spec(observed, {"metadata": pod["metadata"], "spec": pod["spec"]})
    images = _containers(observed, pod["spec"], completed=False)
    return {"name": POSTGRES_NAME, "uid": created_uid, "image_id": images["postgres"]}


class _JobWaitFailure(Exception):
    def __init__(self, diagnostic: dict[str, Any]) -> None:
        super().__init__()
        self.diagnostic = diagnostic


def _diagnostic_container(
    status: dict[str, Any], key: str, name: str
) -> dict[str, Any]:
    entries = status.get(key, [])
    if not isinstance(entries, list) or len(entries) > 1:
        raise ValueError("ambiguous container status")
    if not entries:
        return {"state": "unavailable"}
    entry = entries[0]
    if not isinstance(entry, dict) or entry.get("name") != name:
        raise ValueError("unexpected container status")
    state = entry.get("state", {})
    if not isinstance(state, dict):
        raise ValueError("invalid container state")
    if not state:
        return {"state": "unavailable"}
    if len(state) != 1:
        raise ValueError("ambiguous container state")
    kind, details = next(iter(state.items()))
    if kind not in {"waiting", "running", "terminated"} or not isinstance(
        details, dict
    ):
        raise ValueError("invalid container state")
    if kind != "terminated":
        return {"state": kind}
    exit_code = details.get("exitCode")
    if type(exit_code) is not int or not -(2**31) <= exit_code < 2**31:
        raise ValueError("invalid exit code")
    return {"state": "terminated", "exit_code": exit_code}


def _job_diagnostic(job: dict[str, Any], created_uid: str) -> dict[str, Any]:
    """Read only the created Job and its single controlled Pod after a failed wait."""
    try:
        name = _name(job["metadata"]["name"])
        _uid(created_uid)
        observed = _json_command(
            "--request-timeout=3s", "get", "job", name, "-o", "json", timeout=5
        )
        if _metadata(observed, kind="Job", name=name) != created_uid:
            raise ValueError("Job identity changed")
        response = _json_command(
            "--request-timeout=3s",
            "get",
            "pods",
            "-l",
            f"batch.kubernetes.io/controller-uid={created_uid}",
            "-o",
            "json",
            timeout=5,
        )
        pods = response["items"]
        if not isinstance(pods, list) or len(pods) != 1:
            raise ValueError("ambiguous Job pod")
        pod = pods[0]
        metadata = pod["metadata"]
        pod_name = _name(metadata["name"])
        _uid(metadata["uid"])
        owners = metadata.get("ownerReferences", [])
        if (
            metadata.get("namespace") != NAMESPACE
            or not pod_name.startswith(name + "-")
            or len(owners) != 1
            or not _matches(
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "name": name,
                    "uid": created_uid,
                    "controller": True,
                },
                owners[0],
            )
        ):
            raise ValueError("Job pod identity differs")
        status = pod["status"]
        phase = status.get("phase")
        if phase not in {"Pending", "Running", "Succeeded", "Failed", "Unknown"}:
            raise ValueError("invalid pod phase")
        names = (
            ("readback", "restore")
            if name == RESTORE_JOB
            else ("database-dump", "upload")
        )
        containers = {
            names[0]: _diagnostic_container(status, "initContainerStatuses", names[0]),
            names[1]: _diagnostic_container(status, "containerStatuses", names[1]),
        }
        return {
            "result": "observed",
            "pod_phase": phase.lower(),
            "containers": containers,
        }
    except (Exception, SystemExit):
        return {"result": "unavailable"}


def _job(job: dict[str, Any], created_uid: str) -> dict[str, Any]:
    name = _name(job["metadata"]["name"])
    try:
        _command(
            "wait",
            "--for=condition=complete",
            f"job/{name}",
            "--timeout=240s",
            timeout=250,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise _JobWaitFailure(_job_diagnostic(job, created_uid)) from None
    observed = _json_command("get", "job", name, "-o", "json")
    status = observed["status"]
    if (
        _metadata(observed, kind="Job", name=name) != created_uid
        or type(status.get("succeeded")) is not int
        or status["succeeded"] != 1
        or status.get("failed", 0) != 0
        or status.get("active", 0) != 0
        or not any(
            item.get("type") == "Complete" and item.get("status") == "True"
            for item in status.get("conditions", [])
        )
    ):
        raise ValueError("Job did not complete")
    result = _json_command(
        "get",
        "pods",
        "-l",
        f"batch.kubernetes.io/controller-uid={created_uid}",
        "-o",
        "json",
    )
    pods = result["items"]
    if not isinstance(pods, list) or len(pods) != 1:
        raise ValueError("ambiguous Job pods")
    listed = pods[0]["metadata"]
    pod_name = _name(listed["name"])
    listed_uid = _uid(listed["uid"])
    if listed.get("namespace") != NAMESPACE:
        raise ValueError("Job pod namespace differs")
    pod = _json_command("get", "pod", pod_name, "-o", "json")
    if _metadata(pod, kind="Pod", name=pod_name) != listed_uid:
        raise ValueError("Job pod identity changed")
    metadata = pod["metadata"]
    owners = metadata.get("ownerReferences", [])
    if (
        not pod_name.startswith(name + "-")
        or len(owners) != 1
        or not _matches(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "name": name,
                "uid": created_uid,
                "controller": True,
            },
            owners[0],
        )
        or pod["status"].get("phase") != "Succeeded"
    ):
        raise ValueError("Job pod identity differs")
    template = job["spec"]["template"]
    _pod_spec(pod, template)
    images = _containers(pod, template["spec"], completed=True)
    return {
        "name": name,
        "uid": created_uid,
        "pod": {"name": pod_name, "uid": listed_uid, "image_ids": images},
    }


def _prerequisites(
    job: dict[str, Any], *, ca_certificate: str, access_key: str, secret_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for value, limit in (
        (ca_certificate, 65536),
        (access_key, 1024),
        (secret_key, 1024),
    ):
        if (
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8")) > limit
            or "\x00" in value
        ):
            raise ValueError("invalid fixture input")
    if job["metadata"]["namespace"] != NAMESPACE:
        raise ValueError("unexpected namespace")
    pod = job["spec"]["template"]["spec"]
    if pod["serviceAccountName"] != "probe-a-backup":
        raise ValueError("unexpected backup service account")
    dump, upload = pod["initContainers"][0], pod["containers"][0]
    source_name, source_key = _reference(dump, "DATABASE_URL")
    access = _reference(upload, "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID")
    secret = _reference(upload, "RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY")
    if access == secret or (source_name, source_key) in {access, secret}:
        raise ValueError("conflicting Secret keys")
    fixture = fixture_objects(
        ROOT,
        NAMESPACE,
        dump["image"],
        source_secret_name=source_name,
        source_secret_key=source_key,
    )
    if not isinstance(fixture, list) or len(fixture) > 15:
        raise ValueError("invalid PostgreSQL fixture")
    objects = [
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": pod["serviceAccountName"],
                "namespace": NAMESPACE,
                "labels": job["metadata"]["labels"],
            },
            "automountServiceAccountToken": False,
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": CA_CONFIGMAP, "namespace": NAMESPACE},
            "data": {"ca.crt": ca_certificate},
        },
        *fixture,
    ]
    store_names: set[str] = set()
    for (secret_name, key), value in ((access, access_key), (secret, secret_key)):
        existing = [
            obj
            for obj in objects
            if obj.get("kind") == "Secret" and obj["metadata"]["name"] == secret_name
        ]
        if existing:
            if (
                len(existing) != 1
                or secret_name not in store_names | {source_name}
                or key in existing[0]["stringData"]
            ):
                raise ValueError("conflicting fixture Secret")
            existing[0]["stringData"][key] = value
        else:
            objects.append(
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": secret_name, "namespace": NAMESPACE},
                    "stringData": {key: value},
                }
            )
        store_names.add(secret_name)
    identities = [(obj["kind"], obj["metadata"]["name"]) for obj in objects]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate fixture objects")
    postgres = [
        obj
        for obj in objects
        if obj["kind"] == "Pod" and obj["metadata"]["name"] == POSTGRES_NAME
    ]
    if len(postgres) != 1:
        raise ValueError("missing PostgreSQL pod")
    return objects, postgres[0]


def run_backup_phase(
    cronjob: dict[str, Any], *, ca_certificate: str, access_key: str, secret_key: str
) -> dict[str, Any]:
    """Return bounded positive evidence or a sanitized fixed-stage failure."""
    result: dict[str, Any] = {
        "verdict": "fail",
        "stage": "input",
        "backup_job_attempted": False,
    }
    try:
        backup = build_backup_job(cronjob, ca_configmap=CA_CONFIGMAP)
        restore = build_restore_job(
            backup, name=RESTORE_JOB, restore_secret=RESTORE_NAME
        )
        objects, postgres = _prerequisites(
            backup,
            ca_certificate=ca_certificate,
            access_key=access_key,
            secret_key=secret_key,
        )
        result["stage"] = "prerequisites"
        postgres_uid = ""
        for obj in objects:
            if obj is postgres:
                postgres_uid = _create(obj, identity=True)
            else:
                _create(obj)
        result["stage"] = "postgres_ready"
        result["postgres"] = _postgres(postgres, postgres_uid)
        result["stage"] = "backup_create"
        result["backup_job_attempted"] = True
        backup_uid = _create(backup, identity=True)
        result["stage"] = "backup_completion"
        result["backup_job"] = _job(backup, backup_uid)
        result["stage"] = "restore_create"
        restore_uid = _create(restore, identity=True)
        result["stage"] = "restore_completion"
        result["restore_job"] = _job(restore, restore_uid)
        result["stage"] = "restore_receipt"
        pod_name = result["restore_job"]["pod"]["name"]
        marker = _command("logs", pod_name, "-c", "restore", "--limit-bytes=128")
        if marker not in (RESTORE_RECEIPT, RESTORE_RECEIPT + "\n"):
            raise ValueError("restore receipt differs")
        restore_pod = _json_command("get", "pod", pod_name, "-o", "json")
        if (
            _metadata(restore_pod, kind="Pod", name=pod_name)
            != result["restore_job"]["pod"]["uid"]
        ):
            raise ValueError("restore pod identity changed")
        result.update(
            verdict="pass",
            stage="complete",
            namespace=NAMESPACE,
            restore_receipt=RESTORE_RECEIPT,
        )
    except _JobWaitFailure as failure:
        result["diagnostic"] = failure.diagnostic
        return result
    except (Exception, SystemExit):
        # Command exceptions can carry Secret-bearing stdin or stderr. Do not log,
        # stringify, attach, or return the exception, even for diagnostics.
        return result
    return result
