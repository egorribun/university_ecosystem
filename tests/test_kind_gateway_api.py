from __future__ import annotations

import base64
import hashlib
import json
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts import kind_gateway_api as kind_gateway_api_module
from scripts.kind_gateway_api import (
    CERT_MANAGER_CRDS,
    CERT_MANAGER_DEPLOYMENTS,
    CERT_MANAGER_HELM_CHART,
    CERT_MANAGER_NAMESPACE,
    CERT_MANAGER_RELEASE,
    CERT_MANAGER_VERSION,
    ENVOY_NAMESPACE,
    KIND_CLUSTER_LABEL,
    MANAGED_BY_KEY,
    MANAGED_BY_VALUE,
    OWNER_CONFIGMAP,
    OWNER_CONFIGMAP_NAMESPACE,
    OWNER_KEY,
    REGISTRY_DATA_PATH,
    REGISTRY_HOST_PORT,
    KindGatewayApi,
    KindGatewayApiError,
    RunState,
    default_state_dir,
)

RUN_ID = "012345abcdef"
CLUSTER = f"ue-gw-{RUN_ID}"
CONTEXT = f"kind-{CLUSTER}"
NODE_IMAGE = "kindest/node:v1.35.1"
PINNED_NODE_IMAGE = (
    "kindest/node:v1.36.4@sha256:"
    "099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed"  # pragma: allowlist secret (public kind image digest)
)
REGISTRY_IMAGE = f"registry@sha256:{'a' * 64}"


def _test_ca_pair(
    *,
    is_ca: bool = True,
    expired: bool = False,
    common_name: str = f"ue-gw-{RUN_ID}.kind.local",
) -> tuple[bytes, bytes]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(
                x509.oid.NameOID.ORGANIZATION_NAME, "University Ecosystem kind"
            ),
        ]
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(
            now - timedelta(days=1) if expired else now - timedelta(minutes=1)
        )
        .not_valid_after(
            now - timedelta(seconds=30) if expired else now + timedelta(days=30)
        )
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=is_ca,
                crl_sign=is_ca,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def _resource(
    kind: str,
    name: str,
    *,
    annotations: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {
            "name": name,
            "annotations": annotations or {},
            "labels": labels or {},
            **extra.pop("metadata", {}),
        },
        **extra,
    }


def _run_state(**changes: Any) -> RunState:
    values: dict[str, Any] = {
        "run_id": RUN_ID,
        "cluster": CLUSTER,
        "context": CONTEXT,
        "node_image": NODE_IMAGE,
        "phase": "owned",
        "crds_installed": True,
        "controller_installed": True,
        "gateway_class_created": True,
    }
    values.update(changes)
    return RunState(**values)


def _state_payload(**changes: Any) -> dict[str, Any]:
    payload = {"schema_version": 1, **_run_state().__dict__}
    payload.update(changes)
    return payload


