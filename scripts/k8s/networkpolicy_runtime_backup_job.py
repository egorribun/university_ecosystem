"""Build a one-shot proof Job from the rendered staging backup CronJob."""

from __future__ import annotations

import copy
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

CA_VOLUME = "proof-ca"
CA_DIRECTORY = "/etc/backup-ca"
CA_CERTIFICATE = f"{CA_DIRECTORY}/ca.crt"


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("unexpected rendered backup CronJob")


def _dns_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 253
        and all(
            len(part) <= 63 and re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", part)
            for part in value.split(".")
        )
    )


def _environment(container: dict[str, Any], expected: set[str]) -> dict[str, Any]:
    entries = container["env"]
    _require(isinstance(entries, list) and not container.get("envFrom"))
    result = {entry["name"]: entry for entry in entries}
    _require(len(entries) == len(result) and set(result) == expected)
    return result


def _secret_reference(entry: dict[str, Any]) -> None:
    _require(set(entry) == {"name", "valueFrom"})
    value_from = entry["valueFrom"]
    _require(set(value_from) == {"secretKeyRef"})
    reference = value_from["secretKeyRef"]
    _require(set(reference) == {"name", "key"})
    _require(_dns_name(reference["name"]) and isinstance(reference["key"], str))
    _require(bool(reference["key"]))


def _container(container: dict[str, Any], name: str, volume_names: list[str]) -> None:
    _require(container["name"] == name)
    image = container["image"]
    _require(
        isinstance(image, str)
        and re.fullmatch(r"\S+@sha256:[0-9a-f]{64}", image) is not None
    )
    security = container["securityContext"]
    _require(security.get("allowPrivilegeEscalation") is False)
    _require(
        security.get("readOnlyRootFilesystem") is True
        and security.get("privileged", False) is False
    )
    capabilities = security["capabilities"]
    _require(
        isinstance(capabilities["drop"], list)
        and "ALL" in capabilities["drop"]
        and not capabilities.get("add")
    )
    _require(security.get("runAsNonRoot", True) is True)
    for field in ("runAsUser", "runAsGroup"):
        if field in security:
            _require(type(security[field]) is int and security[field] > 0)
    _require(
        security.get("seccompProfile", {"type": "RuntimeDefault"}).get("type")
        == "RuntimeDefault"
    )
    _require(security.get("procMount", "Default") == "Default")
    _require(not container.get("volumeDevices"))
    _require(
        isinstance(container["command"], list) and isinstance(container["args"], list)
    )
    commands = container["command"] + container["args"]
    _require(
        bool(commands)
        and all(isinstance(part, str) and bool(part) for part in commands)
    )
    forbidden = (
        "--no-check-certificate",
        "--insecure",
        "--ca-cert",
        "rclone_no_check_certificate",
        "rclone_ca_cert",
    )
    _require(
        not any(option in part.lower() for option in forbidden for part in commands)
    )
    ca_path = PurePosixPath(CA_DIRECTORY)
    for mount in container["volumeMounts"]:
        _require(mount["name"] in volume_names and mount["name"] != CA_VOLUME)
        value = mount["mountPath"]
        _require(isinstance(value, str))
        path = PurePosixPath(value)
        _require(path.is_absolute() and str(path) == value and ".." not in path.parts)
        _require(
            path != ca_path
            and path not in ca_path.parents
            and ca_path not in path.parents
        )


