"""Fail-closed, secret-free diagnostics for the actual processor's failed startup.

Log requests have API byte/tail limits. Status lists have API item limits.
Post-capture size checks are validation, not a hard subprocess memory cap.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any
from urllib.parse import urlencode

from networkpolicy_runtime_kube import run_command

MESSAGES = {
    "Failed to load configuration": "configuration-failed",
    "Failed to parse RSA public key": "rsa-parse-failed",
    "RS256 token verification enabled": "rsa-loaded",
    "Failed to initialize JWKS verification": "jwks-failed",
    "Initial file-processor JWKS fetch failed; retaining static last-known-good key": "jwks-static-fallback",
    "Failed to initialize session revocation Redis": "redis-failed",
    "JWT security configuration is invalid": "jwt-config-failed",
    "Attached Temporal service token": "temporal-token-loaded",
    "Connected to Temporal": "temporal-connected",
    "Failed to connect to Temporal, retrying...": "temporal-retrying",
    "Failed to connect to Temporal": "temporal-connect-failed",
    "Failed to setup Temporal worker": "temporal-setup-failed",
    "Unable to start Temporal worker": "temporal-worker-failed",
    "Temporal Worker started": "temporal-worker-started",
    "Failed to initialize MinIO client": "minio-client-failed",
    "Failed to initialize file activities": "activities-failed",
    "Failed to connect to NATS (Legacy)": "nats-connect-failed",
    "Failed to get JetStream context": "nats-context-failed",
    "Failed to reconcile NATS consumer": "nats-consumer-failed",
    "Failed to subscribe to NATS queue": "nats-subscribe-failed",
    "SPIFFE initialization failed": "spiffe-failed",
    "Failed to setup gRPC server": "grpc-setup-failed",
    "Failed to setup GraphQL server": "graphql-setup-failed",
    "Failed to parse GraphQL schema": "graphql-schema-failed",
    "Failed to listen for gRPC": "grpc-listen-failed",
    "gRPC Server listening": "grpc-listening",
    "GraphQL & Metrics Server listening": "http-listening",
    "Failed to serve HTTP": "http-serve-failed",
}
FAILURES = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RecursionError,
    subprocess.SubprocessError,
)


def _request(*args: str) -> str:
    return run_command(["kubectl", "--request-timeout=5s", *args], timeout=10).stdout


def _document(path: str) -> dict[str, Any]:
    data = _request("get", "--raw", path)
    if len(data.encode("utf-8")) > 131072:
        raise ValueError("oversized API document")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("non-object API document")
    return value


def _items(path: str, selector: str) -> list[dict[str, Any]]:
    document = _document(
        path + "?" + urlencode({"labelSelector": selector, "limit": 8})
    )
    items = document["items"]
    if (
        document.get("metadata", {}).get("continue")
        or not isinstance(items, list)
        or len(items) > 8
    ):
        raise ValueError("incomplete bounded API list")
    return items


def _owned(resource: dict[str, Any], kind: str, uids: set[str]) -> bool:
    return any(
        owner.get("controller") is True
        and owner.get("kind") == kind
        and owner.get("uid") in uids
        for owner in resource["metadata"].get("ownerReferences", [])
    )


def _counter(value: Any, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid status counter")
    return value


def _exit(state: dict[str, Any]) -> int | None:
    value = state.get("terminated", {}).get("exitCode")
    return None if value is None else _counter(value, 255)


def _containers(pod: dict[str, Any]) -> list[dict[str, Any]]:
    rows = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(rows, list) or len(rows) > 2:
        raise ValueError("invalid container list")
    result = []
    seen = set()
    for row in rows:
        name = row["name"]
        if name not in {"file-processor", "probe"} or name in seen:
            raise ValueError("unexpected container")
        seen.add(name)
        state = row["state"]
        states = [key for key in ("waiting", "running", "terminated") if key in state]
        result.append(
            {
                "name": name,
                "state": states[0] if len(states) == 1 else "unknown",
                "ready": row.get("ready") is True,
                "restarts": _counter(row.get("restartCount", 0), 100000),
                "exit_code": _exit(state),
                "previous_exit_code": _exit(row.get("lastState", {})),
            }
        )
    return result


def _logs(namespace: str, name: str, previous: bool) -> dict[str, Any]:
    try:
        args = [
            "-n",
            namespace,
            "logs",
            name,
            "-c",
            "file-processor",
            "--tail=100",
            "--limit-bytes=16384",
        ]
        if previous:
            args.append("--previous=true")
        data = _request(*args)
        if len(data.encode("utf-8")) > 16384:
            raise ValueError("oversized bounded log response")
        events = set()
        for line in data.splitlines():
            try:
                row = json.loads(line)
                message = row.get("msg") if isinstance(row, dict) else None
                if isinstance(message, str) and message in MESSAGES:
                    events.add(MESSAGES[message])
            except (ValueError, TypeError):
                continue
        return {
            "status": "classified" if events else "unknown",
            "events": sorted(events),
        }
    except FAILURES:
        return {"status": "unavailable", "events": []}


def processor_startup_diagnostics() -> dict[str, Any]:
    """Inspect only actual Deployment-owned pods; no log data leaves the projection."""
    namespace = "probe-a"
    deployment_name = "probe-a-file-processor"
    try:
        deployment = _document(
            f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment_name}"
        )
        uid = deployment["metadata"]["uid"]
        if not isinstance(uid, str) or not uid:
            raise ValueError("missing deployment identity")
        selector = "app.kubernetes.io/instance=probe-a,app.kubernetes.io/component=file-processor"
        replicas = _items(f"/apis/apps/v1/namespaces/{namespace}/replicasets", selector)
        owned = {
            row["metadata"]["uid"]
            for row in replicas
            if _owned(row, "Deployment", {uid})
        }
        pods = _items(f"/api/v1/namespaces/{namespace}/pods", selector)
        pods = [pod for pod in pods if _owned(pod, "ReplicaSet", owned)]
        if not 1 <= len(pods) <= 2:
            raise ValueError("unexpected actual replica count")
        output = []
        for pod in sorted(pods, key=lambda item: item["metadata"]["name"]):
            name = pod["metadata"]["name"]
            if pod["metadata"].get("namespace") != namespace or not re.fullmatch(
                deployment_name + r"-[a-z0-9-]+", name
            ):
                raise ValueError("unexpected pod identity")
            output.append(
                {
                    "containers": _containers(pod),
                    "current": _logs(namespace, name, False),
                    "previous": _logs(namespace, name, True),
                }
            )
        return {"status": "collected", "replicas": output}
    except FAILURES:
        return {"status": "unavailable"}