class FakeEnvironment:
    def __init__(self, *, owned: bool = True) -> None:
        self.commands: list[tuple[list[str], dict[str, Any]]] = []
        self.clusters: set[str] = {CLUSTER}
        self.contexts: set[str] = {CONTEXT}
        self.context_cluster = CONTEXT
        self.configmap: dict[str, Any] | None = None
        self.node: dict[str, Any] | None = None
        self.crds: list[dict[str, Any]] = []
        self.resources: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        self.gateway_class: dict[str, Any] | None = None
        self.server_version = {"major": "1", "minor": "35", "gitVersion": "v1.35.1"}
        self.deleted: list[tuple[str, ...]] = []
        self.applied_manifests = 0
        self.helm_installs = 0
        self.helm_uninstalls = 0
        self.labelled = False
        self.crd_owner_on_apply: str | None = RUN_ID
        self.add_crds_on_apply = True
        self.controller_owner_on_install: str | None = RUN_ID
        self.controller_version_on_install = "v1.9.2"
        self.add_cert_manager_on_install = True
        self.cert_manager_version_on_install = CERT_MANAGER_VERSION
        self.cert_manager_available_replicas = 1
        self.cert_manager_pair = _test_ca_pair()
        self.namespace_appears_before_create = False
        self.add_controller_on_install = True
        self.ignore_annotations = False
        self.store_gateway_class = True
        self.keep_gateway_class_on_delete = False
        self.docker_volumes: dict[str, dict[str, Any]] = {}
        self.docker_containers: dict[str, dict[str, Any]] = {}
        self.node_registry_configs: dict[tuple[str, str], str] = {}
        self.node_registry_directories: set[tuple[str, str]] = set()
        self.omit_volume_after_create = False
        self.omit_container_after_run = False
        self.omit_container_after_start = False
        self.registry_stays_stopped_after_start = False
        self.fail_docker_command: tuple[str, ...] | None = None
        self.fail_docker_message = "injected Docker failure"
        if owned:
            self.set_owner()

    def set_owner(self) -> None:
        self.configmap = {
            "metadata": {
                "name": OWNER_CONFIGMAP,
                "namespace": OWNER_CONFIGMAP_NAMESPACE,
            },
            "data": {"run-id": RUN_ID, "cluster": CLUSTER, "node-image": NODE_IMAGE},
        }
        self.node = _resource(
            "Node",
            f"{CLUSTER}-control-plane",
            labels={"io.x-k8s.kind.cluster": CLUSTER, OWNER_KEY: RUN_ID},
        )
        self._add_kind_node_container(f"{CLUSTER}-control-plane")

    def _add_kind_node_container(self, name: str, image: str = NODE_IMAGE) -> None:
        self.docker_containers[name] = {
            "Name": f"/{name}",
            "Config": {"Image": image, "Labels": {KIND_CLUSTER_LABEL: CLUSTER}},
            "State": {"Running": True},
        }

    def add_valid_gateway_crds(self, *, owner: str | None = RUN_ID) -> None:
        for name in (
            "gatewayclasses.gateway.networking.k8s.io",
            "gateways.gateway.networking.k8s.io",
            "httproutes.gateway.networking.k8s.io",
        ):
            self.crds.append(
                {
                    "metadata": {
                        "name": name,
                        "annotations": {
                            "gateway.networking.k8s.io/bundle-version": "v1.6.1",
                            "gateway.networking.k8s.io/channel": "standard",
                            **({OWNER_KEY: owner} if owner is not None else {}),
                        },
                    },
                    "spec": {
                        "group": "gateway.networking.k8s.io",
                        "versions": [{"name": "v1", "served": True}],
                    },
                }
            )
        for name in (
            "clienttrafficpolicies.gateway.envoyproxy.io",
            "backendtrafficpolicies.gateway.envoyproxy.io",
        ):
            self.crds.append(
                {
                    "metadata": {
                        "name": name,
                        "annotations": (
                            {OWNER_KEY: owner} if owner is not None else {}
                        ),
                    },
                    "spec": {
                        "group": "gateway.envoyproxy.io",
                        "versions": [{"name": "v1alpha1", "served": True}],
                    },
                }
            )

    def add_controller(
        self,
        *,
        available: int = 1,
        owner: str | None = RUN_ID,
        version: str = "v1.9.2",
    ) -> None:
        self.resources[("namespace", ENVOY_NAMESPACE, None)] = _resource(
            "Namespace",
            ENVOY_NAMESPACE,
            annotations=({OWNER_KEY: owner} if owner is not None else {}),
        )
        self.resources[("deployment", "envoy-gateway", ENVOY_NAMESPACE)] = _resource(
            "Deployment",
            "envoy-gateway",
            annotations=({OWNER_KEY: owner} if owner is not None else {}),
            labels={"app.kubernetes.io/version": version},
            status={
                "availableReplicas": available,
                "conditions": [{"type": "Available", "status": "True"}],
            },
        )

    def add_cert_manager(self, *, run_owned: bool = False) -> None:
        namespace_key = ("namespace", CERT_MANAGER_NAMESPACE, None)
        if namespace_key not in self.resources:
            self.resources[namespace_key] = _resource(
                "Namespace",
                CERT_MANAGER_NAMESPACE,
                annotations=(
                    {OWNER_KEY: RUN_ID, MANAGED_BY_KEY: MANAGED_BY_VALUE}
                    if run_owned
                    else None
                ),
            )
        helm_annotations = {
            "meta.helm.sh/release-name": CERT_MANAGER_RELEASE,
            "meta.helm.sh/release-namespace": CERT_MANAGER_NAMESPACE,
        }
        helm_labels = {
            "app.kubernetes.io/managed-by": "Helm",
            "app.kubernetes.io/instance": CERT_MANAGER_RELEASE,
        }
        for name in CERT_MANAGER_DEPLOYMENTS:
            labels = {
                **helm_labels,
                "app.kubernetes.io/version": self.cert_manager_version_on_install,
            }
            annotations = dict(helm_annotations)
            if run_owned:
                annotations.update(
                    {OWNER_KEY: RUN_ID, MANAGED_BY_KEY: MANAGED_BY_VALUE}
                )
            self.resources[("deployment", name, CERT_MANAGER_NAMESPACE)] = _resource(
                "Deployment",
                name,
                labels=labels,
                annotations=annotations,
                status={"availableReplicas": self.cert_manager_available_replicas},
            )
        for name in CERT_MANAGER_CRDS:
            if name.endswith(".acme.cert-manager.io"):
                group = "acme.cert-manager.io"
            else:
                group = "cert-manager.io"
            annotations = dict(helm_annotations)
            if run_owned:
                annotations.update(
                    {OWNER_KEY: RUN_ID, MANAGED_BY_KEY: MANAGED_BY_VALUE}
                )
            self.crds.append(
                {
                    "metadata": {
                        "name": name,
                        "annotations": annotations,
                        "labels": helm_labels.copy(),
                    },
                    "spec": {
                        "group": group,
                        "versions": [{"name": "v1", "served": True}],
                    },
                }
            )

    def add_gateway_class(self, *, owned: bool = True, accepted: bool = True) -> None:
        annotations = {"university-ecosystem.dev/managed-by": "kind_gateway_api.py"}
        if owned:
            annotations[OWNER_KEY] = RUN_ID
        self.gateway_class = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "GatewayClass",
            "metadata": {"name": f"eg-{RUN_ID}", "annotations": annotations},
            "spec": {"controllerName": "gateway.envoyproxy.io/gatewayclass-controller"},
            "status": {
                "conditions": [
                    {"type": "Accepted", "status": "True" if accepted else "False"}
                ]
            },
        }

    def __call__(
        self, argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append((argv, kwargs))
        output = ""
        returncode = 0
        if argv[0] == "/fake/kind":
            if argv[1:3] == ["get", "clusters"]:
                output = "\n".join(sorted(self.clusters))
            elif argv[1:3] == ["create", "cluster"]:
                self.clusters.add(CLUSTER)
                self.contexts.add(CONTEXT)
                self.context_cluster = CONTEXT
                image = argv[argv.index("--image") + 1]
                self.node = _resource(
                    "Node",
                    f"{CLUSTER}-control-plane",
                    labels={"io.x-k8s.kind.cluster": CLUSTER},
                )
                self._add_kind_node_container(f"{CLUSTER}-control-plane", image=image)
            else:
                returncode = 2
        elif argv[0] == "/fake/kubectl":
            args = argv[3:] if len(argv) > 1 and argv[1] == "--context" else argv[1:]
            if args[:3] == ["config", "get-contexts", "--output=name"]:
                output = "\n".join(sorted(self.contexts))
            elif args[:2] == ["config", "view"]:
                output = json.dumps(
                    {
                        "contexts": [
                            {
                                "name": CONTEXT,
                                "context": {"cluster": self.context_cluster},
                            }
                        ],
                        "clusters": [{"name": self.context_cluster}],
                    }
                )
            elif args and args[0] == "version":
                output = json.dumps({"serverVersion": self.server_version})
            elif args and args[0] == "get":
                output = self._kubectl_get(args)
            elif args[:2] == ["create", "configmap"]:
                data = {}
                for arg in args:
                    if arg.startswith("--from-literal="):
                        key, value = arg.removeprefix("--from-literal=").split("=", 1)
                        data[key] = value
                self.configmap = {
                    "metadata": {
                        "name": OWNER_CONFIGMAP,
                        "namespace": OWNER_CONFIGMAP_NAMESPACE,
                    },
                    "data": data,
                }
            elif args[:2] == ["create", "-f"]:
                body = json.loads(kwargs.get("input", "{}"))
                if body.get("kind") == "GatewayClass" and self.store_gateway_class:
                    self.gateway_class = body
                elif body.get("kind") == "Namespace":
                    key = ("namespace", body["metadata"]["name"], None)
                    if self.namespace_appears_before_create:
                        self.resources[key] = _resource(
                            "Namespace",
                            body["metadata"]["name"],
                            annotations={OWNER_KEY: "ffffffffffff"},
                        )
                        self.namespace_appears_before_create = False
                    if key in self.resources:
                        returncode = 1
                    else:
                        self.resources[key] = body
                elif body.get("kind") in {"Issuer", "Certificate", "ClusterIssuer"}:
                    metadata = body["metadata"]
                    namespace = metadata.get("namespace")
                    kind = body["kind"].lower()
                    resource = {
                        **body,
                        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                    }
                    self.resources[(kind, metadata["name"], namespace)] = resource
                    if body["kind"] == "Certificate":
                        certificate, private_key = self.cert_manager_pair
                        annotations = body["spec"]["secretTemplate"]["annotations"]
                        self.resources[
                            ("secret", body["spec"]["secretName"], namespace)
                        ] = _resource(
                            "Secret",
                            body["spec"]["secretName"],
                            annotations=annotations.copy(),
                            type="kubernetes.io/tls",
                            data={
                                "tls.crt": base64.b64encode(certificate).decode(
                                    "ascii"
                                ),
                                "tls.key": base64.b64encode(private_key).decode(
                                    "ascii"
                                ),
                            },
                        )
            elif args and args[0] == "wait":
                pass
            elif args and args[0] == "label":
                if self.node is not None:
                    key, value = args[3].split("=", 1)
                    self.node["metadata"].setdefault("labels", {})[key] = value
                    self.labelled = True
            elif args and args[0] == "annotate":
                kind = args[1]
                name = args[2]
                namespace = (
                    args[args.index("--namespace") + 1]
                    if "--namespace" in args
                    else None
                )
                resource = self.resources.get((kind, name, namespace))
                if kind == "crd":
                    resource = next(
                        (
                            item
                            for item in self.crds
                            if item["metadata"]["name"] == name
                        ),
                        None,
                    )
                if resource is not None and not self.ignore_annotations:
                    annotations = resource["metadata"].setdefault("annotations", {})
                    for item in args[3:]:
                        if item.startswith("--"):
                            continue
                        if "=" in item:
                            key, value = item.split("=", 1)
                            annotations[key] = value
            elif args and args[0] == "apply":
                self.applied_manifests += 1
                if self.add_crds_on_apply:
                    self.add_valid_gateway_crds(owner=self.crd_owner_on_apply)
            elif args and args[0] == "delete":
                self.deleted.append(tuple(args[1:]))
                if args[1] == "gatewayclass" and not self.keep_gateway_class_on_delete:
                    self.gateway_class = None
            else:
                returncode = 2
        elif argv[0] == "/fake/helm":
            if len(argv) > 1 and argv[1] == "template":
                output = "apiVersion: apiextensions.k8s.io/v1\nkind: CustomResourceDefinition\n"
            elif len(argv) > 1 and argv[1] == "install":
                self.helm_installs += 1
                if len(argv) > 2 and argv[2] == CERT_MANAGER_RELEASE:
                    if self.add_cert_manager_on_install:
                        self.add_cert_manager()
                elif self.add_controller_on_install:
                    self.add_controller(
                        owner=self.controller_owner_on_install,
                        version=self.controller_version_on_install,
                    )
            else:
                returncode = 2
        elif argv[0] == "/fake/docker":
            return self._docker(argv, **kwargs)
        else:
            returncode = 2
        return subprocess.CompletedProcess(
            argv, returncode, output, "fake command error" if returncode else ""
        )

    def _docker(
        self, argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        args = argv[1:]
        output = ""
        error = ""
        returncode = 0
        if self.fail_docker_command == tuple(args):
            returncode = 1
            error = self.fail_docker_message
        elif args[:2] == ["volume", "inspect"]:
            name = args[2]
            volume = self.docker_volumes.get(name)
            if volume is None:
                returncode = 1
                error = f"Error response from daemon: get {name}: no such volume"
            else:
                output = json.dumps([volume])
        elif args[:2] == ["volume", "create"]:
            labels: dict[str, str] = {}
            index = 2
            while index < len(args) and args[index] == "--label":
                key, value = args[index + 1].split("=", 1)
                labels[key] = value
                index += 2
            name = args[index]
            self.docker_volumes[name] = {"Name": name, "Labels": labels}
            output = name
            if self.omit_volume_after_create:
                self.docker_volumes.pop(name)
        elif args[:2] == ["container", "inspect"]:
            name = args[2]
            container = self.docker_containers.get(name)
            if container is None:
                returncode = 1
                error = f"Error: No such object: {name}"
            else:
                output = json.dumps([container])
        elif args and args[0] == "run":
            name = args[args.index("--name") + 1]
            container_labels: dict[str, str] = {}
            for index, arg in enumerate(args[:-1]):
                if arg == "--label":
                    key, value = args[index + 1].split("=", 1)
                    container_labels[key] = value
            host_port = args[args.index("--publish") + 1].split(":")[-2]
            mount_values = dict(
                part.split("=", 1)
                for part in args[args.index("--mount") + 1].split(",")
            )
            volume_name = mount_values.get("source", mount_values.get("src", ""))
            alias = args[args.index("--network-alias") + 1]
            image = args[-1]
            container = {
                "Name": f"/{name}",
                "Config": {"Image": image, "Labels": container_labels},
                "HostConfig": {
                    "PortBindings": {
                        "5000/tcp": [{"HostIp": "127.0.0.1", "HostPort": host_port}]
                    }
                },
                "Mounts": [
                    {
                        "Type": mount_values.get("type"),
                        "Name": volume_name,
                        "Destination": mount_values.get("target"),
                    }
                ],
                "NetworkSettings": {"Networks": {"kind": {"Aliases": [alias]}}},
                "State": {"Running": True},
            }
            if not self.omit_container_after_run:
                self.docker_containers[name] = container
            output = "fake-container-id"
        elif args[:2] == ["container", "start"]:
            name = args[2]
            self.docker_containers[name]["State"][
                "Running"
            ] = not self.registry_stays_stopped_after_start
            if self.omit_container_after_start:
                self.docker_containers.pop(name)
            output = name
        elif args[:2] == ["container", "stop"]:
            name = args[-1]
            self.docker_containers[name]["State"]["Running"] = False
            output = name
        elif args and args[0] == "exec":
            rest = args[1:]
            if rest[0] == "-i":
                node_name, command, path = rest[1], rest[2], rest[3]
            else:
                node_name, command, path = rest[0], rest[1], rest[2]
            if command == "cat":
                config = self.node_registry_configs.get((node_name, path))
                if config is None:
                    returncode = 1
                    error = f"cat: {path}: No such file or directory"
                else:
                    output = config
            elif command == "mkdir":
                self.node_registry_directories.add((node_name, rest[-1]))
            elif command == "tee":
                output = kwargs.get("input", "")
                self.node_registry_configs[(node_name, path)] = output
            else:
                returncode = 2
                error = "unsupported fake docker exec command"
        else:
            returncode = 2
            error = "unsupported fake docker command"
        return subprocess.CompletedProcess(argv, returncode, output, error)

    def _kubectl_get(self, args: list[str]) -> str:
        resource_type = args[1]
        name = args[2] if len(args) > 2 and not args[2].startswith("-") else None
        namespace = None
        if "--namespace" in args:
            namespace = args[args.index("--namespace") + 1]
        if resource_type == "configmap":
            value = self.configmap if name == OWNER_CONFIGMAP else None
        elif resource_type == "node":
            value = self.node if name == f"{CLUSTER}-control-plane" else None
        elif resource_type == "version":
            value = {"serverVersion": self.server_version}
        elif resource_type == "crds":
            value = {"items": self.crds}
        elif resource_type == "crd":
            value = next(
                (
                    crd
                    for crd in self.crds
                    if crd.get("metadata", {}).get("name") == name
                ),
                None,
            )
        elif resource_type == "gatewayclass":
            value = (
                self.gateway_class
                if self.gateway_class and self.gateway_class["metadata"]["name"] == name
                else None
            )
        else:
            key = (resource_type, name or "", namespace)
            value = self.resources.get(key)
        return json.dumps(value) if value is not None else "null"


def _tool(tmp_path: Path, environment: FakeEnvironment) -> KindGatewayApi:
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(_run_state())
    return tool


def _interrupted_create_tool(
    tmp_path: Path, environment: FakeEnvironment | None = None
) -> tuple[KindGatewayApi, FakeEnvironment]:
    env = environment or FakeEnvironment(owned=False)
    env.node = _resource(
        "Node",
        f"{CLUSTER}-control-plane",
        labels={KIND_CLUSTER_LABEL: CLUSTER},
    )
    env._add_kind_node_container(f"{CLUSTER}-control-plane", image=NODE_IMAGE)
    tool = KindGatewayApi(
        runner=env,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            phase="creating",
            crds_installed=False,
            controller_installed=False,
            gateway_class_created=False,
        )
    )
    return tool, env


def _registry_tool(tmp_path: Path, environment: FakeEnvironment) -> KindGatewayApi:
    return _tool(tmp_path, environment)


def _inject_docker_failure(
    tool: KindGatewayApi,
    environment: FakeEnvironment,
    command: tuple[str, ...],
    message: str = "injected Docker failure",
) -> None:
    original_runner = tool._runner

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "/fake/docker" and tuple(argv[1:]) == command:
            environment.commands.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 1, "", message)
        return original_runner(argv, **kwargs)

    tool._runner = runner


