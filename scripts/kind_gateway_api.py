#!/usr/bin/env python3
"""Run-owned kind acceptance helpers for the Gateway API preview.

The tool creates a dedicated kind cluster from an explicit Kubernetes node
image, installs pinned Gateway API, Envoy Gateway, and cert-manager components,
and bootstraps a run-owned local CA. ``rollback`` removes only its own
GatewayClass. The explicit ``teardown`` command deletes the whole run-owned
cluster, including its Kubernetes resources and data, after verifying the local
record, context, ownership markers, and exact single-node cluster identity.
The teardown preserves the local run record and any separately managed
registry container/volume. The local CA is for kind acceptance only; its public
certificate can be exported for client-scoped trust without changing the host
trust store.

Examples (choose an exact kindest/node image within the documented 1.33–1.36
Kubernetes support range)::

    python scripts/kind_gateway_api.py create --node-image <exact-kindest-node-image-in-supported-range>
    python scripts/kind_gateway_api.py recover --run-id <printed-run-id>
    python scripts/kind_gateway_api.py status --run-id <printed-run-id>
    python scripts/kind_gateway_api.py preflight --run-id <printed-run-id>
    python scripts/kind_gateway_api.py prepare --run-id <printed-run-id>
    python scripts/kind_gateway_api.py smoke --run-id <printed-run-id>
    python scripts/kind_gateway_api.py ca-export --run-id <printed-run-id>
    python scripts/kind_gateway_api.py registry-start --run-id <printed-run-id> --image registry@sha256:<64-hex-digest>
    python scripts/kind_gateway_api.py registry-status --run-id <printed-run-id>
    python scripts/kind_gateway_api.py registry-stop --run-id <printed-run-id>
    python scripts/kind_gateway_api.py rollback --run-id <printed-run-id>
    python scripts/kind_gateway_api.py teardown --run-id <printed-run-id>

All external commands use argv lists with ``shell=False``. Read-only commands
never write cluster or local state. Mutating commands after ``create`` require
both the local run record and matching ConfigMap / control-plane node markers.
``recover`` is the narrow exception for an interrupted create: it verifies the
recorded context resolves to the expected cluster, the exact control-plane
node, and its Docker cluster label and image before adding only missing
markers. The Kubernetes Node need not repeat kind's Docker label, but a
conflicting value is rejected.
The local registry image must be supplied by immutable digest. Stopping the
registry preserves its owner-marked Docker volume and the cluster's data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

GATEWAY_API_BUNDLE_VERSION = "v1.6.1"
GATEWAY_API_CHANNEL = "standard"
ENVOY_GATEWAY_VERSION = "v1.9.2"
SUPPORTED_KUBERNETES_MINORS = frozenset({33, 34, 35, 36})

OWNER_KEY = "university-ecosystem.dev/kind-run-id"
OWNER_CONFIGMAP = "university-ecosystem-kind-gateway-api-owner"
OWNER_CONFIGMAP_NAMESPACE = "kube-system"
ENVOY_NAMESPACE = "envoy-gateway-system"
ENVOY_DEPLOYMENT = "envoy-gateway"
ENVOY_RELEASE = "eg"
GATEWAY_CLASS_CONTROLLER = "gateway.envoyproxy.io/gatewayclass-controller"
REGISTRY_HOST_PORT = 5001
REGISTRY_CONTAINER_PORT = 5000
REGISTRY_DATA_PATH = "/var/lib/registry"
KIND_CLUSTER_LABEL = "io.x-k8s.kind.cluster"
MANAGED_BY_KEY = "university-ecosystem.dev/managed-by"
MANAGED_BY_VALUE = "kind_gateway_api.py"

GATEWAY_API_CRDS = (
    "gatewayclasses.gateway.networking.k8s.io",
    "gateways.gateway.networking.k8s.io",
    "httproutes.gateway.networking.k8s.io",
)
ENVOY_GATEWAY_CRDS = (
    "clienttrafficpolicies.gateway.envoyproxy.io",
    "backendtrafficpolicies.gateway.envoyproxy.io",
)
CERT_MANAGER_CRD = "certificates.cert-manager.io"
CERT_MANAGER_VERSION = "v1.21.2"
CERT_MANAGER_HELM_CHART = "oci://quay.io/jetstack/charts/cert-manager"
CERT_MANAGER_NAMESPACE = "cert-manager"
CERT_MANAGER_RELEASE = "cert-manager"
CERT_MANAGER_DEPLOYMENTS = (
    "cert-manager",
    "cert-manager-cainjector",
    "cert-manager-webhook",
)
CERT_MANAGER_CRDS = (
    "certificates.cert-manager.io",
    "certificaterequests.cert-manager.io",
    "clusterissuers.cert-manager.io",
    "issuers.cert-manager.io",
    "orders.acme.cert-manager.io",
    "challenges.acme.cert-manager.io",
)

CRD_HELM_CHART = "oci://docker.io/envoyproxy/gateway-crds-helm"
CONTROLLER_HELM_CHART = "oci://docker.io/envoyproxy/gateway-helm"

_RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_REGISTRY_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_NODE_IMAGE_RE = re.compile(
    r"^(?:docker\.io/)?kindest/node:v1\.(?P<minor>33|34|35|36)\.(?P<patch>0|[1-9][0-9]*)(?:@sha256:[0-9a-f]{64})?$"
)


class KindGatewayApiError(RuntimeError):
    """An unsafe or failed kind Gateway API operation."""


@dataclass(frozen=True)
class RunState:
    run_id: str
    cluster: str
    context: str
    node_image: str
    phase: str
    crds_installed: bool = False
    controller_installed: bool = False
    gateway_class_created: bool = False

    @property
    def gateway_class(self) -> str:
        return f"eg-{self.run_id}"


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def default_state_dir() -> Path:
    """Return a cross-platform user-local directory for run ownership state."""
    return Path.home() / ".university-ecosystem" / "kind-gateway-api"


class KindGatewayApi:
    def __init__(
        self,
        *,
        runner: CommandRunner = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        state_dir: Path | None = None,
    ) -> None:
        self._runner = runner
        self._which = which
        self._state_dir = state_dir or default_state_dir()

    def _tool(self, name: str) -> str:
        path = self._which(name)
        if path is None:
            raise KindGatewayApiError(
                f"required executable '{name}' was not found on PATH"
            )
        return path

    def _run(
        self,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = self._runner(
            list(argv),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if check and result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            message = f"command failed ({result.returncode}): {list(argv)!r}"
            if details:
                message = f"{message}: {details}"
            raise KindGatewayApiError(message)
        return result

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        if not _RUN_ID_RE.fullmatch(run_id):
            raise KindGatewayApiError(
                "run ID must be exactly 12 lowercase hexadecimal characters"
            )
        return run_id

    @staticmethod
    def _cluster_name(run_id: str) -> str:
        return f"ue-gw-{KindGatewayApi._validate_run_id(run_id)}"

    def _state_path(self, run_id: str) -> Path:
        return self._state_dir / f"{self._cluster_name(run_id)}.json"

    def _load_state(self, run_id: str) -> RunState:
        path = self._state_path(run_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KindGatewayApiError(
                f"no local ownership record exists for run '{run_id}'"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise KindGatewayApiError(
                f"could not read local run state '{path}': {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise KindGatewayApiError(
                f"local run state '{path}' is incomplete or invalid"
            )
        if "schema_version" not in raw:
            raise KindGatewayApiError(
                f"local run state '{path}' is incomplete or invalid"
            )
        schema_version = raw.get("schema_version")
        if type(schema_version) is not int or schema_version != 1:
            raise KindGatewayApiError(
                f"local run state '{path}' has an unsupported schema version"
            )
        string_fields = ("run_id", "cluster", "context", "node_image", "phase")
        if any(type(raw.get(field)) is not str for field in string_fields):
            raise KindGatewayApiError(
                f"local run state '{path}' is incomplete or invalid"
            )
        boolean_fields = (
            "crds_installed",
            "controller_installed",
            "gateway_class_created",
        )
        for field in boolean_fields:
            if type(raw.get(field)) is not bool:
                raise KindGatewayApiError(
                    f"local run state '{path}' field '{field}' must be a JSON boolean"
                )
        if raw["phase"] not in {"creating", "owned"}:
            raise KindGatewayApiError(
                f"local run state '{path}' has an unsupported phase"
            )
        state = RunState(
            run_id=raw["run_id"],
            cluster=raw["cluster"],
            context=raw["context"],
            node_image=raw["node_image"],
            phase=raw["phase"],
            crds_installed=raw["crds_installed"],
            controller_installed=raw["controller_installed"],
            gateway_class_created=raw["gateway_class_created"],
        )
        if (
            state.run_id != run_id
            or state.cluster != self._cluster_name(run_id)
            or state.context != f"kind-{state.cluster}"
            or not _NODE_IMAGE_RE.fullmatch(state.node_image)
        ):
            raise KindGatewayApiError(
                f"local run state '{path}' does not match run '{run_id}'"
            )
        return state

    def _save_state(self, state: RunState) -> None:
        path = self._state_path(state.run_id)
        payload = {
            "schema_version": 1,
            "run_id": state.run_id,
            "cluster": state.cluster,
            "context": state.context,
            "node_image": state.node_image,
            "phase": state.phase,
            "crds_installed": state.crds_installed,
            "controller_installed": state.controller_installed,
            "gateway_class_created": state.gateway_class_created,
        }
        temp_name: str | None = None
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._state_dir,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
                temp_name = handle.name
            if os.name != "nt" and temp_name is not None:
                os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
        except OSError as exc:
            if temp_name is not None:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise KindGatewayApiError(
                f"could not write local run state '{path}': {exc}"
            ) from exc

    def _kind_clusters(self) -> set[str]:
        result = self._run([self._tool("kind"), "get", "clusters"])
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _kubectl(
        self,
        state: RunState,
        *args: str,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            [self._tool("kubectl"), "--context", state.context, *args],
            input_text=input_text,
            check=check,
        )

    @staticmethod
    def _json_or_none(
        result: subprocess.CompletedProcess[str], description: str
    ) -> dict[str, Any] | None:
        body = result.stdout.strip()
        if not body or body == "null":
            return None
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise KindGatewayApiError(f"{description} returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise KindGatewayApiError(
                f"{description} returned an unexpected JSON value"
            )
        return value

    def _get_json(self, state: RunState, *args: str) -> dict[str, Any] | None:
        result = self._kubectl(state, "get", *args, "-o", "json", "--ignore-not-found")
        return self._json_or_none(result, "kubectl get")

    def _contexts(self) -> set[str]:
        result = self._run(
            [self._tool("kubectl"), "config", "get-contexts", "--output=name"]
        )
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def _assert_cluster_creation_intent(self, state: RunState) -> None:
        """Guard the initial marker write after this invocation created the cluster."""
        if state.phase != "creating":
            raise KindGatewayApiError(
                "cluster ownership markers can only be established during create"
            )
        if state.cluster not in self._kind_clusters():
            raise KindGatewayApiError(f"kind cluster '{state.cluster}' does not exist")
        if state.context not in self._contexts():
            raise KindGatewayApiError(f"kind context '{state.context}' is unavailable")

    def _assert_context_identity(self, state: RunState) -> None:
        result = self._run(
            [
                self._tool("kubectl"),
                "config",
                "view",
                "--minify",
                "--context",
                state.context,
                "-o",
                "json",
            ]
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KindGatewayApiError(
                f"kind context '{state.context}' returned invalid kubeconfig JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise KindGatewayApiError(
                f"kind context '{state.context}' returned an unexpected kubeconfig value"
            )
        contexts = payload.get("contexts")
        clusters = payload.get("clusters")
        if (
            not isinstance(contexts, list)
            or len(contexts) != 1
            or not isinstance(contexts[0], dict)
            or contexts[0].get("name") != state.context
            or not isinstance(contexts[0].get("context"), dict)
            or contexts[0]["context"].get("cluster") != state.context
            or not isinstance(clusters, list)
            or len(clusters) != 1
            or not isinstance(clusters[0], dict)
            or clusters[0].get("name") != state.context
        ):
            raise KindGatewayApiError(
                f"kind context '{state.context}' does not resolve to its expected cluster"
            )

    def _owner_configmap(self, state: RunState) -> dict[str, Any] | None:
        return self._get_json(
            state,
            "configmap",
            OWNER_CONFIGMAP,
            "--namespace",
            OWNER_CONFIGMAP_NAMESPACE,
        )

    def _node(self, state: RunState) -> dict[str, Any] | None:
        return self._get_json(state, "node", f"{state.cluster}-control-plane")

    def _assert_owner_configmap(
        self, state: RunState, obj: dict[str, Any] | None
    ) -> None:
        if obj is None:
            raise KindGatewayApiError(
                "run ownership ConfigMap is missing; refusing cluster mutation"
            )
        metadata = obj.get("metadata")
        data = obj.get("data")
        if (
            not isinstance(metadata, dict)
            or not isinstance(data, dict)
            or metadata.get("name") != OWNER_CONFIGMAP
            or metadata.get("namespace") != OWNER_CONFIGMAP_NAMESPACE
            or data.get("run-id") != state.run_id
            or data.get("cluster") != state.cluster
            or data.get("node-image") != state.node_image
        ):
            raise KindGatewayApiError(
                "run ownership ConfigMap does not match the local run record"
            )

    def _assert_node_marker(self, state: RunState, obj: dict[str, Any] | None) -> None:
        if obj is None:
            raise KindGatewayApiError(
                "run control-plane node is missing; refusing cluster mutation"
            )
        metadata = obj.get("metadata")
        labels = metadata.get("labels") if isinstance(metadata, dict) else None
        if (
            not isinstance(metadata, dict)
            or not isinstance(labels, dict)
            or metadata.get("name") != f"{state.cluster}-control-plane"
            or (
                KIND_CLUSTER_LABEL in labels
                and labels[KIND_CLUSTER_LABEL] != state.cluster
            )
            or labels.get(OWNER_KEY) != state.run_id
        ):
            raise KindGatewayApiError(
                "control-plane node ownership marker does not match this run"
            )

    def _assert_owned(self, state: RunState) -> None:
        if state.phase != "owned":
            raise KindGatewayApiError(
                f"run '{state.run_id}' is not fully owned (state phase: {state.phase}); refusing mutation"
            )
        if state.cluster not in self._kind_clusters():
            raise KindGatewayApiError(
                f"owned kind cluster '{state.cluster}' is unavailable"
            )
        if state.context not in self._contexts():
            raise KindGatewayApiError(
                f"owned kind context '{state.context}' is unavailable"
            )
        self._assert_context_identity(state)
        self._assert_owner_configmap(state, self._owner_configmap(state))
        self._assert_node_marker(state, self._node(state))
        self._verify_kind_node_container(state, f"{state.cluster}-control-plane")

    def _assert_recoverable_creation_identity(
        self, state: RunState
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Verify an interrupted create before repairing either ownership marker."""
        self._assert_cluster_creation_intent(state)
        self._assert_context_identity(state)

        node = self._node(state)
        if node is None:
            raise KindGatewayApiError(
                "kind control-plane node was not found; refusing create recovery"
            )
        metadata = node.get("metadata")
        labels = metadata.get("labels") if isinstance(metadata, dict) else None
        expected_node = f"{state.cluster}-control-plane"
        if (
            not isinstance(metadata, dict)
            or not isinstance(labels, dict)
            or metadata.get("name") != expected_node
            or (
                KIND_CLUSTER_LABEL in labels
                and labels[KIND_CLUSTER_LABEL] != state.cluster
            )
        ):
            raise KindGatewayApiError(
                "kind control-plane node identity does not match the recorded cluster"
            )
        node_owner = labels.get(OWNER_KEY)
        if node_owner not in (None, state.run_id):
            raise KindGatewayApiError(
                "control-plane node has a different run ownership marker"
            )

        owner_configmap = self._owner_configmap(state)
        if owner_configmap is not None:
            self._assert_owner_configmap(state, owner_configmap)

        self._verify_kind_node_container(state, expected_node)
        return owner_configmap, node

    @staticmethod
    def _registry_name(state: RunState) -> str:
        return f"ue-gw-registry-{state.run_id}"

    @staticmethod
    def _registry_volume_name(state: RunState) -> str:
        return f"ue-gw-registry-data-{state.run_id}"

    @staticmethod
    def _validate_registry_image(image: str) -> str:
        if not _REGISTRY_IMAGE_RE.fullmatch(image):
            raise KindGatewayApiError("registry image must use an exact sha256 digest")
        return image

    @staticmethod
    def _validate_registry_port(port: int) -> int:
        if isinstance(port, bool) or not 1024 <= port <= 65535:
            raise KindGatewayApiError(
                "registry host port must be between 1024 and 65535"
            )
        return port

    def _docker_inspect(self, resource_type: str, name: str) -> dict[str, Any] | None:
        result = self._run(
            [self._tool("docker"), resource_type, "inspect", name], check=False
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            lowered = details.lower()
            if any(
                missing in lowered
                for missing in ("no such object", "no such container", "no such volume")
            ):
                return None
            raise KindGatewayApiError(
                f"docker {resource_type} inspect failed: {details or result.returncode}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise KindGatewayApiError(
                f"docker {resource_type} inspect returned invalid JSON"
            ) from exc
        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], dict)
        ):
            raise KindGatewayApiError(
                f"docker {resource_type} inspect returned an unexpected JSON value"
            )
        return payload[0]

    def _verify_registry_volume(self, state: RunState, volume: dict[str, Any]) -> None:
        labels = volume.get("Labels") or {}
        if (
            volume.get("Name") != self._registry_volume_name(state)
            or labels.get(OWNER_KEY) != state.run_id
            or labels.get(MANAGED_BY_KEY) != MANAGED_BY_VALUE
            or labels.get("university-ecosystem.dev/kind-cluster") != state.cluster
        ):
            raise KindGatewayApiError(
                "local registry volume is unowned or changed; refusing to use it"
            )

    def _verify_registry_container(
        self,
        state: RunState,
        container: dict[str, Any],
        *,
        image: str | None = None,
        port: int | None = None,
    ) -> None:
        name = self._registry_name(state)
        labels = container.get("Config", {}).get("Labels") or {}
        networks = container.get("NetworkSettings", {}).get("Networks") or {}
        mounts = container.get("Mounts") or []
        bindings = (container.get("HostConfig", {}).get("PortBindings") or {}).get(
            f"{REGISTRY_CONTAINER_PORT}/tcp"
        ) or []
        binding = (
            bindings[0] if len(bindings) == 1 and isinstance(bindings[0], dict) else {}
        )
        expected_port = str(port) if port is not None else None
        actual_host = binding.get("HostIp")
        actual_port = binding.get("HostPort")
        valid_host_port = (
            isinstance(actual_port, str)
            and actual_port.isascii()
            and actual_port.isdecimal()
            and 1024 <= int(actual_port) <= 65535
        )
        volume_mounted = any(
            item.get("Type") == "volume"
            and item.get("Name") == self._registry_volume_name(state)
            and item.get("Destination") == REGISTRY_DATA_PATH
            for item in mounts
        )
        if (
            container.get("Name", "").lstrip("/") != name
            or labels.get(OWNER_KEY) != state.run_id
            or labels.get(MANAGED_BY_KEY) != MANAGED_BY_VALUE
            or labels.get("university-ecosystem.dev/kind-cluster") != state.cluster
            or (image is not None and container.get("Config", {}).get("Image") != image)
            or len(bindings) != 1
            or actual_host != "127.0.0.1"
            or not valid_host_port
            or (expected_port is not None and actual_port != expected_port)
            or not volume_mounted
            or "kind" not in networks
            or name not in networks["kind"].get("Aliases", [])
        ):
            raise KindGatewayApiError(
                "local registry container is unowned or changed; refusing to use it"
            )

    def _verify_kind_node_container(
        self, state: RunState, node_name: str
    ) -> dict[str, Any]:
        node_container = self._docker_inspect("container", node_name)
        if node_container is None:
            raise KindGatewayApiError(
                f"kind node container '{node_name}' is unavailable"
            )
        config = node_container.get("Config")
        if not isinstance(config, dict):
            raise KindGatewayApiError(
                f"kind node container '{node_name}' does not belong to this cluster"
            )
        labels = config.get("Labels")
        name = node_container.get("Name")
        if (
            not isinstance(name, str)
            or name.lstrip("/") != node_name
            or not isinstance(labels, dict)
            or labels.get(KIND_CLUSTER_LABEL) != state.cluster
        ):
            raise KindGatewayApiError(
                f"kind node container '{node_name}' does not belong to this cluster"
            )
        image = config.get("Image")
        if image != state.node_image:
            raise KindGatewayApiError(
                "kind control-plane node image does not match the recorded run"
            )
        return node_container

    def _kind_node_container_names(self, state: RunState) -> list[str]:
        result = self._run(
            [
                self._tool("docker"),
                "ps",
                "--all",
                "--filter",
                f"label={KIND_CLUSTER_LABEL}={state.cluster}",
                "--format",
                "{{.Names}}",
            ]
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _assert_teardown_identity(self, state: RunState) -> str:
        node_name = f"{state.cluster}-control-plane"
        initial_container = self._verify_kind_node_container(state, node_name)
        initial_container_id = initial_container.get("Id")
        if not isinstance(initial_container_id, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", initial_container_id
        ):
            raise KindGatewayApiError(
                "kind node container has an invalid Docker identity"
            )

        self._assert_owned(state)
        self._assert_context_identity(state)

        result = self._kubectl(state, "get", "nodes", "-o", "json")
        try:
            payload = json.loads(result.stdout)
            nodes = payload["items"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise KindGatewayApiError(
                "could not verify the run-owned kind node inventory"
            ) from exc
        if (
            not isinstance(nodes, list)
            or len(nodes) != 1
            or not isinstance(nodes[0], dict)
        ):
            raise KindGatewayApiError("teardown requires exactly one run-owned node")
        self._assert_node_marker(state, nodes[0])

        if self._kind_node_container_names(state) != [node_name]:
            raise KindGatewayApiError(
                "Docker node-container inventory differs from this run's cluster"
            )
        container = self._verify_kind_node_container(state, node_name)
        config = container.get("Config")
        docker_state = container.get("State")
        container_id = container.get("Id")
        if not isinstance(container_id, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", container_id
        ):
            raise KindGatewayApiError(
                "kind node container has an invalid Docker identity"
            )
        if container_id.casefold() != initial_container_id.casefold():
            raise KindGatewayApiError(
                "kind node container identity changed before teardown"
            )
        if (
            not isinstance(config, dict)
            or config.get("Image") != state.node_image
            or not isinstance(docker_state, dict)
            or docker_state.get("Running") is not True
        ):
            raise KindGatewayApiError(
                "kind node container image or running state differs from the run record"
            )
        return container_id.casefold()

    def teardown(self, run_id: str) -> bool:
        """Delete only a fully verified single-node cluster created by this run."""
        state = self._load_state(self._validate_run_id(run_id))
        if state.phase != "owned":
            raise KindGatewayApiError(
                "teardown requires a fully owned cluster; refusing mutation"
            )
        if state.cluster not in self._kind_clusters():
            return False

        verified_container_id = self._assert_teardown_identity(state)
        if state.cluster not in self._kind_clusters():
            return False
        final_container_id = self._assert_teardown_identity(state)
        if final_container_id != verified_container_id:
            raise KindGatewayApiError(
                "kind node container identity changed before teardown"
            )
        self._run(
            [
                self._tool("kind"),
                "delete",
                "cluster",
                "--name",
                state.cluster,
            ]
        )
        if state.cluster in self._kind_clusters():
            raise KindGatewayApiError("kind cluster remains after teardown")
        if self._kind_node_container_names(state):
            raise KindGatewayApiError("kind node containers remain after teardown")
        return True

    @staticmethod
    def _registry_hosts_toml(state: RunState) -> str:
        return (
            f"# {OWNER_KEY}={state.run_id}\n"
            f'[host."http://{KindGatewayApi._registry_name(state)}:{REGISTRY_CONTAINER_PORT}"]\n'
            '  capabilities = ["pull", "resolve"]\n'
        )

    def _configure_registry_node(
        self, state: RunState, node_name: str, port: int
    ) -> None:
        self._assert_owned(state)
        self._verify_kind_node_container(state, node_name)
        config_dir = f"/etc/containerd/certs.d/localhost:{port}"
        config_path = f"{config_dir}/hosts.toml"
        expected = self._registry_hosts_toml(state)
        current = self._run(
            [self._tool("docker"), "exec", node_name, "cat", config_path],
            check=False,
        )
        if current.returncode == 0:
            if current.stdout != expected:
                raise KindGatewayApiError(
                    f"containerd registry config '{config_path}' is unowned or changed"
                )
            return
        details = (current.stderr or current.stdout or "").strip()
        if "no such file or directory" not in details.lower():
            raise KindGatewayApiError(
                f"could not read containerd registry config '{config_path}': {details or current.returncode}"
            )
        self._assert_owned(state)
        self._verify_kind_node_container(state, node_name)
        self._run([self._tool("docker"), "exec", node_name, "mkdir", "-p", config_dir])
        self._assert_owned(state)
        self._verify_kind_node_container(state, node_name)
        self._run(
            [self._tool("docker"), "exec", "-i", node_name, "tee", config_path],
            input_text=expected,
        )

    def registry_start(
        self, run_id: str, *, image: str, port: int = REGISTRY_HOST_PORT
    ) -> dict[str, Any]:
        state = self._load_state(self._validate_run_id(run_id))
        image = self._validate_registry_image(image)
        port = self._validate_registry_port(port)
        self._assert_owned(state)
        volume_name = self._registry_volume_name(state)
        volume = self._docker_inspect("volume", volume_name)
        if volume is None:
            self._assert_owned(state)
            self._run(
                [
                    self._tool("docker"),
                    "volume",
                    "create",
                    "--label",
                    f"{OWNER_KEY}={state.run_id}",
                    "--label",
                    f"{MANAGED_BY_KEY}={MANAGED_BY_VALUE}",
                    "--label",
                    f"university-ecosystem.dev/kind-cluster={state.cluster}",
                    volume_name,
                ]
            )
            volume = self._docker_inspect("volume", volume_name)
            if volume is None:
                raise KindGatewayApiError(
                    "created registry volume could not be verified"
                )
        self._verify_registry_volume(state, volume)

        registry_name = self._registry_name(state)
        container = self._docker_inspect("container", registry_name)
        if container is None:
            self._assert_owned(state)
            self._run(
                [
                    self._tool("docker"),
                    "run",
                    "--detach",
                    "--name",
                    registry_name,
                    "--restart=no",
                    "--label",
                    f"{OWNER_KEY}={state.run_id}",
                    "--label",
                    f"{MANAGED_BY_KEY}={MANAGED_BY_VALUE}",
                    "--label",
                    f"university-ecosystem.dev/kind-cluster={state.cluster}",
                    "--network",
                    "kind",
                    "--network-alias",
                    registry_name,
                    "--publish",
                    f"127.0.0.1:{port}:{REGISTRY_CONTAINER_PORT}",
                    "--mount",
                    f"type=volume,source={volume_name},target={REGISTRY_DATA_PATH}",
                    image,
                ]
            )
            container = self._docker_inspect("container", registry_name)
            if container is None:
                raise KindGatewayApiError(
                    "created local registry container could not be verified"
                )
        self._verify_registry_container(state, container, image=image, port=port)
        if not container.get("State", {}).get("Running", False):
            self._assert_owned(state)
            self._verify_registry_container(state, container, image=image, port=port)
            self._run([self._tool("docker"), "container", "start", registry_name])
            container = self._docker_inspect("container", registry_name)
            if container is None:
                raise KindGatewayApiError(
                    "started local registry container could not be verified"
                )
            self._verify_registry_container(state, container, image=image, port=port)
        if not container.get("State", {}).get("Running", False):
            raise KindGatewayApiError("local registry container did not remain running")
        node_name = f"{state.cluster}-control-plane"
        self._configure_registry_node(state, node_name, port)
        return {
            "run_id": state.run_id,
            "registry": f"localhost:{port}",
            "in_cluster_endpoint": f"{registry_name}:{REGISTRY_CONTAINER_PORT}",
            "image": image,
            "running": True,
            "data_volume": volume_name,
        }

    def registry_status(self, run_id: str) -> dict[str, Any]:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        volume = self._docker_inspect("volume", self._registry_volume_name(state))
        container = self._docker_inspect("container", self._registry_name(state))
        if volume is None and container is None:
            return {
                "run_id": state.run_id,
                "configured": False,
                "running": False,
            }
        if volume is None:
            raise KindGatewayApiError(
                "local registry container has no run-owned data volume"
            )
        self._verify_registry_volume(state, volume)
        if container is None:
            return {
                "run_id": state.run_id,
                "configured": True,
                "container_exists": False,
                "running": False,
                "data_volume": self._registry_volume_name(state),
            }
        self._verify_registry_container(state, container)
        bindings = container.get("HostConfig", {}).get("PortBindings", {})
        host_bindings = bindings.get(f"{REGISTRY_CONTAINER_PORT}/tcp", [])
        host_port = next(
            item["HostPort"]
            for item in host_bindings
            if item.get("HostIp") == "127.0.0.1"
        )
        return {
            "run_id": state.run_id,
            "configured": True,
            "container_exists": True,
            "running": bool(container.get("State", {}).get("Running", False)),
            "image": container.get("Config", {}).get("Image"),
            "registry": f"localhost:{host_port}",
            "data_volume": self._registry_volume_name(state),
        }

    def registry_stop(self, run_id: str) -> bool:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        volume = self._docker_inspect("volume", self._registry_volume_name(state))
        container = self._docker_inspect("container", self._registry_name(state))
        if volume is None and container is None:
            return False
        if volume is None:
            raise KindGatewayApiError(
                "local registry container has no run-owned data volume"
            )
        self._verify_registry_volume(state, volume)
        if container is None:
            return False
        self._verify_registry_container(state, container)
        if not container.get("State", {}).get("Running", False):
            return False
        self._assert_owned(state)
        self._verify_registry_container(state, container)
        self._run(
            [
                self._tool("docker"),
                "container",
                "stop",
                "--time",
                "10",
                self._registry_name(state),
            ]
        )
        return True

    def create(self, *, node_image: str, run_id: str | None = None) -> RunState:
        match = _NODE_IMAGE_RE.fullmatch(node_image)
        if match is None:
            raise KindGatewayApiError(
                "node image must be an exact kindest/node:v1.33.x through v1.36.x version, optionally pinned by a lowercase sha256 digest"
            )
        selected_run_id = self._validate_run_id(run_id or uuid.uuid4().hex[:12])
        state = RunState(
            run_id=selected_run_id,
            cluster=self._cluster_name(selected_run_id),
            context=f"kind-{self._cluster_name(selected_run_id)}",
            node_image=node_image,
            phase="creating",
        )
        state_path = self._state_path(state.run_id)
        if state_path.exists():
            existing = self._load_state(state.run_id)
            if existing.phase == "owned":
                if existing.node_image != node_image:
                    raise KindGatewayApiError(
                        "run ID already belongs to a cluster created with a different node image"
                    )
                self._assert_owned(existing)
                return existing
            if existing.node_image != node_image:
                raise KindGatewayApiError(
                    "run ID already belongs to a cluster creation intent with a different node image"
                )
            return self.recover(existing.run_id)
        if state.cluster in self._kind_clusters():
            raise KindGatewayApiError(
                f"kind cluster '{state.cluster}' already exists without this run's local ownership record"
            )

        # The run-specific cluster name was confirmed absent immediately above.
        # This is the only cluster mutation allowed before remote run markers exist.
        self._save_state(state)
        self._run(
            [
                self._tool("kind"),
                "create",
                "cluster",
                "--config=-",
                "--name",
                state.cluster,
                "--image",
                node_image,
                "--wait",
                "5m",
            ],
            input_text=(
                "kind: Cluster\n"
                "apiVersion: kind.x-k8s.io/v1alpha4\n"
                "containerdConfigPatches:\n"
                "- |-\n"
                '  [plugins."io.containerd.grpc.v1.cri".registry]\n'
                '    config_path = "/etc/containerd/certs.d"\n'
            ),
        )
        self._establish_owner_markers(state)
        owned_state = RunState(**{**state.__dict__, "phase": "owned"})
        self._save_state(owned_state)
        return owned_state

    def _establish_owner_markers(self, state: RunState) -> None:
        owner_configmap, node = self._assert_recoverable_creation_identity(state)
        if owner_configmap is None:
            self._assert_recoverable_creation_identity(state)
            self._run(
                [
                    self._tool("kubectl"),
                    "--context",
                    state.context,
                    "create",
                    "configmap",
                    OWNER_CONFIGMAP,
                    "--namespace",
                    OWNER_CONFIGMAP_NAMESPACE,
                    f"--from-literal=run-id={state.run_id}",
                    f"--from-literal=cluster={state.cluster}",
                    f"--from-literal=node-image={state.node_image}",
                ]
            )
            owner_configmap = self._owner_configmap(state)
        self._assert_owner_configmap(state, owner_configmap)

        labels = node.get("metadata", {}).get("labels", {})
        existing_marker = labels.get(OWNER_KEY)
        if existing_marker is None:
            self._assert_recoverable_creation_identity(state)
            self._assert_owner_configmap(state, self._owner_configmap(state))
            self._run(
                [
                    self._tool("kubectl"),
                    "--context",
                    state.context,
                    "label",
                    "node",
                    f"{state.cluster}-control-plane",
                    f"{OWNER_KEY}={state.run_id}",
                ]
            )
        self._assert_node_marker(state, self._node(state))

    def recover(self, run_id: str) -> RunState:
        """Finish ownership markers for this run's interrupted cluster create."""
        state = self._load_state(self._validate_run_id(run_id))
        if state.phase == "owned":
            self._assert_owned(state)
            return state
        if state.phase != "creating":
            raise KindGatewayApiError(
                f"run '{state.run_id}' cannot be recovered from phase '{state.phase}'"
            )

        self._establish_owner_markers(state)
        owned_state = RunState(**{**state.__dict__, "phase": "owned"})
        self._save_state(owned_state)
        return owned_state

    def status(self, run_id: str) -> dict[str, Any]:
        self._validate_run_id(run_id)
        state_path = self._state_path(run_id)
        if not state_path.exists():
            return {
                "run_id": run_id,
                "cluster": self._cluster_name(run_id),
                "exists": self._cluster_name(run_id) in self._kind_clusters(),
                "owned": False,
                "reason": "no local run ownership record",
            }
        state = self._load_state(run_id)
        clusters = self._kind_clusters()
        if state.cluster not in clusters:
            return {
                "run_id": run_id,
                "cluster": state.cluster,
                "exists": False,
                "owned": False,
            }
        try:
            self._assert_owned(state)
        except KindGatewayApiError as exc:
            return {
                "run_id": run_id,
                "cluster": state.cluster,
                "exists": True,
                "owned": False,
                "reason": str(exc),
            }
        return {
            "run_id": run_id,
            "cluster": state.cluster,
            "context": state.context,
            "node_image": state.node_image,
            "exists": True,
            "owned": True,
            "phase": state.phase,
            "crds_installed": state.crds_installed,
            "controller_installed": state.controller_installed,
            "gateway_class": state.gateway_class,
            "gateway_class_created": state.gateway_class_created,
        }

    def _server_version(self, state: RunState) -> tuple[int, int]:
        result = self._kubectl(state, "version", "-o", "json")
        try:
            payload = json.loads(result.stdout)
            version = payload["serverVersion"]
            major = int(str(version["major"]).rstrip("+"))
            minor_text = str(version["minor"]).rstrip("+")
            minor = int(minor_text)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise KindGatewayApiError(
                "could not parse Kubernetes server version"
            ) from exc
        return major, minor

    @staticmethod
    def _served_versions(crd: dict[str, Any]) -> set[str]:
        versions = crd.get("spec", {}).get("versions", [])
        return {
            str(item.get("name"))
            for item in versions
            if isinstance(item, dict) and item.get("served") is True
        }

    def _require_crd(
        self,
        state: RunState,
        name: str,
        version: str | None = None,
        *,
        require_gateway_bundle: bool = False,
    ) -> dict[str, Any]:
        crd = self._get_json(state, "crd", name)
        if crd is None:
            raise KindGatewayApiError(f"required CRD '{name}' is unavailable")
        if version is not None and version not in self._served_versions(crd):
            raise KindGatewayApiError(
                f"CRD '{name}' does not serve required version '{version}'"
            )
        if require_gateway_bundle:
            annotations = crd.get("metadata", {}).get("annotations", {})
            actual = (
                annotations.get("gateway.networking.k8s.io/bundle-version"),
                annotations.get("gateway.networking.k8s.io/channel"),
            )
            if actual != (GATEWAY_API_BUNDLE_VERSION, GATEWAY_API_CHANNEL):
                raise KindGatewayApiError(
                    f"Gateway API CRD '{name}' must use {GATEWAY_API_BUNDLE_VERSION} on the Standard channel"
                )
        return crd

    def _preflight(
        self, state: RunState, *, include_cert_manager: bool
    ) -> dict[str, Any]:
        self._assert_owned(state)
        major, minor = self._server_version(state)
        if major != 1 or minor not in SUPPORTED_KUBERNETES_MINORS:
            raise KindGatewayApiError(
                "Kubernetes server version must be within the documented 1.33–1.36 range"
            )
        for name in GATEWAY_API_CRDS:
            self._require_crd(state, name, "v1", require_gateway_bundle=True)
        for name in ENVOY_GATEWAY_CRDS:
            self._require_crd(state, name, "v1alpha1")
        if include_cert_manager:
            self._require_crd(state, CERT_MANAGER_CRD, "v1")
        deployment = self._get_json(
            state,
            "deployment",
            ENVOY_DEPLOYMENT,
            "--namespace",
            ENVOY_NAMESPACE,
        )
        if deployment is None:
            raise KindGatewayApiError(
                f"Envoy Gateway deployment is unavailable in {ENVOY_NAMESPACE}"
            )
        version = (
            deployment.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/version")
        )
        if version != ENVOY_GATEWAY_VERSION:
            raise KindGatewayApiError(
                f"Envoy Gateway version must be {ENVOY_GATEWAY_VERSION}"
            )
        return {
            "kubernetes": f"{major}.{minor}",
            "gateway_api_bundle": GATEWAY_API_BUNDLE_VERSION,
            "gateway_api_channel": GATEWAY_API_CHANNEL,
            "envoy_gateway": ENVOY_GATEWAY_VERSION,
            "cert_manager_crd_checked": include_cert_manager,
        }

    def preflight(self, run_id: str) -> dict[str, Any]:
        state = self._load_state(self._validate_run_id(run_id))
        return self._preflight(state, include_cert_manager=True)

    def _gateway_crds(self, state: RunState) -> list[dict[str, Any]]:
        result = self._kubectl(state, "get", "crds", "-o", "json")
        try:
            payload = json.loads(result.stdout)
            items = payload["items"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise KindGatewayApiError("could not list cluster CRDs") from exc
        if not isinstance(items, list):
            raise KindGatewayApiError("kubectl CRD list did not contain an item list")
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _is_gateway_crd(crd: dict[str, Any]) -> bool:
        group = crd.get("spec", {}).get("group")
        return group in {"gateway.networking.k8s.io", "gateway.envoyproxy.io"}

    def _verify_owned_gateway_crds(
        self, state: RunState, crds: list[dict[str, Any]]
    ) -> None:
        for crd in crds:
            if not self._is_gateway_crd(crd):
                continue
            annotations = crd.get("metadata", {}).get("annotations", {})
            owner = annotations.get(OWNER_KEY)
            if owner != state.run_id:
                name = crd.get("metadata", {}).get("name", "<unnamed>")
                raise KindGatewayApiError(
                    f"Gateway API CRD '{name}' is unowned; refusing to apply over it"
                )

    def _install_gateway_crds(self, state: RunState) -> RunState:
        before = self._gateway_crds(state)
        self._verify_owned_gateway_crds(state, before)
        if state.crds_installed:
            existing_names = {
                crd.get("metadata", {}).get("name")
                for crd in before
                if self._is_gateway_crd(crd)
            }
            missing = set((*GATEWAY_API_CRDS, *ENVOY_GATEWAY_CRDS)) - existing_names
            if missing:
                raise KindGatewayApiError(
                    "recorded run-owned Gateway API setup is incomplete; refusing to reinstall CRDs"
                )
            for name in GATEWAY_API_CRDS:
                self._require_crd(state, name, "v1", require_gateway_bundle=True)
            for name in ENVOY_GATEWAY_CRDS:
                self._require_crd(state, name, "v1alpha1")
            return state
        rendered = self._run(
            [
                self._tool("helm"),
                "template",
                "eg-crds",
                CRD_HELM_CHART,
                "--version",
                ENVOY_GATEWAY_VERSION,
                "--set",
                "crds.gatewayAPI.enabled=true",
                "--set",
                f"crds.gatewayAPI.channel={GATEWAY_API_CHANNEL}",
                "--set",
                "crds.envoyGateway.enabled=true",
            ]
        )
        self._assert_owned(state)
        self._run(
            [
                self._tool("kubectl"),
                "--context",
                state.context,
                "apply",
                "--server-side",
                "-f",
                "-",
            ],
            input_text=rendered.stdout,
        )
        current = self._gateway_crds(state)
        names = {
            crd.get("metadata", {}).get("name")
            for crd in current
            if self._is_gateway_crd(crd)
        }
        missing = set((*GATEWAY_API_CRDS, *ENVOY_GATEWAY_CRDS)) - names
        if missing:
            raise KindGatewayApiError(
                f"Envoy Gateway CRD install did not create: {', '.join(sorted(missing))}"
            )
        for crd in current:
            if not self._is_gateway_crd(crd):
                continue
            name = crd.get("metadata", {}).get("name")
            owner = crd.get("metadata", {}).get("annotations", {}).get(OWNER_KEY)
            if owner == state.run_id:
                continue
            if owner is not None:
                raise KindGatewayApiError(
                    f"CRD '{name}' has a different run ownership marker"
                )
            # A CRD absent before this command was created by the pinned chart;
            # any pre-existing CRD was required to carry this run's marker.
            self._assert_owned(state)
            self._run(
                [
                    self._tool("kubectl"),
                    "--context",
                    state.context,
                    "annotate",
                    "crd",
                    str(name),
                    f"{OWNER_KEY}={state.run_id}",
                    "--overwrite=false",
                ]
            )
        marked = self._gateway_crds(state)
        self._verify_owned_gateway_crds(state, marked)
        for name in GATEWAY_API_CRDS:
            self._require_crd(state, name, "v1", require_gateway_bundle=True)
        for name in ENVOY_GATEWAY_CRDS:
            self._require_crd(state, name, "v1alpha1")
        updated = RunState(**{**state.__dict__, "crds_installed": True})
        self._save_state(updated)
        return updated

    @staticmethod
    def _is_cert_manager_crd(crd: dict[str, Any]) -> bool:
        spec = crd.get("spec")
        return isinstance(spec, dict) and spec.get("group") in {
            "cert-manager.io",
            "acme.cert-manager.io",
        }

    def _cert_manager_crds(self, state: RunState) -> dict[str, dict[str, Any]]:
        return {
            str(metadata["name"]): crd
            for crd in self._gateway_crds(state)
            if self._is_cert_manager_crd(crd)
            and isinstance(metadata := crd.get("metadata"), dict)
            and isinstance(metadata.get("name"), str)
        }

    @staticmethod
    def _cert_manager_names(state: RunState) -> dict[str, str]:
        return {
            "bootstrap_issuer": f"ue-gw-selfsigned-{state.run_id}",
            "root_certificate": f"ue-gw-root-ca-{state.run_id}",
            "ca_secret": f"ue-gw-root-ca-{state.run_id}",
            "cluster_issuer": f"ue-gw-ca-{state.run_id}",
        }

    @staticmethod
    def _has_run_owner(resource: dict[str, Any] | None, run_id: str) -> bool:
        if resource is None:
            return False
        metadata = resource.get("metadata")
        annotations = (
            metadata.get("annotations") if isinstance(metadata, dict) else None
        )
        return (
            isinstance(annotations, dict)
            and annotations.get(OWNER_KEY) == run_id
            and annotations.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE
        )

    @staticmethod
    def _has_helm_identity(resource: dict[str, Any] | None) -> bool:
        if resource is None:
            return False
        metadata = resource.get("metadata")
        if not isinstance(metadata, dict):
            return False
        labels = metadata.get("labels")
        annotations = metadata.get("annotations")
        return (
            isinstance(labels, dict)
            and labels.get("app.kubernetes.io/managed-by") == "Helm"
            and labels.get("app.kubernetes.io/instance") == CERT_MANAGER_RELEASE
            and isinstance(annotations, dict)
            and annotations.get("meta.helm.sh/release-name") == CERT_MANAGER_RELEASE
            and annotations.get("meta.helm.sh/release-namespace")
            == CERT_MANAGER_NAMESPACE
        )

    def _mark_cert_manager_owned(
        self,
        state: RunState,
        kind: str,
        name: str,
        resource: dict[str, Any],
        *,
        namespace: str | None = None,
    ) -> None:
        if not self._has_helm_identity(resource):
            raise KindGatewayApiError(
                f"cert-manager {kind} '{name}' lacks the pinned Helm release identity"
            )
        metadata = resource.get("metadata", {})
        annotations = metadata.get("annotations", {})
        owner = annotations.get(OWNER_KEY)
        manager = annotations.get(MANAGED_BY_KEY)
        if owner == state.run_id and manager == MANAGED_BY_VALUE:
            return
        if owner is not None or manager is not None:
            raise KindGatewayApiError(
                f"cert-manager {kind} '{name}' has conflicting run ownership"
            )
        self._assert_owned(state)
        self._kubectl(
            state,
            "annotate",
            kind,
            name,
            f"{OWNER_KEY}={state.run_id}",
            f"{MANAGED_BY_KEY}={MANAGED_BY_VALUE}",
            "--overwrite=false",
            *(["--namespace", namespace] if namespace else []),
        )
        verified = self._get_json(
            state, kind, name, *(["--namespace", namespace] if namespace else [])
        )
        if not self._has_run_owner(verified, state.run_id):
            raise KindGatewayApiError(
                f"cert-manager {kind} '{name}' ownership could not be verified"
            )

    def _verify_cert_manager_installation(self, state: RunState) -> None:
        namespace = self._get_json(state, "namespace", CERT_MANAGER_NAMESPACE)
        if (
            namespace is None
            or namespace.get("metadata", {}).get("name") != CERT_MANAGER_NAMESPACE
        ):
            raise KindGatewayApiError("cert-manager namespace is unavailable")
        if not self._has_run_owner(namespace, state.run_id):
            raise KindGatewayApiError("cert-manager namespace is unowned by this run")

        for name in CERT_MANAGER_DEPLOYMENTS:
            deployment = self._get_json(
                state, "deployment", name, "--namespace", CERT_MANAGER_NAMESPACE
            )
            metadata = deployment.get("metadata", {}) if deployment else {}
            labels = metadata.get("labels", {}) if isinstance(metadata, dict) else {}
            status = deployment.get("status", {}) if deployment else {}
            replicas = (
                status.get("availableReplicas", 0) if isinstance(status, dict) else 0
            )
            if (
                not self._has_run_owner(deployment, state.run_id)
                or not self._has_helm_identity(deployment)
                or not isinstance(labels, dict)
                or labels.get("app.kubernetes.io/version") != CERT_MANAGER_VERSION
                or not isinstance(replicas, int)
                or isinstance(replicas, bool)
                or replicas < 1
            ):
                raise KindGatewayApiError(
                    f"cert-manager deployment '{name}' is unowned, unready, or not {CERT_MANAGER_VERSION}"
                )

        crds = self._cert_manager_crds(state)
        if set(crds) != set(CERT_MANAGER_CRDS):
            raise KindGatewayApiError(
                "cert-manager CRD inventory is incomplete or unexpected"
            )
        for name, crd in crds.items():
            self._require_crd(state, name, "v1")
            if not self._has_run_owner(
                crd, state.run_id
            ) or not self._has_helm_identity(crd):
                raise KindGatewayApiError(
                    f"cert-manager CRD '{name}' is unowned or not part of the pinned Helm release"
                )

    def _install_cert_manager(self, state: RunState) -> None:
        namespace = self._get_json(state, "namespace", CERT_MANAGER_NAMESPACE)
        deployments = (
            {
                name: self._get_json(
                    state, "deployment", name, "--namespace", CERT_MANAGER_NAMESPACE
                )
                for name in CERT_MANAGER_DEPLOYMENTS
            }
            if namespace is not None
            else {name: None for name in CERT_MANAGER_DEPLOYMENTS}
        )
        existing_crds = self._cert_manager_crds(state)
        present = (
            namespace is not None
            or any(resource is not None for resource in deployments.values())
            or bool(existing_crds)
        )
        if present:
            if (
                namespace is None
                or any(resource is None for resource in deployments.values())
                or set(existing_crds) != set(CERT_MANAGER_CRDS)
            ):
                raise KindGatewayApiError(
                    "cert-manager installation is partial; refusing Helm mutation"
                )
            self._verify_cert_manager_installation(state)
            return

        namespace_manifest = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": CERT_MANAGER_NAMESPACE,
                "annotations": {
                    OWNER_KEY: state.run_id,
                    MANAGED_BY_KEY: MANAGED_BY_VALUE,
                },
            },
        }
        self._assert_owned(state)
        self._kubectl(
            state,
            "create",
            "-f",
            "-",
            input_text=json.dumps(namespace_manifest, separators=(",", ":")),
        )
        created_namespace = self._get_json(state, "namespace", CERT_MANAGER_NAMESPACE)
        if created_namespace is None or not self._has_run_owner(
            created_namespace, state.run_id
        ):
            raise KindGatewayApiError(
                "cert-manager namespace ownership could not be verified after creation"
            )
        self._assert_owned(state)
        self._run(
            [
                self._tool("helm"),
                "install",
                CERT_MANAGER_RELEASE,
                CERT_MANAGER_HELM_CHART,
                "--version",
                CERT_MANAGER_VERSION,
                "--namespace",
                CERT_MANAGER_NAMESPACE,
                "--set",
                "crds.enabled=true",
                "--set",
                "config.gatewayAPI.enabled=true",
                "--set",
                f"clusterResourceNamespace={CERT_MANAGER_NAMESPACE}",
                "--wait",
                "--timeout",
                "180s",
                "--kube-context",
                state.context,
            ]
        )
        created_namespace = self._get_json(state, "namespace", CERT_MANAGER_NAMESPACE)
        if created_namespace is None or not self._has_run_owner(
            created_namespace, state.run_id
        ):
            raise KindGatewayApiError(
                "cert-manager namespace ownership was lost during Helm install"
            )
        for name in CERT_MANAGER_DEPLOYMENTS:
            deployment = self._get_json(
                state, "deployment", name, "--namespace", CERT_MANAGER_NAMESPACE
            )
            self._mark_cert_manager_owned(
                state,
                "deployment",
                name,
                deployment or {},
                namespace=CERT_MANAGER_NAMESPACE,
            )
        crds = self._cert_manager_crds(state)
        if set(crds) != set(CERT_MANAGER_CRDS):
            raise KindGatewayApiError(
                "cert-manager Helm install created an unexpected CRD inventory"
            )
        for name, crd in crds.items():
            self._require_crd(state, name, "v1")
            self._mark_cert_manager_owned(state, "crd", name, crd)
        self._verify_cert_manager_installation(state)

    def _local_ca_manifests(self, state: RunState) -> tuple[dict[str, Any], ...]:
        names = self._cert_manager_names(state)
        owned = {OWNER_KEY: state.run_id, MANAGED_BY_KEY: MANAGED_BY_VALUE}
        return (
            {
                "apiVersion": "cert-manager.io/v1",
                "kind": "Issuer",
                "metadata": {
                    "name": names["bootstrap_issuer"],
                    "namespace": CERT_MANAGER_NAMESPACE,
                    "annotations": owned,
                },
                "spec": {"selfSigned": {}},
            },
            {
                "apiVersion": "cert-manager.io/v1",
                "kind": "Certificate",
                "metadata": {
                    "name": names["root_certificate"],
                    "namespace": CERT_MANAGER_NAMESPACE,
                    "annotations": owned,
                },
                "spec": {
                    "secretName": names["ca_secret"],
                    "commonName": f"ue-gw-{state.run_id}.kind.local",
                    "subject": {"organizations": ["University Ecosystem kind"]},
                    "duration": "2160h",
                    "renewBefore": "24h",
                    "isCA": True,
                    "privateKey": {
                        "algorithm": "ECDSA",
                        "size": 256,
                        "rotationPolicy": "Always",
                    },
                    "usages": ["cert sign", "crl sign", "digital signature"],
                    "issuerRef": {
                        "name": names["bootstrap_issuer"],
                        "kind": "Issuer",
                        "group": "cert-manager.io",
                    },
                    "secretTemplate": {"annotations": owned},
                },
            },
            {
                "apiVersion": "cert-manager.io/v1",
                "kind": "ClusterIssuer",
                "metadata": {
                    "name": names["cluster_issuer"],
                    "annotations": owned,
                },
                "spec": {"ca": {"secretName": names["ca_secret"]}},
            },
        )

    def _assert_local_ca_resources_available(self, state: RunState) -> None:
        manifests = self._local_ca_manifests(state)
        existing_crds = self._cert_manager_crds(state)
        namespace_exists = (
            self._get_json(state, "namespace", CERT_MANAGER_NAMESPACE) is not None
        )
        crd_for_kind = {
            "issuer": "issuers.cert-manager.io",
            "certificate": "certificates.cert-manager.io",
            "clusterissuer": "clusterissuers.cert-manager.io",
        }
        for manifest in manifests:
            metadata = manifest["metadata"]
            namespace = metadata.get("namespace")
            args = ["--namespace", namespace] if namespace else []
            resource_kind = manifest["kind"].lower()
            if (namespace is not None and not namespace_exists) or crd_for_kind[
                resource_kind
            ] not in existing_crds:
                continue
            resource = self._get_json(state, resource_kind, metadata["name"], *args)
            if resource is not None and (
                not self._has_run_owner(resource, state.run_id)
                or not self._contains_expected(resource.get("spec"), manifest["spec"])
            ):
                raise KindGatewayApiError(
                    f"run-specific local CA {manifest['kind']} '{metadata['name']}' "
                    "already exists with conflicting ownership or configuration"
                )

        secret = (
            self._get_json(
                state,
                "secret",
                self._cert_manager_names(state)["ca_secret"],
                "--namespace",
                CERT_MANAGER_NAMESPACE,
            )
            if namespace_exists
            else None
        )
        if secret is not None:
            if secret.get("type") != "kubernetes.io/tls" or not self._has_run_owner(
                secret, state.run_id
            ):
                raise KindGatewayApiError(
                    "run-specific local CA Secret already exists with conflicting ownership"
                )
            self._local_ca_pair(state)

    @staticmethod
    def _contains_expected(actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(
                key in actual and KindGatewayApi._contains_expected(actual[key], value)
                for key, value in expected.items()
            )
        return actual == expected

    def _ensure_ca_resource(
        self, state: RunState, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        metadata = manifest["metadata"]
        name = metadata["name"]
        namespace = metadata.get("namespace")
        namespace_args = ["--namespace", namespace] if namespace else []
        kind = manifest["kind"].lower()
        resource = self._get_json(state, kind, name, *namespace_args)
        if resource is None:
            self._assert_owned(state)
            self._kubectl(
                state,
                "create",
                "-f",
                "-",
                input_text=json.dumps(manifest, separators=(",", ":")),
            )
            resource = self._get_json(state, kind, name, *namespace_args)
        if not self._has_run_owner(
            resource, state.run_id
        ) or not self._contains_expected(resource.get("spec"), manifest["spec"]):
            raise KindGatewayApiError(
                f"run-owned local CA {manifest['kind']} '{name}' could not be verified"
            )
        return resource

    def _wait_for_ca_resource(
        self, state: RunState, manifest: dict[str, Any]
    ) -> dict[str, Any]:
        metadata = manifest["metadata"]
        namespace = metadata.get("namespace")
        args = ["--namespace", namespace] if namespace else []
        kind = manifest["kind"].lower()
        self._assert_owned(state)
        self._kubectl(
            state,
            "wait",
            "--for=condition=Ready",
            f"{kind}/{metadata['name']}",
            *args,
            "--timeout=120s",
        )
        resource = self._get_json(state, kind, metadata["name"], *args)
        if not self._condition_true(resource, "Ready"):
            raise KindGatewayApiError(
                f"run-owned local CA {kind} '{metadata['name']}' is not Ready"
            )
        return resource

    @staticmethod
    def _validated_ca_pair(
        certificate_pem: bytes,
        private_key_pem: bytes,
        *,
        expected_common_name: str,
        expected_organization: str,
    ) -> bytes:
        try:
            certificate = x509.load_pem_x509_certificate(certificate_pem)
            private_key = serialization.load_pem_private_key(
                private_key_pem, password=None
            )
            constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
            usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
            public_key = certificate.public_key()
            common_names = certificate.subject.get_attributes_for_oid(
                x509.oid.NameOID.COMMON_NAME
            )
            organizations = certificate.subject.get_attributes_for_oid(
                x509.oid.NameOID.ORGANIZATION_NAME
            )
            if (
                not constraints.ca
                or not usage.key_cert_sign
                or certificate.subject != certificate.issuer
                or len(common_names) != 1
                or common_names[0].value != expected_common_name
                or len(organizations) != 1
                or organizations[0].value != expected_organization
                or not isinstance(public_key, ec.EllipticCurvePublicKey)
                or not isinstance(private_key, ec.EllipticCurvePrivateKey)
                or public_key.curve.name != "secp256r1"
            ):
                raise ValueError("certificate is not the expected run-owned ECDSA CA")
            if public_key.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ) != private_key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ):
                raise ValueError("CA private key does not match its certificate")
            now = datetime.now(UTC)
            if (
                not certificate.not_valid_before_utc
                <= now
                < certificate.not_valid_after_utc
            ):
                raise ValueError("CA certificate is outside its validity period")
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                ec.ECDSA(certificate.signature_hash_algorithm),
            )
            canonical_pem = certificate.public_bytes(serialization.Encoding.PEM)
            if certificate_pem != canonical_pem:
                raise ValueError("CA certificate is not one canonical PEM certificate")
        except (
            InvalidSignature,
            UnsupportedAlgorithm,
            ValueError,
            TypeError,
            x509.ExtensionNotFound,
        ) as exc:
            raise KindGatewayApiError("run-owned local CA key pair is invalid") from exc
        return canonical_pem

    def _local_ca_pair(self, state: RunState) -> bytes:
        name = self._cert_manager_names(state)["ca_secret"]
        secret = self._get_json(
            state, "secret", name, "--namespace", CERT_MANAGER_NAMESPACE
        )
        data = secret.get("data") if secret else None
        if (
            secret is None
            or secret.get("type") != "kubernetes.io/tls"
            or not self._has_run_owner(secret, state.run_id)
            or not isinstance(data, dict)
            or not isinstance(data.get("tls.crt"), str)
            or not isinstance(data.get("tls.key"), str)
        ):
            raise KindGatewayApiError("run-owned local CA TLS secret is unavailable")
        try:
            certificate = base64.b64decode(data["tls.crt"], validate=True)
            private_key = base64.b64decode(data["tls.key"], validate=True)
        except (ValueError, TypeError) as exc:
            raise KindGatewayApiError(
                "run-owned local CA TLS secret is malformed"
            ) from exc
        return self._validated_ca_pair(
            certificate,
            private_key,
            expected_common_name=f"ue-gw-{state.run_id}.kind.local",
            expected_organization="University Ecosystem kind",
        )

    def _ensure_local_ca(self, state: RunState) -> None:
        self._verify_cert_manager_installation(state)
        manifests = self._local_ca_manifests(state)
        for manifest in manifests:
            self._ensure_ca_resource(state, manifest)
            self._wait_for_ca_resource(state, manifest)
            if manifest["kind"] == "Certificate":
                self._local_ca_pair(state)

    def _verify_local_ca(self, state: RunState) -> bytes:
        self._verify_cert_manager_installation(state)
        for manifest in self._local_ca_manifests(state):
            metadata = manifest["metadata"]
            namespace = metadata.get("namespace")
            args = ["--namespace", namespace] if namespace else []
            resource = self._get_json(
                state, manifest["kind"].lower(), metadata["name"], *args
            )
            if (
                not self._has_run_owner(resource, state.run_id)
                or not self._contains_expected(
                    resource.get("spec") if resource else None, manifest["spec"]
                )
                or not self._condition_true(resource, "Ready")
            ):
                raise KindGatewayApiError(
                    f"run-owned local CA {manifest['kind']} is not Ready"
                )
        return self._local_ca_pair(state)

    def ca_export(self, run_id: str) -> dict[str, str]:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        certificate = self._verify_local_ca(state)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        path = self._state_dir / f"{state.cluster}-ca.crt"
        if path.is_symlink():
            raise KindGatewayApiError("local CA output path is a symbolic link")
        if path.exists():
            try:
                existing = path.read_bytes()
            except OSError as exc:
                raise KindGatewayApiError(
                    "could not read existing local CA file"
                ) from exc
            if existing != certificate:
                raise KindGatewayApiError(
                    "local CA file differs; refusing to overwrite it"
                )
        else:
            try:
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(certificate)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise KindGatewayApiError("could not create local CA file") from exc
        return {
            "run_id": state.run_id,
            "ca_bundle_path": str(path),
            "ca_bundle_sha256": hashlib.sha256(certificate).hexdigest(),
            "host_trust_store_modified": "false",
        }

    def _namespace(self, state: RunState) -> dict[str, Any] | None:
        return self._get_json(state, "namespace", ENVOY_NAMESPACE)

    def _deployment(self, state: RunState) -> dict[str, Any] | None:
        return self._get_json(
            state,
            "deployment",
            ENVOY_DEPLOYMENT,
            "--namespace",
            ENVOY_NAMESPACE,
        )

    @staticmethod
    def _resource_owner(resource: dict[str, Any] | None) -> str | None:
        if resource is None:
            return None
        owner = resource.get("metadata", {}).get("annotations", {}).get(OWNER_KEY)
        return owner if isinstance(owner, str) else None

    def _install_envoy_controller(self, state: RunState) -> RunState:
        namespace = self._namespace(state)
        deployment = self._deployment(state)
        if namespace is not None or deployment is not None:
            if (
                deployment is None
                or self._resource_owner(namespace) != state.run_id
                or self._resource_owner(deployment) != state.run_id
            ):
                raise KindGatewayApiError(
                    "Envoy Gateway namespace/deployment is unowned or only partially marked; refusing Helm mutation"
                )
            version = (
                deployment.get("metadata", {})
                .get("labels", {})
                .get("app.kubernetes.io/version")
            )
            if version != ENVOY_GATEWAY_VERSION:
                raise KindGatewayApiError(
                    f"owned Envoy Gateway deployment must be {ENVOY_GATEWAY_VERSION}"
                )
            updated = RunState(**{**state.__dict__, "controller_installed": True})
            self._save_state(updated)
            return updated

        self._assert_owned(state)
        self._run(
            [
                self._tool("helm"),
                "install",
                ENVOY_RELEASE,
                CONTROLLER_HELM_CHART,
                "--version",
                ENVOY_GATEWAY_VERSION,
                "--namespace",
                ENVOY_NAMESPACE,
                "--create-namespace",
                "--set",
                "crds.enabled=false",
                "--kube-context",
                state.context,
            ]
        )
        for kind, name in (
            ("namespace", ENVOY_NAMESPACE),
            ("deployment", ENVOY_DEPLOYMENT),
        ):
            resource = (
                self._namespace(state)
                if kind == "namespace"
                else self._deployment(state)
            )
            if resource is None:
                raise KindGatewayApiError(
                    f"Helm install did not create {kind} '{name}'"
                )
            owner = self._resource_owner(resource)
            if owner not in (None, state.run_id):
                raise KindGatewayApiError(
                    f"{kind} '{name}' has a different run ownership marker"
                )
            if owner is None:
                self._assert_owned(state)
                self._run(
                    [
                        self._tool("kubectl"),
                        "--context",
                        state.context,
                        "annotate",
                        kind,
                        name,
                        f"{OWNER_KEY}={state.run_id}",
                        "--overwrite=false",
                        *(
                            ["--namespace", ENVOY_NAMESPACE]
                            if kind == "deployment"
                            else []
                        ),
                    ]
                )
        deployment = self._deployment(state)
        if deployment is None or self._resource_owner(deployment) != state.run_id:
            raise KindGatewayApiError(
                "Envoy Gateway deployment ownership marker could not be verified"
            )
        version = (
            deployment.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/version")
        )
        if version != ENVOY_GATEWAY_VERSION:
            raise KindGatewayApiError(
                f"Envoy Gateway deployment must be {ENVOY_GATEWAY_VERSION}"
            )
        updated = RunState(**{**state.__dict__, "controller_installed": True})
        self._save_state(updated)
        return updated

    def _gateway_class_resource(self, state: RunState) -> dict[str, Any] | None:
        return self._get_json(state, "gatewayclass", state.gateway_class)

    def _assert_gateway_class_not_foreign(self, state: RunState) -> None:
        existing = self._gateway_class_resource(state)
        if existing is None:
            return
        metadata = existing.get("metadata", {})
        annotations = metadata.get("annotations", {})
        controller = existing.get("spec", {}).get("controllerName")
        if (
            annotations.get(OWNER_KEY) != state.run_id
            or annotations.get("university-ecosystem.dev/managed-by")
            != "kind_gateway_api.py"
            or controller != GATEWAY_CLASS_CONTROLLER
        ):
            raise KindGatewayApiError(
                f"GatewayClass '{state.gateway_class}' is not owned by this run; refusing to change it"
            )

    def _ensure_gateway_class(self, state: RunState) -> RunState:
        existing = self._gateway_class_resource(state)
        if existing is not None:
            self._assert_gateway_class_not_foreign(state)
            updated = RunState(**{**state.__dict__, "gateway_class_created": True})
            self._save_state(updated)
            return updated
        body = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "GatewayClass",
            "metadata": {
                "name": state.gateway_class,
                "annotations": {
                    OWNER_KEY: state.run_id,
                    "university-ecosystem.dev/managed-by": "kind_gateway_api.py",
                },
            },
            "spec": {"controllerName": GATEWAY_CLASS_CONTROLLER},
        }
        self._assert_owned(state)
        self._run(
            [
                self._tool("kubectl"),
                "--context",
                state.context,
                "create",
                "-f",
                "-",
            ],
            input_text=json.dumps(body, separators=(",", ":")),
        )
        created = self._gateway_class_resource(state)
        if (
            created is None
            or created.get("metadata", {}).get("annotations", {}).get(OWNER_KEY)
            != state.run_id
        ):
            raise KindGatewayApiError(
                "created GatewayClass ownership marker could not be verified"
            )
        updated = RunState(**{**state.__dict__, "gateway_class_created": True})
        self._save_state(updated)
        return updated

    def prepare(self, run_id: str) -> RunState:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        self._assert_gateway_class_not_foreign(state)
        self._assert_local_ca_resources_available(state)
        state = self._install_gateway_crds(state)
        self._assert_owned(state)
        self._install_cert_manager(state)
        self._ensure_local_ca(state)
        self._assert_owned(state)
        state = self._install_envoy_controller(state)
        self._assert_owned(state)
        state = self._ensure_gateway_class(state)
        return state

    @staticmethod
    def _condition_true(resource: dict[str, Any] | None, condition_type: str) -> bool:
        if resource is None:
            return False
        conditions = resource.get("status", {}).get("conditions", [])
        return any(
            isinstance(condition, dict)
            and condition.get("type") == condition_type
            and condition.get("status") == "True"
            for condition in conditions
        )

    def smoke(self, run_id: str) -> dict[str, Any]:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        self._preflight(state, include_cert_manager=False)
        deployment = self._deployment(state)
        if deployment is None or self._resource_owner(deployment) != state.run_id:
            raise KindGatewayApiError(
                "Envoy Gateway deployment is not marked as owned by this run"
            )
        available = int(deployment.get("status", {}).get("availableReplicas", 0) or 0)
        if available < 1:
            raise KindGatewayApiError("Envoy Gateway has no available replicas")
        gateway_class = self._gateway_class_resource(state)
        annotations = (
            gateway_class.get("metadata", {}).get("annotations", {})
            if gateway_class
            else {}
        )
        if annotations.get(OWNER_KEY) != state.run_id:
            raise KindGatewayApiError("GatewayClass is not marked as owned by this run")
        if not self._condition_true(gateway_class, "Accepted"):
            raise KindGatewayApiError(
                "Envoy Gateway has not accepted the run-owned GatewayClass"
            )
        return {
            "cluster": state.cluster,
            "gateway_class": state.gateway_class,
            "gateway_class_accepted": True,
            "envoy_gateway_available_replicas": available,
            "gateway_api_bundle": GATEWAY_API_BUNDLE_VERSION,
            "envoy_gateway": ENVOY_GATEWAY_VERSION,
            "scope": "controller and GatewayClass readiness; application routes remain blocked by chart parity validation",
        }

    def rollback(self, run_id: str) -> bool:
        state = self._load_state(self._validate_run_id(run_id))
        self._assert_owned(state)
        resource = self._gateway_class_resource(state)
        if resource is None:
            if state.gateway_class_created:
                self._save_state(
                    RunState(**{**state.__dict__, "gateway_class_created": False})
                )
            return False
        metadata = resource.get("metadata", {})
        annotations = metadata.get("annotations", {})
        if (
            metadata.get("name") != state.gateway_class
            or annotations.get(OWNER_KEY) != state.run_id
            or annotations.get("university-ecosystem.dev/managed-by")
            != "kind_gateway_api.py"
            or resource.get("spec", {}).get("controllerName")
            != GATEWAY_CLASS_CONTROLLER
        ):
            raise KindGatewayApiError(
                f"GatewayClass '{state.gateway_class}' is unowned or changed; refusing to delete it"
            )
        self._assert_owned(state)
        self._run(
            [
                self._tool("kubectl"),
                "--context",
                state.context,
                "delete",
                "gatewayclass",
                state.gateway_class,
                "--wait=true",
                "--timeout=60s",
            ]
        )
        remaining = self._gateway_class_resource(state)
        if remaining is not None:
            raise KindGatewayApiError("run-owned GatewayClass remains after rollback")
        updated = RunState(**{**state.__dict__, "gateway_class_created": False})
        self._save_state(updated)
        return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir(),
        help="user-local directory for run ownership records",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create", help="create a dedicated, run-owned kind cluster"
    )
    create_parser.add_argument(
        "--node-image",
        required=True,
        help="exact kindest/node image within Kubernetes 1.33–1.36",
    )
    create_parser.add_argument(
        "--run-id", help="optional 12-character lowercase hex run ID"
    )

    for name, help_text in (
        (
            "recover",
            "finish ownership markers for this run's interrupted cluster create",
        ),
        ("status", "read-only ownership and cluster status"),
        ("preflight", "read-only pinned Gateway API prerequisites check"),
        (
            "prepare",
            "install pinned Gateway API/cert-manager prerequisites and run-owned CA",
        ),
        ("smoke", "check controller availability and GatewayClass acceptance"),
        ("rollback", "delete only this run's GatewayClass; retain cluster and data"),
        (
            "teardown",
            "delete only this run's verified kind cluster after evidence capture",
        ),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--run-id", required=True)
    ca_export_parser = subparsers.add_parser(
        "ca-export",
        help="write this run's public local CA certificate without changing host trust",
    )
    ca_export_parser.add_argument("--run-id", required=True)
    registry_start_parser = subparsers.add_parser(
        "registry-start", help="start this run's persistent local registry"
    )
    registry_start_parser.add_argument("--run-id", required=True)
    registry_start_parser.add_argument(
        "--image", required=True, help="registry image pinned by sha256 digest"
    )
    registry_start_parser.add_argument(
        "--port", type=int, default=REGISTRY_HOST_PORT, help="host port (default: 5001)"
    )
    for name, help_text in (
        ("registry-status", "read-only local registry ownership and status"),
        ("registry-stop", "stop the run-owned registry while preserving its volume"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    tool = KindGatewayApi(state_dir=args.state_dir)
    try:
        if args.command == "create":
            state = tool.create(node_image=args.node_image, run_id=args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": state.run_id,
                        "cluster": state.cluster,
                        "context": state.context,
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "recover":
            state = tool.recover(args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": state.run_id,
                        "cluster": state.cluster,
                        "context": state.context,
                        "recovered": True,
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "status":
            print(json.dumps(tool.status(args.run_id), sort_keys=True))
        elif args.command == "preflight":
            print(json.dumps(tool.preflight(args.run_id), sort_keys=True))
        elif args.command == "prepare":
            state = tool.prepare(args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": state.run_id,
                        "prepared": True,
                        "gateway_class": state.gateway_class,
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "smoke":
            print(json.dumps(tool.smoke(args.run_id), sort_keys=True))
        elif args.command == "ca-export":
            print(json.dumps(tool.ca_export(args.run_id), sort_keys=True))
        elif args.command == "registry-start":
            print(
                json.dumps(
                    tool.registry_start(args.run_id, image=args.image, port=args.port),
                    sort_keys=True,
                )
            )
        elif args.command == "registry-status":
            print(json.dumps(tool.registry_status(args.run_id), sort_keys=True))
        elif args.command == "registry-stop":
            stopped = tool.registry_stop(args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": args.run_id,
                        "stopped": stopped,
                        "registry_data_preserved": True,
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "teardown":
            deleted = tool.teardown(args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": args.run_id,
                        "cluster_deleted": deleted,
                        "local_run_record_preserved": True,
                        "registry_volume_preserved": True,
                    },
                    sort_keys=True,
                )
            )
        else:
            deleted = tool.rollback(args.run_id)
            print(
                json.dumps(
                    {
                        "run_id": args.run_id,
                        "gateway_class_deleted": deleted,
                        "cluster_and_data_preserved": True,
                    },
                    sort_keys=True,
                )
            )
        return 0
    except KindGatewayApiError as exc:
        print(f"kind_gateway_api: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