def _https_endpoint(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.startswith("https://")
        or any(char.isspace() for char in value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        return (
            bool(parsed.hostname)
            and not parsed.netloc.endswith(":")
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (parsed.port is None or 0 < parsed.port <= 65535)
        )
    except ValueError:
        return False


def build_backup_job(cronjob: dict[str, Any], *, ca_configmap: str) -> dict[str, Any]:
    """Copy the chart workload into a Job, adding only the upload's CA trust.

    The caller renders the staging CronJob with its chosen HTTPS endpoint and
    provisions ``ca_configmap`` with a ``ca.crt`` key. The input is not changed.
    """
    try:
        _require(_dns_name(ca_configmap))
        _require(cronjob["apiVersion"] == "batch/v1" and cronjob["kind"] == "CronJob")
        metadata = cronjob["metadata"]
        name, namespace, labels = (
            metadata["name"],
            metadata["namespace"],
            metadata["labels"],
        )
        _require(
            _dns_name(name) and _dns_name(f"{name}-proof") and _dns_name(namespace)
        )
        _require("." not in namespace and len(namespace) <= 63)
        _require(
            isinstance(labels, dict)
            and labels.get("app.kubernetes.io/component") == "backup"
        )

        job_spec = cronjob["spec"]["jobTemplate"]["spec"]
        _require(
            job_spec.get("parallelism", 1) == 1 and job_spec.get("completions", 1) == 1
        )
        _require(
            not job_spec.get("selector")
            and not job_spec.get("manualSelector")
            and not job_spec.get("suspend")
        )
        template = job_spec["template"]
        pod_labels = template["metadata"]["labels"]
        for label in (
            "app.kubernetes.io/name",
            "app.kubernetes.io/instance",
            "app.kubernetes.io/component",
        ):
            _require(isinstance(pod_labels.get(label), str) and bool(pod_labels[label]))
            _require(pod_labels[label] == labels.get(label))
        pod = template["spec"]
        _require(_dns_name(pod["serviceAccountName"]))
        _require(
            pod["automountServiceAccountToken"] is False
            and pod["restartPolicy"] == "OnFailure"
        )
        for field in (
            "hostNetwork",
            "hostPID",
            "hostIPC",
            "shareProcessNamespace",
            "hostAliases",
            "ephemeralContainers",
        ):
            _require(not pod.get(field))
        security = pod["securityContext"]
        _require(security.get("runAsNonRoot") is True)
        _require(type(security.get("runAsUser")) is int and security["runAsUser"] > 0)
        for field in ("runAsGroup", "fsGroup"):
            if field in security:
                _require(type(security[field]) is int and security[field] > 0)
        _require(security.get("seccompProfile", {}).get("type") == "RuntimeDefault")
        pull_secrets = pod.get("imagePullSecrets", [])
        _require(isinstance(pull_secrets, list))
        for secret in pull_secrets:
            _require(set(secret) == {"name"} and _dns_name(secret["name"]))
        volumes = pod["volumes"]
        _require(isinstance(volumes, list))
        volume_names = [item["name"] for item in volumes]
        _require(
            len(volume_names) == len(set(volume_names))
            and CA_VOLUME not in volume_names
        )
        _require(all("hostPath" not in item for item in volumes))
        _require(len(pod["initContainers"]) == 1 and len(pod["containers"]) == 1)
        init, upload = pod["initContainers"][0], pod["containers"][0]
        _container(init, "database-dump", volume_names)
        _container(upload, "upload", volume_names)
        init_env = _environment(init, {"DATABASE_URL", "HOME"})
        upload_env = _environment(
            upload,
            {
                "BACKUP_BUCKET",
                "RCLONE_CONFIG_BACKUP_TYPE",
                "RCLONE_CONFIG_BACKUP_PROVIDER",
                "RCLONE_CONFIG_BACKUP_ENDPOINT",
                "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID",
                "RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY",
                "HOME",
            },
        )
        _secret_reference(init_env["DATABASE_URL"])
        for key in (
            "RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID",
            "RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY",
        ):
            _secret_reference(upload_env[key])
        for env in (init_env, upload_env):
            home = env["HOME"]
            _require(
                set(home) == {"name", "value"}
                and isinstance(home["value"], str)
                and bool(home["value"])
            )
        for key, value in (
            ("RCLONE_CONFIG_BACKUP_TYPE", "s3"),
            ("RCLONE_CONFIG_BACKUP_PROVIDER", "Other"),
        ):
            _require(upload_env[key] == {"name": key, "value": value})
        for key in ("BACKUP_BUCKET", "RCLONE_CONFIG_BACKUP_ENDPOINT"):
            entry = upload_env[key]
            _require(
                set(entry) == {"name", "value"}
                and isinstance(entry["value"], str)
                and bool(entry["value"])
            )
        _require(_https_endpoint(upload_env["RCLONE_CONFIG_BACKUP_ENDPOINT"]["value"]))
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("unexpected rendered backup CronJob") from exc

    job = copy.deepcopy(
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": f"{name}-proof",
                "namespace": namespace,
                "labels": labels,
            },
            "spec": job_spec,
        }
    )
    job_pod = job["spec"]["template"]["spec"]
    job_pod["volumes"].append({"name": CA_VOLUME, "configMap": {"name": ca_configmap}})
    job_upload = job_pod["containers"][0]
    job_upload["volumeMounts"].append(
        {"name": CA_VOLUME, "mountPath": CA_DIRECTORY, "readOnly": True}
    )
    job_upload["env"].append({"name": "RCLONE_CA_CERT", "value": CA_CERTIFICATE})
    return job