def test_create_uses_run_specific_cluster_and_argv_without_shell(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment(owned=False)
    environment.clusters.clear()
    environment.contexts.clear()
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )

    state = tool.create(node_image=NODE_IMAGE, run_id=RUN_ID)

    assert state.phase == "owned"
    assert state.cluster == CLUSTER
    kind_create = next(
        (argv, kwargs)
        for argv, kwargs in environment.commands
        if argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
    )
    assert "--config=-" in kind_create[0]
    assert "containerd/certs.d" in kind_create[1]["input"]
    assert environment.labelled is True
    assert any(
        "create" in argv and "cluster" in argv for argv, _ in environment.commands
    )
    assert all(kwargs["shell"] is False for _, kwargs in environment.commands)
    saved = json.loads((tmp_path / f"{CLUSTER}.json").read_text(encoding="utf-8"))
    assert saved["run_id"] == RUN_ID
    assert saved["phase"] == "owned"


def test_create_preserves_digest_pinned_node_image_in_state_and_argv(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment(owned=False)
    environment.clusters.clear()
    environment.contexts.clear()
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )

    state = tool.create(node_image=PINNED_NODE_IMAGE, run_id=RUN_ID)
    saved_state = tool._load_state(RUN_ID)
    kind_create = next(
        argv
        for argv, _ in environment.commands
        if argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
    )

    assert state.node_image == PINNED_NODE_IMAGE
    assert saved_state.node_image == PINNED_NODE_IMAGE
    assert kind_create[kind_create.index("--image") + 1] == PINNED_NODE_IMAGE
    assert all(kwargs["shell"] is False for _, kwargs in environment.commands)


@pytest.mark.parametrize(
    "image",
    [
        "kindest/node:latest",
        "kindest/node:v1.32.9",
        "kindest/node:v1.37.0",
        "kindest/node:v1.36.4@sha256:ABCDEF" + ("0" * 58),
        "kindest/node:v1.36.4@sha256:" + ("0" * 63),
        "ghcr.io/kindest/node:v1.36.4@sha256:" + ("0" * 64),
        "kindest/node:v1.36.4@sha256:" + ("0" * 64) + " --help",
    ],
)
def test_create_rejects_unpinned_or_undocumented_kubernetes_versions(
    tmp_path: Path, image: str
) -> None:
    tool = KindGatewayApi(which=lambda name: f"/fake/{name}", state_dir=tmp_path)

    with pytest.raises(KindGatewayApiError, match="exact kindest/node"):
        tool.create(node_image=image, run_id=RUN_ID)


def test_create_refuses_existing_cluster_without_run_state(tmp_path: Path) -> None:
    environment = FakeEnvironment(owned=False)
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match="already exists without"):
        tool.create(node_image=NODE_IMAGE, run_id=RUN_ID)

    assert not any(
        argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
        for argv, _ in environment.commands
    )


def test_run_id_and_missing_tool_validation(tmp_path: Path) -> None:
    tool = KindGatewayApi(which=lambda _name: None, state_dir=tmp_path)

    assert default_state_dir().name == "kind-gateway-api"
    with pytest.raises(KindGatewayApiError, match="12 lowercase hexadecimal"):
        tool.status("not-a-run-id")
    with pytest.raises(KindGatewayApiError, match="was not found on PATH"):
        tool._tool("kind")


def test_command_failure_reports_stderr_and_argv(tmp_path: Path) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 7, "", "executable failed"
        ),
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match="executable failed"):
        tool._run(["kubectl", "get", "gatewayclass"])


def test_command_failure_without_output_uses_basic_error(tmp_path: Path) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 7, "", ""),
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match=r"command failed \(7\)"):
        tool._run(["kubectl", "get", "gatewayclass"])


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (None, "no local ownership record"),
        ("not json", "could not read local run state"),
        ("[]", "incomplete or invalid"),
        ("{}", "incomplete or invalid"),
        (
            json.dumps(
                _state_payload(
                    cluster="unrelated-cluster",
                    context="kind-unrelated-cluster",
                )
            ),
            "does not match run",
        ),
    ],
)
def test_load_state_fails_closed_for_missing_or_malformed_records(
    tmp_path: Path, contents: str | None, message: str
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    if contents is not None:
        (tmp_path / f"{CLUSTER}.json").write_text(contents, encoding="utf-8")

    with pytest.raises(KindGatewayApiError, match=message):
        tool._load_state(RUN_ID)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": 2}, "unsupported schema version"),
        ({"schema_version": True}, "unsupported schema version"),
        ({"schema_version": 1.0}, "unsupported schema version"),
        ({"crds_installed": 1}, "crds_installed.*JSON boolean"),
        ({"controller_installed": "false"}, "controller_installed.*JSON boolean"),
        ({"gateway_class_created": None}, "gateway_class_created.*JSON boolean"),
        ({"run_id": 123}, "incomplete or invalid"),
        ({"phase": "pending"}, "unsupported phase"),
    ],
)
def test_load_state_rejects_unsupported_schema_and_non_boolean_flags(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    payload = _state_payload(**changes)
    (tmp_path / f"{CLUSTER}.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(KindGatewayApiError, match=message):
        tool._load_state(RUN_ID)


def test_load_state_requires_every_ownership_boolean_and_schema_version(
    tmp_path: Path,
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    missing_flag = _state_payload()
    del missing_flag["controller_installed"]
    (tmp_path / f"{CLUSTER}.json").write_text(
        json.dumps(missing_flag), encoding="utf-8"
    )

    with pytest.raises(
        KindGatewayApiError, match=r"controller_installed.*JSON boolean"
    ):
        tool._load_state(RUN_ID)

    missing_schema = _run_state().__dict__
    (tmp_path / f"{CLUSTER}.json").write_text(
        json.dumps(missing_schema), encoding="utf-8"
    )
    with pytest.raises(KindGatewayApiError, match="incomplete or invalid"):
        tool._load_state(RUN_ID)


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not-json", "invalid kubeconfig JSON"),
        ("[]", "unexpected kubeconfig value"),
        (
            json.dumps(
                {
                    "contexts": [{"name": CONTEXT, "context": {"cluster": "wrong"}}],
                    "clusters": [{"name": "wrong"}],
                }
            ),
            "does not resolve to its expected cluster",
        ),
    ],
)
def test_context_identity_rejects_malformed_or_unrelated_kubeconfig(
    tmp_path: Path, output: str, message: str
) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, output, ""),
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool._assert_context_identity(_run_state(phase="creating"))


def test_save_state_wraps_directory_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    tool = KindGatewayApi(state_dir=blocker)

    with pytest.raises(KindGatewayApiError, match="could not write local run state"):
        tool._save_state(_run_state())


def test_save_state_cleans_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    tool = KindGatewayApi(state_dir=tmp_path)

    with pytest.raises(KindGatewayApiError, match="replace failed"):
        tool._save_state(_run_state())

    assert not list(tmp_path.glob("*.tmp"))


def test_save_state_surfaces_cleanup_failure_without_hiding_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cleanup failed")),
    )
    tool = KindGatewayApi(state_dir=tmp_path)

    with pytest.raises(KindGatewayApiError, match="replace failed"):
        tool._save_state(_run_state())


def test_save_state_applies_private_mode_on_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "name", "posix")
    tool = KindGatewayApi(state_dir=tmp_path)

    tool._save_state(_run_state())

    assert (tmp_path / f"{CLUSTER}.json").exists()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("phase", "not fully owned"),
        ("cluster", "unavailable"),
        ("context", "context .* is unavailable"),
        ("configmap_missing", "ownership ConfigMap is missing"),
        ("configmap_mismatch", "ConfigMap does not match"),
        ("node_missing", "control-plane node is missing"),
        ("node_mismatch", "control-plane node ownership marker"),
    ],
)
def test_owned_guard_refuses_incomplete_or_mismatched_markers(
    tmp_path: Path, mutation: str, message: str
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)
    state = _run_state()
    if mutation == "phase":
        state = _run_state(phase="creating")
    elif mutation == "cluster":
        environment.clusters.clear()
    elif mutation == "context":
        environment.contexts.clear()
    elif mutation == "configmap_missing":
        environment.configmap = None
    elif mutation == "configmap_mismatch":
        assert environment.configmap is not None
        environment.configmap["data"]["run-id"] = "ffffffffffff"
    elif mutation == "node_missing":
        environment.node = None
    elif mutation == "node_mismatch":
        assert environment.node is not None
        environment.node["metadata"]["labels"][OWNER_KEY] = "ffffffffffff"

    with pytest.raises(KindGatewayApiError, match=message):
        tool._assert_owned(state)


@pytest.mark.parametrize(
    ("clusters_present", "contexts_present", "phase", "message"),
    [
        (True, True, "owned", "only be established during create"),
        (False, True, "creating", "does not exist"),
        (True, False, "creating", "context .* unavailable"),
    ],
)
def test_creation_marker_guard_requires_new_cluster_and_kind_context(
    tmp_path: Path,
    clusters_present: bool,
    contexts_present: bool,
    phase: str,
    message: str,
) -> None:
    environment = FakeEnvironment()
    if not clusters_present:
        environment.clusters.clear()
    if not contexts_present:
        environment.contexts.clear()
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=message):
        tool._assert_cluster_creation_intent(_run_state(phase=phase))


def test_owner_marker_establishment_is_idempotent_for_matching_remote_markers(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    tool._establish_owner_markers(_run_state(phase="creating"))

    assert environment.labelled is False
    assert not any(
        argv[0] == "/fake/kubectl" and argv[3] in {"create", "label"}
        for argv, _ in environment.commands
    )


def test_owner_marker_establishment_rejects_mismatched_configmap_or_node(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    assert environment.configmap is not None
    environment.configmap["data"]["cluster"] = "other-cluster"
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="ConfigMap does not match"):
        tool._establish_owner_markers(_run_state(phase="creating"))

    environment = FakeEnvironment()
    assert environment.node is not None
    environment.node["metadata"]["labels"][OWNER_KEY] = "ffffffffffff"
    tool = _tool(tmp_path, environment)
    with pytest.raises(KindGatewayApiError, match="different run ownership"):
        tool._establish_owner_markers(_run_state(phase="creating"))


def test_owner_marker_establishment_rejects_missing_control_plane_node(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.node = None
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="control-plane node was not found"):
        tool._establish_owner_markers(_run_state(phase="creating"))


def test_node_marker_requires_kind_identity_and_run_id(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)
    assert environment.node is not None
    environment.node["metadata"]["labels"].pop("io.x-k8s.kind.cluster")

    with pytest.raises(
        KindGatewayApiError, match="control-plane node ownership marker"
    ):
        tool._assert_node_marker(_run_state(), environment.node)


def test_json_reader_handles_empty_null_invalid_and_non_object_output() -> None:
    def make_result(output: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, output, "")

    assert KindGatewayApi._json_or_none(make_result(""), "test") is None
    assert KindGatewayApi._json_or_none(make_result("null"), "test") is None
    with pytest.raises(KindGatewayApiError, match="invalid JSON"):
        KindGatewayApi._json_or_none(make_result("{"), "test")
    with pytest.raises(KindGatewayApiError, match="unexpected JSON value"):
        KindGatewayApi._json_or_none(make_result("[]"), "test")


@pytest.mark.parametrize(
    ("server_version", "message"),
    [
        ("not json", "could not parse Kubernetes server version"),
        (json.dumps({}), "could not parse Kubernetes server version"),
        (
            json.dumps({"serverVersion": {"major": "one", "minor": "35"}}),
            "could not parse Kubernetes server version",
        ),
    ],
)
def test_server_version_parser_rejects_malformed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    server_version: str,
    message: str,
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    monkeypatch.setattr(
        tool,
        "_kubectl",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, server_version, ""
        ),
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool._server_version(_run_state())


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not json", "could not list cluster CRDs"),
        (json.dumps({}), "could not list cluster CRDs"),
        (json.dumps({"items": "bad"}), "did not contain an item list"),
    ],
)
def test_gateway_crd_list_parser_rejects_malformed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: str,
    message: str,
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    monkeypatch.setattr(
        tool,
        "_kubectl",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, payload, ""),
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool._gateway_crds(_run_state())


