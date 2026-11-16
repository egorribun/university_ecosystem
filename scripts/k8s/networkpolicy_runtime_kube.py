"""kubectl, helm and in-pod exec helpers for the NetworkPolicy runtime proof."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from networkpolicy_runtime_standins import PROBE_SRC

PROBE_TIMEOUT = 3.0
EXEC_OVERHEAD_SECONDS = 60


@dataclass(frozen=True)
class CreatedPod:
    """Identity returned by a successful create, never an observed preexisting Pod."""

    namespace: str
    name: str
    uid: str


@dataclass
class Pod:
    namespace: str
    name: str
    ip: str = ""
    uid: str = ""
    created: CreatedPod | None = None


def run_command(
    cmd: list[str], *, stdin: str | None = None, timeout: float = 300.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv list of pinned kubectl/helm/kind tools, no shell
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=True,
    )


def kubectl(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return run_command(["kubectl", *args], stdin=stdin)


def kubectl_json(*args: str) -> dict[str, Any]:
    loaded = json.loads(kubectl(*args).stdout)
    if not isinstance(loaded, dict):
        raise SystemExit("kubectl returned a non-object document")
    return loaded


def apply_objects(objects: list[dict[str, Any]]) -> None:
    payload = json.dumps({"apiVersion": "v1", "kind": "List", "items": objects})
    kubectl("apply", "-f", "-", stdin=payload)


def create_pod(pod: dict[str, Any]) -> CreatedPod:
    """Create the one matrix fixture whose identity must later be retired."""
    metadata = pod.get("metadata", {})
    if (
        not isinstance(metadata, dict)
        or pod.get("apiVersion") != "v1"
        or pod.get("kind") != "Pod"
        or metadata.get("namespace") != "probe-a"
        or metadata.get("name") != "probe-a-ws-hub"
        or any(key in metadata for key in ("uid", "generateName", "ownerReferences"))
    ):
        raise ValueError("unexpected ws-hub fixture")
    result = run_command(
        ["kubectl", "create", "-f", "-", "-o", "json"],
        stdin=json.dumps(pod),
        timeout=30,
    )
    created = json.loads(result.stdout)
    if not isinstance(created, dict) or not isinstance(created.get("metadata"), dict):
        raise ValueError("create returned an invalid ws-hub fixture identity")
    created_metadata = created["metadata"]
    uid = created_metadata.get("uid")
    if (
        created.get("apiVersion") != "v1"
        or created.get("kind") != "Pod"
        or created_metadata.get("namespace") != "probe-a"
        or created_metadata.get("name") != "probe-a-ws-hub"
        or not isinstance(uid, str)
        or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
            uid,
        )
    ):
        raise ValueError("create returned an invalid ws-hub fixture identity")
    return CreatedPod("probe-a", "probe-a-ws-hub", uid)


def helm_template(
    release: str, chart: Path, values: Path, extra: list[str], namespace: str
) -> list[dict[str, Any]]:
    result = run_command(
        [
            "helm",
            "template",
            release,
            str(chart),
            "--dependency-update=false",
            "--namespace",
            namespace,
            "--values",
            str(values),
            *extra,
        ],
        timeout=180,
    )
    return [item for item in yaml.safe_load_all(result.stdout) if item]


def find(resources: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    matches = [
        r for r in resources if r.get("kind") == kind and r["metadata"]["name"] == name
    ]
    if len(matches) != 1:
        raise SystemExit(f"expected one {kind}/{name}, found {len(matches)}")
    return matches[0]


def pod_template_labels(
    resources: list[dict[str, Any]], kind: str, name: str
) -> dict[str, str]:
    return dict(find(resources, kind, name)["spec"]["template"]["metadata"]["labels"])


def cronjob_template_labels(
    resources: list[dict[str, Any]], name: str
) -> dict[str, str]:
    """Return the pod-template labels of a rendered CronJob's Job, fail closed."""
    job = find(resources, "CronJob", name)["spec"]["jobTemplate"]["spec"]["template"]
    return dict(job["metadata"]["labels"])


def run_in_pod(
    pod: Pod,
    source: str,
    args: list[str],
    *,
    stdin: str = "",
    timeout: float = PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Run a stdlib Python program in a pod's network namespace; return its JSON verdict."""
    cmd = [
        "kubectl",
        "-n",
        pod.namespace,
        "exec",
        "-i",
        pod.name,
        "--",
        "python3",
        "-I",
        "-c",
        source,
        *args,
    ]
    try:
        result = subprocess.run(  # noqa: S603 - fixed kubectl exec argv into the run's own probe pod, no shell
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout + EXEC_OVERHEAD_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"result": "exec-timeout"}
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or not lines:
        return {"result": "exec-error"}
    try:
        parsed = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"result": "exec-error"}
    return parsed if isinstance(parsed, dict) else {"result": "exec-error"}


def probe_connection(
    source: Pod, mode: str, host: str, port: int, extra: tuple[str, ...] = ()
) -> dict[str, Any]:
    return run_in_pod(
        source,
        PROBE_SRC,
        [mode, host, str(port), str(PROBE_TIMEOUT), *extra],
    )
