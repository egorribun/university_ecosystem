"""Offline contracts for the rendered backup CronJob proof fixture."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import _render_staging

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/k8s"))


def test_backup_job_helper_is_available() -> None:
    assert importlib.util.find_spec("networkpolicy_runtime_backup_job") is not None


@pytest.fixture(scope="module")
def proof() -> Any:
    name = "networkpolicy_runtime_backup_job"
    assert importlib.util.find_spec(name) is not None
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def rendered_cronjob() -> dict[str, Any]:
    resources = _render_staging(
        "--set",
        "backup.enabled=true",
        "--set-string",
        "backup.minioEndpoint=https://backup.probe.invalid:443",
        release_name="backup-proof",
    )
    matches = [
        resource
        for resource in resources
        if resource.get("kind") == "CronJob"
        and resource["metadata"]["labels"].get("app.kubernetes.io/component")
        == "backup"
    ]
    assert len(matches) == 1
    return matches[0]


def _pod(cronjob: dict[str, Any]) -> dict[str, Any]:
    return cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def _upload(cronjob: dict[str, Any]) -> dict[str, Any]:
    return _pod(cronjob)["containers"][0]


def test_job_preserves_the_rendered_workload_and_adds_only_upload_ca(
    proof: Any, rendered_cronjob: dict[str, Any]
) -> None:
    before = copy.deepcopy(rendered_cronjob)
    job = proof.build_backup_job(rendered_cronjob, ca_configmap="proof-trust-ca")

    assert job["apiVersion"] == "batch/v1"
    assert job["kind"] == "Job"
    assert job["metadata"] == {
        "name": before["metadata"]["name"] + "-proof",
        "namespace": before["metadata"]["namespace"],
        "labels": before["metadata"]["labels"],
    }
    expected = copy.deepcopy(before["spec"]["jobTemplate"]["spec"])
    pod = expected["template"]["spec"]
    pod["volumes"].append({"name": "proof-ca", "configMap": {"name": "proof-trust-ca"}})
    pod["containers"][0]["volumeMounts"].append(
        {"name": "proof-ca", "mountPath": "/etc/backup-ca", "readOnly": True}
    )
    pod["containers"][0]["env"].append(
        {"name": "RCLONE_CA_CERT", "value": "/etc/backup-ca/ca.crt"}
    )
    assert job["spec"] == expected
    assert rendered_cronjob == before
    job["spec"]["template"]["metadata"]["labels"]["fixture"] = "changed"
    assert rendered_cronjob == before


def test_job_allows_render_without_pull_secrets(
    proof: Any, rendered_cronjob: dict[str, Any]
) -> None:
    cronjob = copy.deepcopy(rendered_cronjob)
    _pod(cronjob).pop("imagePullSecrets")
    job = proof.build_backup_job(cronjob, ca_configmap="proof-ca")
    assert "imagePullSecrets" not in job["spec"]["template"]["spec"]


def test_preserves_safe_changes_in_rendered_commands_and_hardening(
    proof: Any, rendered_cronjob: dict[str, Any]
) -> None:
    cronjob = copy.deepcopy(rendered_cronjob)
    pod = _pod(cronjob)
    pod["initContainers"][0]["args"][0] += "\n"
    pod["containers"][0]["args"][0] += "true\n"
    pod["securityContext"]["runAsUser"] = 1001
    pod["securityContext"].pop("runAsGroup")
    pod["securityContext"].pop("fsGroup")
    pod["containers"][0]["securityContext"]["runAsNonRoot"] = True
    pod["containers"][0]["securityContext"]["runAsUser"] = 1001
    pod["containers"][0]["securityContext"]["runAsGroup"] = 1001
    pod["containers"][0]["resources"]["limits"]["memory"] = "512Mi"
    cronjob["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] = 600
    before = copy.deepcopy(cronjob)
    job = proof.build_backup_job(cronjob, ca_configmap="proof-ca")
    result = job["spec"]["template"]["spec"]
    assert result["initContainers"][0] == pod["initContainers"][0]
    assert result["containers"][0]["args"] == pod["containers"][0]["args"]
    assert (
        result["containers"][0]["securityContext"]
        == pod["containers"][0]["securityContext"]
    )
    assert result["containers"][0]["resources"] == pod["containers"][0]["resources"]
    assert result["securityContext"] == pod["securityContext"]
    assert job["spec"]["activeDeadlineSeconds"] == 600
    assert cronjob == before


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://backup.probe.invalid:443",
        "https://",
        "https://host:bad",
        "https://host:",
    ],
)
def test_rejects_non_https_or_malformed_endpoint(
    proof: Any, rendered_cronjob: dict[str, Any], endpoint: str
) -> None:
    cronjob = copy.deepcopy(rendered_cronjob)
    for item in _upload(cronjob)["env"]:
        if item["name"] == "RCLONE_CONFIG_BACKUP_ENDPOINT":
            item["value"] = endpoint
    before = copy.deepcopy(cronjob)
    with pytest.raises(ValueError):
        proof.build_backup_job(cronjob, ca_configmap="proof-ca")
    assert cronjob == before


@pytest.mark.parametrize(
    "name",
    [
        "RCLONE_NO_CHECK_CERTIFICATE",
        "RCLONE_INSECURE_SKIP_VERIFY",
        "RCLONE_CONFIG_BACKUP_NO_CHECK_CERTIFICATE",
        "RCLONE_CA_CERT",
    ],
)
def test_rejects_existing_tls_overrides(
    proof: Any, rendered_cronjob: dict[str, Any], name: str
) -> None:
    cronjob = copy.deepcopy(rendered_cronjob)
    _upload(cronjob)["env"].append({"name": name, "value": "true"})
    with pytest.raises(ValueError):
        proof.build_backup_job(cronjob, ca_configmap="proof-ca")


@pytest.mark.parametrize(
    "change",
    [
        "wrong_kind",
        "invalid_namespace",
        "invalid_pull_secret",
        "parallel_job",
        "wrong_labels",
        "extra_container",
        "wrong_init",
        "mutable_init_image",
        "mutable_upload_image",
        "altered_upload_command",
        "extra_env_from",
        "duplicate_endpoint",
        "inline_secret",
        "missing_security",
        "privileged_container",
        "unconfined_container",
        "extra_capability",
        "host_network",
        "host_volume",
        "ca_volume_collision",
        "ca_mount_collision",
    ],
)
def test_rejects_unexpected_rendered_workload(
    proof: Any, rendered_cronjob: dict[str, Any], change: str
) -> None:
    cronjob = copy.deepcopy(rendered_cronjob)
    pod = _pod(cronjob)
    init = pod["initContainers"][0]
    upload = pod["containers"][0]
    if change == "wrong_kind":
        cronjob["kind"] = "Job"
    elif change == "invalid_namespace":
        cronjob["metadata"]["namespace"] = "invalid.namespace"
    elif change == "invalid_pull_secret":
        pod["imagePullSecrets"] = [{"name": "BAD_NAME"}]
    elif change == "parallel_job":
        cronjob["spec"]["jobTemplate"]["spec"]["parallelism"] = 2
    elif change == "wrong_labels":
        cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"].pop(
            "app.kubernetes.io/component"
        )
    elif change == "extra_container":
        pod["containers"].append(copy.deepcopy(upload))
    elif change == "wrong_init":
        init["name"] = "other"
    elif change == "mutable_init_image":
        init["image"] = init["image"].split("@")[0]
    elif change == "mutable_upload_image":
        upload["image"] = upload["image"].split("@")[0]
    elif change == "altered_upload_command":
        upload["args"][0] += "rclone --no-check-certificate version\n"
    elif change == "extra_env_from":
        upload["envFrom"] = [{"configMapRef": {"name": "extra"}}]
    elif change == "duplicate_endpoint":
        endpoint = next(
            item
            for item in upload["env"]
            if item["name"] == "RCLONE_CONFIG_BACKUP_ENDPOINT"
        )
        upload["env"].append(copy.deepcopy(endpoint))
    elif change == "inline_secret":
        item = next(
            item
            for item in upload["env"]
            if item["name"] == "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID"
        )
        item.pop("valueFrom")
        item["value"] = "unexpected"
    elif change == "missing_security":
        upload["securityContext"]["readOnlyRootFilesystem"] = False
    elif change == "privileged_container":
        upload["securityContext"]["privileged"] = True
    elif change == "unconfined_container":
        upload["securityContext"]["seccompProfile"] = {"type": "Unconfined"}
    elif change == "extra_capability":
        upload["securityContext"]["capabilities"]["add"] = ["NET_ADMIN"]
    elif change == "host_network":
        pod["hostNetwork"] = True
    elif change == "host_volume":
        pod["volumes"].append({"name": "host-volume", "hostPath": {}})
    elif change == "ca_volume_collision":
        pod["volumes"].append({"name": "proof-ca", "emptyDir": {}})
    elif change == "ca_mount_collision":
        upload["volumeMounts"].append({"name": "tmp", "mountPath": "/etc/backup-ca"})
    before = copy.deepcopy(cronjob)
    with pytest.raises(ValueError):
        proof.build_backup_job(cronjob, ca_configmap="proof-ca")
    assert cronjob == before


@pytest.mark.parametrize("name", ["", "INVALID", "../wrong", "bad_name", "a" * 254])
def test_rejects_invalid_ca_configmap_names(
    proof: Any, rendered_cronjob: dict[str, Any], name: str
) -> None:
    with pytest.raises(ValueError):
        proof.build_backup_job(rendered_cronjob, ca_configmap=name)


@pytest.mark.parametrize(
    "cronjob", [None, {}, {"apiVersion": "batch/v1", "kind": "CronJob"}]
)
def test_rejects_missing_rendered_shape(proof: Any, cronjob: Any) -> None:
    with pytest.raises(ValueError):
        proof.build_backup_job(cronjob, ca_configmap="proof-ca")