@pytest.mark.parametrize(
    ("target", "mutation", "message"),
    [
        ("standard", "missing", "required CRD .* unavailable"),
        ("standard", "unserved", "does not serve required version"),
        ("standard", "wrong_bundle", "must use v1.6.1"),
        ("envoy", "missing", "required CRD .* unavailable"),
        ("envoy", "unserved", "does not serve required version"),
    ],
)
def test_required_gateway_crd_checks_fail_closed(
    tmp_path: Path, target: str, mutation: str, message: str
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    name = (
        "gatewayclasses.gateway.networking.k8s.io"
        if target == "standard"
        else "clienttrafficpolicies.gateway.envoyproxy.io"
    )
    crd = next(item for item in environment.crds if item["metadata"]["name"] == name)
    if mutation == "missing":
        environment.crds.remove(crd)
    elif mutation == "unserved":
        crd["spec"]["versions"][0]["served"] = False
    elif mutation == "wrong_bundle":
        crd["metadata"]["annotations"]["gateway.networking.k8s.io/bundle-version"] = (
            "v1.5.0"
        )
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=message):
        if target == "standard":
            tool._require_crd(_run_state(), name, "v1", require_gateway_bundle=True)
        else:
            tool._require_crd(_run_state(), name, "v1alpha1")


@pytest.mark.parametrize(
    "problem", ["missing_cert_manager", "missing_deployment", "wrong_envoy_version"]
)
def test_full_preflight_rejects_missing_required_component(
    tmp_path: Path, problem: str
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.crds.append(
        {
            "metadata": {"name": "certificates.cert-manager.io", "annotations": {}},
            "spec": {
                "group": "cert-manager.io",
                "versions": [{"name": "v1", "served": True}],
            },
        }
    )
    environment.add_controller()
    if problem == "missing_cert_manager":
        environment.crds = [
            crd
            for crd in environment.crds
            if crd["metadata"]["name"] != "certificates.cert-manager.io"
        ]
        message = "required CRD 'certificates.cert-manager.io' is unavailable"
    elif problem == "missing_deployment":
        environment.resources.clear()
        message = "Envoy Gateway deployment is unavailable"
    else:
        environment.resources[("deployment", "envoy-gateway", ENVOY_NAMESPACE)][
            "metadata"
        ]["labels"]["app.kubernetes.io/version"] = "v1.8.0"
        message = "Envoy Gateway version must be v1.9.2"
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=message):
        tool.preflight(RUN_ID)


def test_create_rerun_returns_the_same_owned_cluster_without_recreating_it(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    state = tool.create(node_image=NODE_IMAGE, run_id=RUN_ID)

    assert state.cluster == CLUSTER
    assert not any(
        argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
        for argv, _ in environment.commands
    )


def test_create_rerun_refuses_a_different_node_image(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="different node image"):
        tool.create(node_image="kindest/node:v1.35.2", run_id=RUN_ID)


def test_create_rerun_fails_closed_when_interrupted_cluster_identity_is_missing(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment(owned=False)
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(_run_state(phase="creating"))

    with pytest.raises(KindGatewayApiError, match="control-plane node was not found"):
        tool.create(node_image=NODE_IMAGE, run_id=RUN_ID)

    assert not any(
        argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
        for argv, _ in environment.commands
    )


def test_create_rerun_refuses_interrupted_state_with_different_image(
    tmp_path: Path,
) -> None:
    tool, environment = _interrupted_create_tool(tmp_path)

    with pytest.raises(KindGatewayApiError, match="creation intent with a different"):
        tool.create(node_image="kindest/node:v1.35.2", run_id=RUN_ID)

    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3:5] in (["create", "configmap"], ["label", "node"])
        for argv, _ in environment.commands
    )


def test_recover_finishes_markers_and_is_idempotent(tmp_path: Path) -> None:
    tool, environment = _interrupted_create_tool(tmp_path)

    recovered = tool.recover(RUN_ID)

    assert recovered.phase == "owned"
    assert environment.configmap is not None
    assert environment.configmap["data"]["run-id"] == RUN_ID
    assert environment.node is not None
    assert environment.node["metadata"]["labels"][OWNER_KEY] == RUN_ID
    saved = json.loads((tmp_path / f"{CLUSTER}.json").read_text(encoding="utf-8"))
    assert saved["phase"] == "owned"
    assert (
        len(
            [
                argv
                for argv, _ in environment.commands
                if argv[0] == "/fake/kubectl"
                and argv[3:5] in (["create", "configmap"], ["label", "node"])
            ]
        )
        == 2
    )

    command_count = len(environment.commands)
    assert tool.recover(RUN_ID) == recovered
    assert len(environment.commands) > command_count  # read-only ownership checks
    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3:5] in (["create", "configmap"], ["label", "node"])
        for argv, _ in environment.commands[command_count:]
    )


def test_create_rerun_recovers_matching_interrupted_create_without_recreating(
    tmp_path: Path,
) -> None:
    tool, environment = _interrupted_create_tool(tmp_path)

    recovered = tool.create(node_image=NODE_IMAGE, run_id=RUN_ID)

    assert recovered.phase == "owned"
    assert not any(
        argv[0] == "/fake/kind" and argv[1:3] == ["create", "cluster"]
        for argv, _ in environment.commands
    )


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("cluster_missing", "kind cluster .* does not exist"),
        ("context_missing", "kind context .* unavailable"),
        ("context_mismatch", "does not resolve to its expected cluster"),
        ("node_missing", "control-plane node was not found"),
        ("node_identity", "node identity does not match"),
        ("node_marker", "different run ownership marker"),
        ("configmap_marker", "ConfigMap does not match"),
        ("docker_node_missing", "kind node container .* unavailable"),
        ("docker_cluster_identity", "does not belong to this cluster"),
        ("docker_image", "image does not match the recorded run"),
    ],
)
def test_recover_refuses_unverified_or_conflicting_cluster_identity_without_mutation(
    tmp_path: Path, problem: str, message: str
) -> None:
    tool, environment = _interrupted_create_tool(tmp_path)
    node_name = f"{CLUSTER}-control-plane"
    if problem == "cluster_missing":
        environment.clusters.clear()
    elif problem == "context_missing":
        environment.contexts.clear()
    elif problem == "context_mismatch":
        environment.context_cluster = "kind-unrelated"
    elif problem == "node_missing":
        environment.node = None
    elif problem == "node_identity":
        assert environment.node is not None
        environment.node["metadata"]["labels"][KIND_CLUSTER_LABEL] = "unrelated"
    elif problem == "node_marker":
        assert environment.node is not None
        environment.node["metadata"]["labels"][OWNER_KEY] = "ffffffffffff"
    elif problem == "configmap_marker":
        environment.configmap = {
            "metadata": {
                "name": OWNER_CONFIGMAP,
                "namespace": OWNER_CONFIGMAP_NAMESPACE,
            },
            "data": {
                "run-id": "ffffffffffff",
                "cluster": CLUSTER,
                "node-image": NODE_IMAGE,
            },
        }
    elif problem == "docker_node_missing":
        environment.docker_containers.pop(node_name)
    elif problem == "docker_cluster_identity":
        environment.docker_containers[node_name]["Config"]["Labels"][
            KIND_CLUSTER_LABEL
        ] = "unrelated"
    elif problem == "docker_image":
        environment.docker_containers[node_name]["Config"]["Image"] = (
            "kindest/node:v1.35.2"
        )

    with pytest.raises(KindGatewayApiError, match=message):
        tool.recover(RUN_ID)

    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3:5] in (["create", "configmap"], ["label", "node"])
        for argv, _ in environment.commands
    )
    assert environment.configmap is None or environment.configmap["data"]["run-id"] == (
        "ffffffffffff" if problem == "configmap_marker" else RUN_ID
    )


def test_recover_repairs_only_missing_same_run_marker(tmp_path: Path) -> None:
    environment = FakeEnvironment(owned=False)
    tool, environment = _interrupted_create_tool(tmp_path, environment)
    assert environment.node is not None
    environment.node["metadata"]["labels"][OWNER_KEY] = RUN_ID

    state = tool.recover(RUN_ID)

    assert state.phase == "owned"
    assert environment.configmap is not None
    assert environment.configmap["data"]["run-id"] == RUN_ID
    assert environment.node is not None
    assert environment.node["metadata"]["labels"][OWNER_KEY] == RUN_ID
    assert any(
        argv[0] == "/fake/kubectl" and argv[3:5] == ["create", "configmap"]
        for argv, _ in environment.commands
    )
    assert not any(
        argv[0] == "/fake/kubectl" and argv[3:5] == ["label", "node"]
        for argv, _ in environment.commands
    )


def test_recover_rejects_unexpected_in_memory_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    monkeypatch.setattr(
        tool, "_load_state", lambda _run_id: _run_state(phase="pending")
    )

    with pytest.raises(KindGatewayApiError, match="cannot be recovered from phase"):
        tool.recover(RUN_ID)


@pytest.mark.parametrize(
    ("resource", "message"),
    [
        ("node_metadata", "node identity does not match"),
        ("node_labels", "node identity does not match"),
        ("configmap_data", "ConfigMap does not match"),
        ("docker_config", "does not belong to this cluster"),
    ],
)
def test_recover_refuses_malformed_remote_identity_without_mutation(
    tmp_path: Path, resource: str, message: str
) -> None:
    tool, environment = _interrupted_create_tool(tmp_path)
    node_name = f"{CLUSTER}-control-plane"
    if resource == "node_metadata":
        assert environment.node is not None
        environment.node["metadata"] = None
    elif resource == "node_labels":
        assert environment.node is not None
        environment.node["metadata"]["labels"] = None
    elif resource == "configmap_data":
        environment.configmap = {
            "metadata": {
                "name": OWNER_CONFIGMAP,
                "namespace": OWNER_CONFIGMAP_NAMESPACE,
            },
            "data": None,
        }
    elif resource == "docker_config":
        environment.docker_containers[node_name]["Config"] = None

    with pytest.raises(KindGatewayApiError, match=message):
        tool.recover(RUN_ID)

    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3:5] in (["create", "configmap"], ["label", "node"])
        for argv, _ in environment.commands
    )


def test_status_checks_ownership_read_only(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    status = tool.status(RUN_ID)

    assert status["owned"] is True
    assert status["cluster"] == CLUSTER
    assert all(
        not (
            argv[0] == "/fake/kubectl"
            and argv[3] in {"create", "apply", "annotate", "label", "delete"}
        )
        for argv, _ in environment.commands
    )
    assert all(kwargs["shell"] is False for _, kwargs in environment.commands)


def test_status_reports_unmarked_cluster_without_claiming_it(tmp_path: Path) -> None:
    environment = FakeEnvironment(owned=False)
    tool = _tool(tmp_path, environment)

    status = tool.status(RUN_ID)

    assert status["exists"] is True
    assert status["owned"] is False
    assert "ownership ConfigMap is missing" in status["reason"]
    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3] in {"create", "apply", "annotate", "label", "delete"}
        for argv, _ in environment.commands
    )


@pytest.mark.parametrize("cluster_exists", [True, False])
def test_status_without_local_state_only_reports_cluster_presence(
    tmp_path: Path, cluster_exists: bool
) -> None:
    environment = FakeEnvironment(owned=False)
    if not cluster_exists:
        environment.clusters.clear()
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )

    status = tool.status(RUN_ID)

    assert status["exists"] is cluster_exists
    assert status["owned"] is False


def test_status_reports_missing_cluster_from_local_run_record(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)
    environment.clusters.clear()

    status = tool.status(RUN_ID)

    assert status["exists"] is False
    assert status["owned"] is False


def test_status_reports_incomplete_local_run_as_unowned(tmp_path: Path) -> None:
    environment = FakeEnvironment(owned=False)
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(_run_state(phase="creating"))

    status = tool.status(RUN_ID)

    assert status["exists"] is True
    assert status["owned"] is False
    assert "not fully owned" in status["reason"]


def test_preflight_checks_documented_versions_without_mutating(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_controller()
    environment.crds.append(
        {
            "metadata": {"name": "certificates.cert-manager.io", "annotations": {}},
            "spec": {
                "group": "cert-manager.io",
                "versions": [{"name": "v1", "served": True}],
            },
        }
    )
    tool = _tool(tmp_path, environment)

    result = tool.preflight(RUN_ID)

    assert result == {
        "kubernetes": "1.35",
        "gateway_api_bundle": "v1.6.1",
        "gateway_api_channel": "standard",
        "envoy_gateway": "v1.9.2",
        "cert_manager_crd_checked": True,
    }
    assert not any(
        argv[0] == "/fake/kubectl"
        and argv[3] in {"create", "apply", "annotate", "label", "delete"}
        for argv, _ in environment.commands
    )


def test_preflight_rejects_kubernetes_outside_documented_range(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.server_version = {"major": "1", "minor": "37", "gitVersion": "v1.37.0"}
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="documented"):
        tool.preflight(RUN_ID)


def test_prepare_refuses_unowned_gateway_crd_before_applying_anything(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.crds = [
        {
            "metadata": {
                "name": "gateways.gateway.networking.k8s.io",
                "annotations": {},
            },
            "spec": {"group": "gateway.networking.k8s.io", "versions": []},
        }
    ]
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="is unowned; refusing to apply"):
        tool.prepare(RUN_ID)

    assert environment.applied_manifests == 0
    assert environment.helm_installs == 0
    assert not environment.deleted


def test_prepare_refuses_recorded_crd_setup_that_is_now_incomplete(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=r"recorded run-owned.*incomplete"):
        tool._install_gateway_crds(_run_state(crds_installed=True))

    assert environment.applied_manifests == 0
    assert not environment.deleted


def test_crd_install_skips_unrelated_preexisting_crds(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.crds.append(
        {
            "metadata": {"name": "certificates.cert-manager.io", "annotations": {}},
            "spec": {"group": "cert-manager.io"},
        }
    )
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            crds_installed=False,
            controller_installed=False,
            gateway_class_created=False,
        )
    )

    state = tool._install_gateway_crds(_run_state(crds_installed=False))

    assert state.crds_installed is True
    assert environment.crds[0]["metadata"]["name"] == "certificates.cert-manager.io"
    assert OWNER_KEY not in environment.crds[0]["metadata"]["annotations"]


def test_gateway_crd_ownership_check_ignores_unrelated_api_groups(
    tmp_path: Path,
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    unrelated = {
        "metadata": {"name": "certificates.cert-manager.io", "annotations": {}},
        "spec": {"group": "cert-manager.io"},
    }

    tool._verify_owned_gateway_crds(_run_state(), [unrelated])


def test_prepare_marks_new_crds_and_controller_after_verified_install(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.crd_owner_on_apply = None
    environment.controller_owner_on_install = None
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            crds_installed=False,
            controller_installed=False,
            gateway_class_created=False,
        )
    )

    state = tool.prepare(RUN_ID)

    assert state.crds_installed is True
    assert state.controller_installed is True
    assert state.gateway_class_created is True
    assert all(
        crd["metadata"]["annotations"][OWNER_KEY] == RUN_ID for crd in environment.crds
    )
    assert (
        environment.resources[("namespace", ENVOY_NAMESPACE, None)]["metadata"][
            "annotations"
        ][OWNER_KEY]
        == RUN_ID
    )
    assert (
        environment.resources[("deployment", "envoy-gateway", ENVOY_NAMESPACE)][
            "metadata"
        ]["annotations"][OWNER_KEY]
        == RUN_ID
    )
    crd_annotations = [
        argv
        for argv, _ in environment.commands
        if argv[0] == "/fake/kubectl" and argv[3:5] == ["annotate", "crd"]
    ]
    assert len(crd_annotations) == 5 + len(CERT_MANAGER_CRDS)


def test_cert_manager_install_is_pinned_and_marks_only_verified_release_resources(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    tool._install_cert_manager(_run_state())

    install = next(
        argv
        for argv, _ in environment.commands
        if argv[0] == "/fake/helm"
        and len(argv) > 2
        and argv[1:3] == ["install", CERT_MANAGER_RELEASE]
    )
    assert install == [
        "/fake/helm",
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
        "clusterResourceNamespace=cert-manager",
        "--wait",
        "--timeout",
        "180s",
        "--kube-context",
        CONTEXT,
    ]
    namespace = environment.resources[("namespace", CERT_MANAGER_NAMESPACE, None)]
    assert namespace["metadata"]["annotations"][OWNER_KEY] == RUN_ID
    assert namespace["metadata"]["annotations"][MANAGED_BY_KEY] == MANAGED_BY_VALUE
    for name in CERT_MANAGER_DEPLOYMENTS:
        deployment = environment.resources[("deployment", name, CERT_MANAGER_NAMESPACE)]
        assert deployment["metadata"]["annotations"][OWNER_KEY] == RUN_ID
    for crd in environment.crds:
        if crd["metadata"]["name"] in CERT_MANAGER_CRDS:
            assert crd["metadata"]["annotations"][OWNER_KEY] == RUN_ID


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("partial", "installation is partial"),
        ("wrong_version", "unowned, unready, or not"),
        ("wrong_helm_identity", "not part of the pinned Helm release"),
        ("unready", "unowned, unready, or not"),
        ("foreign_owner", "unowned by this run"),
    ],
)
def test_cert_manager_installation_fails_closed_on_existing_drift(
    tmp_path: Path, problem: str, message: str
) -> None:
    environment = FakeEnvironment()
    if problem == "partial":
        environment.resources[("namespace", CERT_MANAGER_NAMESPACE, None)] = _resource(
            "Namespace", CERT_MANAGER_NAMESPACE
        )
    else:
        environment.add_cert_manager(run_owned=True)
        if problem == "wrong_version":
            for name in CERT_MANAGER_DEPLOYMENTS:
                environment.resources[("deployment", name, CERT_MANAGER_NAMESPACE)][
                    "metadata"
                ]["labels"]["app.kubernetes.io/version"] = "v1.20.0"
        elif problem == "wrong_helm_identity":
            environment.crds[0]["metadata"]["annotations"].pop(
                "meta.helm.sh/release-name"
            )
        elif problem == "unready":
            environment.resources[
                ("deployment", CERT_MANAGER_DEPLOYMENTS[0], CERT_MANAGER_NAMESPACE)
            ]["status"]["availableReplicas"] = 0
        elif problem == "foreign_owner":
            environment.resources[("namespace", CERT_MANAGER_NAMESPACE, None)][
                "metadata"
            ]["annotations"][OWNER_KEY] = "ffffffffffff"
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=message):
        tool._install_cert_manager(_run_state())

    assert environment.helm_installs == 0


def test_cert_manager_namespace_create_race_does_not_adopt_foreign_namespace(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.namespace_appears_before_create = True
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError):
        tool._install_cert_manager(_run_state())

    namespace = environment.resources[("namespace", CERT_MANAGER_NAMESPACE, None)]
    assert namespace["metadata"]["annotations"] == {OWNER_KEY: "ffffffffffff"}
    assert environment.helm_installs == 0


@pytest.mark.parametrize(
    "resource_kind", ["issuer", "certificate", "clusterissuer", "secret"]
)
def test_prepare_rejects_foreign_local_ca_name_before_installing_cert_manager(
    tmp_path: Path, resource_kind: str
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.resources[("namespace", CERT_MANAGER_NAMESPACE, None)] = _resource(
        "Namespace",
        CERT_MANAGER_NAMESPACE,
        annotations={OWNER_KEY: RUN_ID, MANAGED_BY_KEY: MANAGED_BY_VALUE},
    )
    tool = _tool(tmp_path, environment)
    state = _run_state()
    names = tool._cert_manager_names(state)
    if resource_kind == "secret":
        name = names["ca_secret"]
        namespace = CERT_MANAGER_NAMESPACE
        resource = _resource(
            "Secret",
            name,
            annotations={OWNER_KEY: "ffffffffffff"},
            type="kubernetes.io/tls",
            data={},
        )
    else:
        manifest = next(
            item
            for item in tool._local_ca_manifests(state)
            if item["kind"].lower() == resource_kind
        )
        metadata = manifest["metadata"]
        name = metadata["name"]
        namespace = metadata.get("namespace")
        crd_name = {
            "issuer": "issuers.cert-manager.io",
            "certificate": "certificates.cert-manager.io",
            "clusterissuer": "clusterissuers.cert-manager.io",
        }[resource_kind]
        environment.crds.append(
            {
                "metadata": {"name": crd_name},
                "spec": {
                    "group": "cert-manager.io",
                    "versions": [{"name": "v1", "served": True}],
                },
            }
        )
        resource = _resource(
            manifest["kind"],
            name,
            annotations={OWNER_KEY: "ffffffffffff"},
            spec=manifest["spec"],
        )
    environment.resources[(resource_kind, name, namespace)] = resource

    with pytest.raises(
        KindGatewayApiError, match="already exists with conflicting ownership"
    ):
        tool.prepare(RUN_ID)

    assert environment.helm_installs == 0
    assert environment.applied_manifests == 0


@pytest.mark.parametrize(
    "invalid_pair",
    [
        "malformed",
        "not_ca",
        "mismatched_key",
        "expired",
        "appended_certificate",
        "wrong_subject",
    ],
)
def test_local_ca_pair_validation_rejects_invalid_material(invalid_pair: str) -> None:
    certificate, private_key = _test_ca_pair()
    if invalid_pair == "malformed":
        certificate = b"not a certificate"
    elif invalid_pair == "not_ca":
        certificate, private_key = _test_ca_pair(is_ca=False)
    elif invalid_pair == "mismatched_key":
        _, private_key = _test_ca_pair()
    elif invalid_pair == "appended_certificate":
        second_certificate, _ = _test_ca_pair()
        certificate += second_certificate
    elif invalid_pair == "wrong_subject":
        certificate, private_key = _test_ca_pair(common_name="foreign-ca.example")
    else:
        certificate, private_key = _test_ca_pair(expired=True)

    with pytest.raises(KindGatewayApiError, match="key pair is invalid"):
        KindGatewayApi._validated_ca_pair(
            certificate,
            private_key,
            expected_common_name=f"ue-gw-{RUN_ID}.kind.local",
            expected_organization="University Ecosystem kind",
        )


def test_ca_export_writes_only_the_public_certificate_create_only(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_cert_manager(run_owned=True)
    tool = _tool(tmp_path, environment)
    state = _run_state()
    tool._ensure_local_ca(state)
    certificate, private_key = environment.cert_manager_pair

    result = tool.ca_export(RUN_ID)
    output_path = tmp_path / f"{CLUSTER}-ca.crt"

    assert Path(result["ca_bundle_path"]) == output_path
    assert output_path.read_bytes() == certificate
    assert private_key not in output_path.read_bytes()
    assert result["ca_bundle_sha256"] == hashlib.sha256(certificate).hexdigest()
    assert result["host_trust_store_modified"] == "false"
    assert tool.ca_export(RUN_ID) == result

    output_path.write_bytes(b"foreign replacement")
    with pytest.raises(KindGatewayApiError, match="refusing to overwrite"):
        tool.ca_export(RUN_ID)
    assert output_path.read_bytes() == b"foreign replacement"


@pytest.mark.parametrize(
    ("apply_crds", "owner", "message"),
    [
        (False, RUN_ID, "install did not create"),
        (True, "ffffffffffff", "different run ownership marker"),
    ],
)
def test_prepare_refuses_incomplete_or_foreign_crds_after_apply(
    tmp_path: Path, apply_crds: bool, owner: str, message: str
) -> None:
    environment = FakeEnvironment()
    environment.add_crds_on_apply = apply_crds
    environment.crd_owner_on_apply = owner
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            crds_installed=False,
            controller_installed=False,
            gateway_class_created=False,
        )
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool.prepare(RUN_ID)

    assert environment.deleted == []


def test_controller_installer_refuses_partial_or_unowned_existing_resources(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.resources[("namespace", ENVOY_NAMESPACE, None)] = _resource(
        "Namespace", ENVOY_NAMESPACE, annotations={OWNER_KEY: RUN_ID}
    )
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="unowned or only partially marked"):
        tool._install_envoy_controller(_run_state())

    assert environment.helm_installs == 0


def test_controller_installer_rejects_owned_controller_with_wrong_version(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_controller(version="v1.8.0")
    tool = _tool(tmp_path, environment)

    with pytest.raises(
        KindGatewayApiError, match=r"owned Envoy Gateway deployment must be v1.9.2"
    ):
        tool._install_envoy_controller(_run_state())

    assert environment.helm_installs == 0


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("missing", "Helm install did not create namespace"),
        ("foreign", "has a different run ownership marker"),
        ("no_annotation", "deployment ownership marker could not be verified"),
        ("wrong_version", "deployment must be v1.9.2"),
    ],
)
def test_controller_install_verifies_created_namespace_and_deployment(
    tmp_path: Path, mode: str, message: str
) -> None:
    environment = FakeEnvironment()
    environment.add_controller_on_install = mode != "missing"
    environment.controller_owner_on_install = (
        "ffffffffffff"
        if mode == "foreign"
        else None
        if mode == "no_annotation"
        else RUN_ID
    )
    environment.ignore_annotations = mode == "no_annotation"
    environment.controller_version_on_install = (
        "v1.8.0" if mode == "wrong_version" else "v1.9.2"
    )
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match=message):
        tool._install_envoy_controller(_run_state())

    assert environment.helm_installs == 1
    assert not environment.deleted


def test_prepare_rerun_is_idempotent_for_run_owned_resources(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_cert_manager(run_owned=True)
    environment.add_controller()
    environment.add_gateway_class()
    tool = _tool(tmp_path, environment)

    first = tool.prepare(RUN_ID)
    commands_after_first_prepare = len(environment.commands)
    second = tool.prepare(RUN_ID)
    second_prepare_commands = environment.commands[commands_after_first_prepare:]

    assert first.gateway_class_created is True
    assert second.gateway_class_created is True
    assert environment.applied_manifests == 0
    assert environment.helm_installs == 0
    assert not any(
        argv[0] == "/fake/kubectl" and argv[3] == "create" and argv[4:6] == ["-f", "-"]
        for argv, _ in second_prepare_commands
    )


def test_prepare_installs_pinned_prerequisites_once_and_creates_run_owned_class(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            crds_installed=False,
            controller_installed=False,
            gateway_class_created=False,
        )
    )

    first = tool.prepare(RUN_ID)
    second = tool.prepare(RUN_ID)
    names = tool._cert_manager_names(_run_state())
    ca_certificate = environment.resources[
        ("certificate", names["root_certificate"], CERT_MANAGER_NAMESPACE)
    ]
    ca_issuer = environment.resources[("clusterissuer", names["cluster_issuer"], None)]

    assert first.crds_installed is True
    assert first.controller_installed is True
    assert first.gateway_class_created is True
    assert second.gateway_class_created is True
    assert environment.applied_manifests == 1
    assert environment.helm_installs == 2
    assert environment.gateway_class is not None
    assert environment.gateway_class["metadata"]["annotations"][OWNER_KEY] == RUN_ID
    assert ca_certificate["metadata"]["annotations"][OWNER_KEY] == RUN_ID
    assert ca_certificate["status"]["conditions"][0]["status"] == "True"
    assert ca_issuer["metadata"]["annotations"][OWNER_KEY] == RUN_ID


@pytest.mark.parametrize("mutation", ["owner", "manager", "controller"])
def test_prepare_refuses_existing_gatewayclass_not_owned_by_this_run(
    tmp_path: Path, mutation: str
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_controller()
    environment.add_gateway_class()
    if mutation == "owner":
        assert environment.gateway_class is not None
        environment.gateway_class["metadata"]["annotations"][OWNER_KEY] = "ffffffffffff"
    elif mutation == "manager":
        assert environment.gateway_class is not None
        environment.gateway_class["metadata"]["annotations"][
            "university-ecosystem.dev/managed-by"
        ] = "other"
    else:
        assert environment.gateway_class is not None
        environment.gateway_class["spec"]["controllerName"] = "another.controller"
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="is not owned by this run"):
        tool.prepare(RUN_ID)

    assert environment.deleted == []
    assert environment.applied_manifests == 0
    assert environment.helm_installs == 0


def test_prepare_requires_gatewayclass_creation_to_be_verifiable(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_controller()
    environment.store_gateway_class = False
    tool = KindGatewayApi(
        runner=environment,
        which=lambda name: f"/fake/{name}",
        state_dir=tmp_path,
    )
    tool._save_state(
        _run_state(
            crds_installed=True,
            controller_installed=True,
            gateway_class_created=False,
        )
    )

    with pytest.raises(
        KindGatewayApiError, match="ownership marker could not be verified"
    ):
        tool.prepare(RUN_ID)

    assert environment.gateway_class is None
    assert environment.deleted == []


def test_smoke_checks_gatewayclass_and_controller_readiness_read_only(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_controller()
    environment.add_gateway_class()
    tool = _tool(tmp_path, environment)

    result = tool.smoke(RUN_ID)

    assert result["gateway_class_accepted"] is True
    assert result["envoy_gateway_available_replicas"] == 1
    assert not any(
        argv[0] == "/fake/kubectl"
        and len(argv) > 3
        and argv[3] in {"create", "apply", "annotate", "label", "delete"}
        for argv, _ in environment.commands
    )


def test_smoke_fails_when_controller_rejects_the_gatewayclass(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    environment.add_controller()
    environment.add_gateway_class(accepted=False)
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="has not accepted"):
        tool.smoke(RUN_ID)


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("unavailable", "no available replicas"),
        ("missing_controller", "deployment is not marked as owned"),
        ("foreign_controller", "deployment is not marked as owned"),
        ("missing_class", "GatewayClass is not marked as owned"),
        ("foreign_class", "GatewayClass is not marked as owned"),
    ],
)
def test_smoke_fails_closed_for_unready_or_unowned_resources(
    tmp_path: Path,
    problem: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = FakeEnvironment()
    environment.add_valid_gateway_crds()
    if problem != "missing_controller":
        environment.add_controller(
            available=0 if problem == "unavailable" else 1,
            owner="ffffffffffff" if problem == "foreign_controller" else RUN_ID,
        )
    if problem != "missing_class":
        environment.add_gateway_class(owned=problem != "foreign_class")
    tool = _tool(tmp_path, environment)
    if problem == "missing_controller":
        monkeypatch.setattr(
            tool,
            "_preflight",
            lambda _state, *, include_cert_manager: {},
        )

    with pytest.raises(KindGatewayApiError, match=message):
        tool.smoke(RUN_ID)


def test_condition_checker_handles_missing_resource_and_missing_conditions() -> None:
    assert KindGatewayApi._condition_true(None, "Accepted") is False
    assert KindGatewayApi._condition_true({"status": {}}, "Accepted") is False


def test_resource_owner_handles_missing_resource() -> None:
    assert KindGatewayApi._resource_owner(None) is None


def test_rollback_refuses_unowned_gateway_class_and_deletes_nothing(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_gateway_class(owned=False)
    tool = _tool(tmp_path, environment)

    with pytest.raises(
        KindGatewayApiError, match="unowned or changed; refusing to delete"
    ):
        tool.rollback(RUN_ID)

    assert not environment.deleted
    assert environment.gateway_class is not None
    assert environment.helm_uninstalls == 0


def test_rollback_is_idempotent_when_owned_class_is_already_absent(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)

    assert tool.rollback(RUN_ID) is False
    assert not environment.deleted


def test_rollback_clears_stale_class_state_when_resource_is_absent(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _tool(tmp_path, environment)
    stale_state = _run_state(gateway_class_created=False)
    tool._save_state(stale_state)

    assert tool.rollback(RUN_ID) is False
    assert tool._load_state(RUN_ID).gateway_class_created is False
    assert not environment.deleted


def test_rollback_deletes_only_owned_gateway_class_and_preserves_cluster_data(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.add_controller()
    environment.add_gateway_class()
    environment.resources[("persistentvolumeclaim", "user-data", "university")] = (
        _resource("PersistentVolumeClaim", "user-data")
    )
    tool = _tool(tmp_path, environment)

    assert tool.rollback(RUN_ID) is True

    assert environment.deleted == [
        ("gatewayclass", f"eg-{RUN_ID}", "--wait=true", "--timeout=60s")
    ]
    assert environment.gateway_class is None
    assert ("persistentvolumeclaim", "user-data", "university") in environment.resources
    assert environment.clusters == {CLUSTER}
    assert environment.resources[("namespace", ENVOY_NAMESPACE, None)] is not None
    assert environment.helm_uninstalls == 0


def test_rollback_fails_if_owned_class_remains_after_delete(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    environment.add_gateway_class()
    environment.keep_gateway_class_on_delete = True
    tool = _tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="remains after rollback"):
        tool.rollback(RUN_ID)

    assert environment.gateway_class is not None
    assert environment.deleted == [
        ("gatewayclass", f"eg-{RUN_ID}", "--wait=true", "--timeout=60s")
    ]


def test_mutator_refuses_when_control_plane_run_marker_is_missing(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    assert environment.node is not None
    environment.node["metadata"]["labels"].pop(OWNER_KEY)
    environment.add_gateway_class()
    tool = _tool(tmp_path, environment)

    with pytest.raises(
        KindGatewayApiError, match="control-plane node ownership marker"
    ):
        tool.rollback(RUN_ID)

    assert not environment.deleted


def test_cli_dispatches_every_supported_command_without_cluster_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    class CliTool:
        def __init__(self, *, state_dir: Path) -> None:
            calls.append(("init", (), {"state_dir": state_dir}))

        def create(self, **kwargs: Any) -> RunState:
            calls.append(("create", (), kwargs))
            return _run_state()

        def recover(self, run_id: str) -> RunState:
            calls.append(("recover", (run_id,), {}))
            return _run_state()

        def status(self, run_id: str) -> dict[str, str]:
            calls.append(("status", (run_id,), {}))
            return {"status": "ok"}

        def preflight(self, run_id: str) -> dict[str, str]:
            calls.append(("preflight", (run_id,), {}))
            return {"preflight": "ok"}

        def prepare(self, run_id: str) -> RunState:
            calls.append(("prepare", (run_id,), {}))
            return _run_state()

        def smoke(self, run_id: str) -> dict[str, str]:
            calls.append(("smoke", (run_id,), {}))
            return {"smoke": "ok"}

        def ca_export(self, run_id: str) -> dict[str, str]:
            calls.append(("ca-export", (run_id,), {}))
            return {"ca_bundle_path": str(tmp_path / "ca.crt")}

        def registry_start(
            self, run_id: str, *, image: str, port: int
        ) -> dict[str, str]:
            calls.append(("registry-start", (run_id,), {"image": image, "port": port}))
            return {"registry": f"localhost:{port}"}

        def registry_status(self, run_id: str) -> dict[str, str]:
            calls.append(("registry-status", (run_id,), {}))
            return {"configured": "true"}

        def registry_stop(self, run_id: str) -> bool:
            calls.append(("registry-stop", (run_id,), {}))
            return True

        def rollback(self, run_id: str) -> bool:
            calls.append(("rollback", (run_id,), {}))
            return True

    monkeypatch.setattr(kind_gateway_api_module, "KindGatewayApi", CliTool)
    commands = [
        ["create", "--node-image", NODE_IMAGE, "--run-id", RUN_ID],
        ["recover", "--run-id", RUN_ID],
        ["status", "--run-id", RUN_ID],
        ["preflight", "--run-id", RUN_ID],
        ["prepare", "--run-id", RUN_ID],
        ["smoke", "--run-id", RUN_ID],
        ["ca-export", "--run-id", RUN_ID],
        ["registry-start", "--run-id", RUN_ID, "--image", REGISTRY_IMAGE],
        ["registry-status", "--run-id", RUN_ID],
        ["registry-stop", "--run-id", RUN_ID],
        ["rollback", "--run-id", RUN_ID],
    ]

    for command in commands:
        assert (
            kind_gateway_api_module.main(["--state-dir", str(tmp_path), *command]) == 0
        )
        assert isinstance(json.loads(capsys.readouterr().out), dict)

    assert [call[0] for call in calls if call[0] != "init"] == [
        "create",
        "recover",
        "status",
        "preflight",
        "prepare",
        "smoke",
        "ca-export",
        "registry-start",
        "registry-status",
        "registry-stop",
        "rollback",
    ]
    assert all(
        call[2].get("state_dir") == tmp_path for call in calls if call[0] == "init"
    )


def test_cli_reports_kind_gateway_api_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingCliTool:
        def __init__(self, *, state_dir: Path) -> None:
            self.state_dir = state_dir

        def status(self, _run_id: str) -> dict[str, str]:
            raise KindGatewayApiError("ownership marker mismatch")

    monkeypatch.setattr(kind_gateway_api_module, "KindGatewayApi", FailingCliTool)

    result = kind_gateway_api_module.main(
        ["--state-dir", str(tmp_path), "status", "--run-id", RUN_ID]
    )

    assert result == 1
    assert (
        capsys.readouterr().err.strip() == "kind_gateway_api: ownership marker mismatch"
    )


def test_script_entrypoint_help_does_not_access_a_cluster(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["kind_gateway_api.py", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(Path(kind_gateway_api_module.__file__)), run_name="__main__")

    assert exit_info.value.code == 0
    assert "Run-owned kind acceptance helpers" in capsys.readouterr().out


def test_registry_start_creates_run_owned_persistent_registry_and_node_config(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    result = tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    registry_name = f"ue-gw-registry-{RUN_ID}"
    volume_name = f"ue-gw-registry-data-{RUN_ID}"
    node_name = f"{CLUSTER}-control-plane"
    config_path = f"/etc/containerd/certs.d/localhost:{REGISTRY_HOST_PORT}/hosts.toml"
    assert result["registry"] == f"localhost:{REGISTRY_HOST_PORT}"
    assert result["in_cluster_endpoint"] == f"{registry_name}:5000"
    assert environment.docker_volumes[volume_name]["Labels"] == {
        OWNER_KEY: RUN_ID,
        MANAGED_BY_KEY: MANAGED_BY_VALUE,
        "university-ecosystem.dev/kind-cluster": CLUSTER,
    }
    container = environment.docker_containers[registry_name]
    assert container["Config"]["Image"] == REGISTRY_IMAGE
    assert container["State"]["Running"] is True
    assert REGISTRY_DATA_PATH == container["Mounts"][0]["Destination"]
    assert environment.node_registry_configs[(node_name, config_path)] == (
        kind_gateway_api_module.KindGatewayApi._registry_hosts_toml(_run_state())
    )
    assert all(kwargs["shell"] is False for _, kwargs in environment.commands)
    assert not any(
        argv[1] in {"rm", "volume"} and "rm" in argv
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_start_rerun_is_idempotent(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.commands.clear()
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    docker_commands = [
        argv[1:] for argv, _ in environment.commands if argv[0] == "/fake/docker"
    ]
    assert not any(command[:2] == ["volume", "create"] for command in docker_commands)
    assert not any(command[0] == "run" for command in docker_commands)
    assert not any(
        command[0] == "exec" and command[-2] in {"mkdir", "tee"}
        for command in docker_commands
    )
    assert environment.docker_volumes[f"ue-gw-registry-data-{RUN_ID}"]


def test_registry_status_is_read_only_and_reports_owned_container(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.commands.clear()

    result = tool.registry_status(RUN_ID)

    assert result["configured"] is True
    assert result["container_exists"] is True
    assert result["running"] is True
    assert result["image"] == REGISTRY_IMAGE
    assert result["registry"] == f"localhost:{REGISTRY_HOST_PORT}"
    assert all(
        argv[1:3] in (["volume", "inspect"], ["container", "inspect"])
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_status_reports_absent_registry_without_mutation(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    result = tool.registry_status(RUN_ID)

    assert result == {"run_id": RUN_ID, "configured": False, "running": False}
    assert not any(
        argv[1] in {"run", "create", "start", "stop"}
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_stop_preserves_container_volume_and_cluster_data(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    registry_name = f"ue-gw-registry-{RUN_ID}"
    volume_name = f"ue-gw-registry-data-{RUN_ID}"

    assert tool.registry_stop(RUN_ID) is True
    assert environment.docker_containers[registry_name]["State"]["Running"] is False
    assert volume_name in environment.docker_volumes
    assert environment.clusters == {CLUSTER}
    assert tool.registry_stop(RUN_ID) is False
    assert not any(
        argv[1:2] == ["rm"]
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_start_resumes_stopped_owned_container_and_keeps_volume(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    tool.registry_stop(RUN_ID)
    volume_name = f"ue-gw-registry-data-{RUN_ID}"
    environment.commands.clear()

    result = tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert result["running"] is True
    assert (
        environment.docker_containers[f"ue-gw-registry-{RUN_ID}"]["State"]["Running"]
        is True
    )
    assert volume_name in environment.docker_volumes
    assert any(
        argv[1:3] == ["container", "start"]
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )
    assert not any(
        argv[1:2] == ["run"] or argv[1:3] == ["volume", "create"]
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_start_fails_if_container_does_not_remain_running(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    tool.registry_stop(RUN_ID)
    environment.registry_stays_stopped_after_start = True

    with pytest.raises(KindGatewayApiError, match="did not remain running"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert f"ue-gw-registry-data-{RUN_ID}" in environment.docker_volumes
    assert (
        environment.docker_containers[f"ue-gw-registry-{RUN_ID}"]["State"]["Running"]
        is False
    )


def test_registry_start_requires_container_to_exist_after_restart(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    tool.registry_stop(RUN_ID)
    environment.omit_container_after_start = True

    with pytest.raises(
        KindGatewayApiError,
        match="started local registry container could not be verified",
    ):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert f"ue-gw-registry-data-{RUN_ID}" in environment.docker_volumes


@pytest.mark.parametrize("image", ["registry:3", "registry@sha256:bad", ""])
def test_registry_requires_an_immutable_image_digest(
    tmp_path: Path, image: str
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="exact sha256 digest"):
        tool.registry_start(RUN_ID, image=image)

    assert not environment.docker_volumes
    assert not any(argv[0] == "/fake/docker" for argv, _ in environment.commands)


@pytest.mark.parametrize("port", [True, 1023, 65536])
def test_registry_rejects_invalid_host_port(tmp_path: Path, port: int) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="between 1024 and 65535"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE, port=port)

    assert not environment.docker_volumes


@pytest.mark.parametrize(
    "message",
    ["Error: No such object: x", "no such container x", "no such volume x"],
)
def test_docker_inspect_recognizes_missing_resource_errors(
    tmp_path: Path, message: str
) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 1, "", message
        ),
        which=lambda _name: "/fake/docker",
        state_dir=tmp_path,
    )

    assert tool._docker_inspect("container", "x") is None


def test_docker_inspect_wraps_unexpected_command_errors(tmp_path: Path) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 1, "", "Docker daemon is not running"
        ),
        which=lambda _name: "/fake/docker",
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match="Docker daemon is not running"):
        tool._docker_inspect("container", "x")


def test_docker_inspect_wraps_empty_error_details(tmp_path: Path) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 7, "", ""),
        which=lambda _name: "/fake/docker",
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match="inspect failed: 7"):
        tool._docker_inspect("container", "x")


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        ("not json", "invalid JSON"),
        ("{}", "unexpected JSON value"),
        ("[]", "unexpected JSON value"),
        ("[{}, {}]", "unexpected JSON value"),
    ],
)
def test_docker_inspect_rejects_malformed_json(
    tmp_path: Path, stdout: str, message: str
) -> None:
    tool = KindGatewayApi(
        runner=lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, stdout, ""),
        which=lambda _name: "/fake/docker",
        state_dir=tmp_path,
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool._docker_inspect("container", "x")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Name", "other-volume"),
        (OWNER_KEY, "ffffffffffff"),
        (MANAGED_BY_KEY, "another-tool"),
        ("university-ecosystem.dev/kind-cluster", "other-cluster"),
    ],
)
def test_registry_volume_owner_mismatch_fails_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    tool = KindGatewayApi(state_dir=tmp_path)
    volume: dict[str, Any] = {
        "Name": f"ue-gw-registry-data-{RUN_ID}",
        "Labels": {
            OWNER_KEY: RUN_ID,
            MANAGED_BY_KEY: MANAGED_BY_VALUE,
            "university-ecosystem.dev/kind-cluster": CLUSTER,
        },
    }
    if field == "Name":
        volume[field] = value
    else:
        volume["Labels"][field] = value

    with pytest.raises(KindGatewayApiError, match="volume is unowned or changed"):
        tool._verify_registry_volume(_run_state(), volume)


@pytest.mark.parametrize(
    "mutation",
    [
        "name",
        "owner",
        "managed_by",
        "cluster",
        "image",
        "port",
        "host_ip",
        "extra_public_binding",
        "volume_type",
        "volume_name",
        "volume_destination",
        "mounts_missing",
        "port_bindings_missing",
        "network",
        "alias",
    ],
)
def test_registry_container_mismatch_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    container = environment.docker_containers[f"ue-gw-registry-{RUN_ID}"]
    if mutation == "name":
        container["Name"] = "/other"
    elif mutation == "owner":
        container["Config"]["Labels"][OWNER_KEY] = "ffffffffffff"
    elif mutation == "managed_by":
        container["Config"]["Labels"][MANAGED_BY_KEY] = "other"
    elif mutation == "cluster":
        container["Config"]["Labels"]["university-ecosystem.dev/kind-cluster"] = "other"
    elif mutation == "image":
        container["Config"]["Image"] = "other@sha256:" + "b" * 64
    elif mutation == "port":
        container["HostConfig"]["PortBindings"]["5000/tcp"][0]["HostPort"] = "5555"
    elif mutation == "host_ip":
        container["HostConfig"]["PortBindings"]["5000/tcp"][0]["HostIp"] = "127.0.0.2"
    elif mutation == "extra_public_binding":
        container["HostConfig"]["PortBindings"]["5000/tcp"].append(
            {
                "HostIp": ".".join(("0", "0", "0", "0")),
                "HostPort": str(REGISTRY_HOST_PORT),
            }
        )
    elif mutation == "volume_type":
        container["Mounts"][0]["Type"] = "bind"
    elif mutation == "volume_name":
        container["Mounts"][0]["Name"] = "other-volume"
    elif mutation == "volume_destination":
        container["Mounts"][0]["Destination"] = "/different"
    elif mutation == "mounts_missing":
        container["Mounts"] = []
    elif mutation == "port_bindings_missing":
        container["HostConfig"]["PortBindings"] = {}
    elif mutation == "network":
        container["NetworkSettings"]["Networks"] = {}
    else:
        container["NetworkSettings"]["Networks"]["kind"]["Aliases"] = []

    with pytest.raises(KindGatewayApiError, match="container is unowned or changed"):
        tool._verify_registry_container(
            _run_state(),
            container,
            image=REGISTRY_IMAGE,
            port=None
            if mutation in {"host_ip", "port_bindings_missing"}
            else REGISTRY_HOST_PORT,
        )


@pytest.mark.parametrize("mutation", ["missing", "wrong_name", "wrong_cluster"])
def test_registry_node_container_identity_is_required(
    tmp_path: Path, mutation: str
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    node_name = f"{CLUSTER}-control-plane"
    if mutation == "missing":
        environment.docker_containers.pop(node_name)
    elif mutation == "wrong_name":
        environment.docker_containers[node_name]["Name"] = "/different"
    else:
        environment.docker_containers[node_name]["Config"]["Labels"][
            KIND_CLUSTER_LABEL
        ] = "different-cluster"

    with pytest.raises(KindGatewayApiError, match="kind node container"):
        tool._verify_kind_node_container(_run_state(), node_name)


def test_registry_refuses_unmarked_volume_before_creating_a_container(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    volume_name = f"ue-gw-registry-data-{RUN_ID}"
    environment.docker_volumes[volume_name] = {"Name": volume_name, "Labels": {}}
    tool = _registry_tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="volume is unowned or changed"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert f"ue-gw-registry-{RUN_ID}" not in environment.docker_containers
    assert not any(
        argv[1:2] == ["run"] or argv[1:3] == ["volume", "create"]
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_refuses_unmarked_container_without_changing_it(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    registry_name = f"ue-gw-registry-{RUN_ID}"
    container = environment.docker_containers[registry_name]
    container["Config"]["Labels"][OWNER_KEY] = "ffffffffffff"
    before = json.loads(json.dumps(container))
    environment.commands.clear()

    with pytest.raises(KindGatewayApiError, match="container is unowned or changed"):
        tool.registry_stop(RUN_ID)

    assert environment.docker_containers[registry_name] == before
    assert not any(
        argv[1:3] in (["container", "stop"], ["container", "start"])
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_start_refuses_unowned_cluster_before_docker_mutation(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    environment.configmap = None
    tool = _registry_tool(tmp_path, environment)

    with pytest.raises(KindGatewayApiError, match="ownership ConfigMap is missing"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert not environment.docker_volumes
    assert not any(
        argv[1:2] in (["run"], ["volume"])
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


@pytest.mark.parametrize("omit_volume", [True, False])
def test_registry_creation_requires_post_mutation_markers(
    tmp_path: Path, omit_volume: bool
) -> None:
    environment = FakeEnvironment()
    environment.omit_volume_after_create = omit_volume
    environment.omit_container_after_run = not omit_volume
    tool = _registry_tool(tmp_path, environment)
    message = (
        "created registry volume could not be verified"
        if omit_volume
        else "created local registry container could not be verified"
    )

    with pytest.raises(KindGatewayApiError, match=message):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert not environment.deleted


def test_registry_start_command_failure_keeps_owned_volume(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    original_runner = tool._runner

    def fail_registry_run(
        argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if argv[0] == "/fake/docker" and argv[1] == "run":
            environment.commands.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 1, "", "port conflict")
        return original_runner(argv, **kwargs)

    tool._runner = fail_registry_run
    with pytest.raises(KindGatewayApiError, match="port conflict"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert f"ue-gw-registry-data-{RUN_ID}" in environment.docker_volumes
    assert f"ue-gw-registry-{RUN_ID}" not in environment.docker_containers


def test_registry_start_refuses_changed_existing_image_or_port(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    container = environment.docker_containers[f"ue-gw-registry-{RUN_ID}"]
    container["Config"]["Image"] = "other@sha256:" + "b" * 64

    with pytest.raises(KindGatewayApiError, match="container is unowned or changed"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)


def test_registry_start_refuses_changed_node_registry_config(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    node_name = f"{CLUSTER}-control-plane"
    config_path = f"/etc/containerd/certs.d/localhost:{REGISTRY_HOST_PORT}/hosts.toml"
    environment.node_registry_configs[(node_name, config_path)] = "# another run\n"
    environment.commands.clear()

    with pytest.raises(KindGatewayApiError, match=r"config .* is unowned or changed"):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert not any(
        argv[1] == "exec" and argv[-2] in {"mkdir", "tee"}
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            (
                "exec",
                f"{CLUSTER}-control-plane",
                "cat",
                f"/etc/containerd/certs.d/localhost:{REGISTRY_HOST_PORT}/hosts.toml",
            ),
            "permission denied",
        ),
        (
            (
                "exec",
                f"{CLUSTER}-control-plane",
                "mkdir",
                "-p",
                f"/etc/containerd/certs.d/localhost:{REGISTRY_HOST_PORT}",
            ),
            "mkdir denied",
        ),
        (
            (
                "exec",
                "-i",
                f"{CLUSTER}-control-plane",
                "tee",
                f"/etc/containerd/certs.d/localhost:{REGISTRY_HOST_PORT}/hosts.toml",
            ),
            "write denied",
        ),
    ],
)
def test_registry_node_configuration_command_failures_fail_closed(
    tmp_path: Path, command: tuple[str, ...], message: str
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    _inject_docker_failure(tool, environment, command, message)

    with pytest.raises(KindGatewayApiError, match=message):
        tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)

    assert environment.docker_volumes
    assert not environment.deleted


def test_registry_status_reports_owned_volume_without_container(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.docker_containers.pop(f"ue-gw-registry-{RUN_ID}")

    result = tool.registry_status(RUN_ID)

    assert result["configured"] is True
    assert result["container_exists"] is False
    assert result["running"] is False


def test_registry_status_refuses_container_without_volume(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.docker_volumes.pop(f"ue-gw-registry-data-{RUN_ID}")

    with pytest.raises(KindGatewayApiError, match="no run-owned data volume"):
        tool.registry_status(RUN_ID)


def test_registry_stop_is_idempotent_without_resources(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)

    assert tool.registry_stop(RUN_ID) is False
    assert not any(
        argv[1:2] in (["run"], ["stop"], ["rm"])
        for argv, _ in environment.commands
        if argv[0] == "/fake/docker"
    )


def test_registry_stop_preserves_volume_when_container_is_missing(
    tmp_path: Path,
) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.docker_containers.pop(f"ue-gw-registry-{RUN_ID}")

    assert tool.registry_stop(RUN_ID) is False
    assert f"ue-gw-registry-data-{RUN_ID}" in environment.docker_volumes


def test_registry_stop_refuses_container_without_volume(tmp_path: Path) -> None:
    environment = FakeEnvironment()
    tool = _registry_tool(tmp_path, environment)
    tool.registry_start(RUN_ID, image=REGISTRY_IMAGE)
    environment.docker_volumes.pop(f"ue-gw-registry-data-{RUN_ID}")

    with pytest.raises(KindGatewayApiError, match="no run-owned data volume"):
        tool.registry_stop(RUN_ID)

    assert (
        environment.docker_containers[f"ue-gw-registry-{RUN_ID}"]["State"]["Running"]
        is True
    )
