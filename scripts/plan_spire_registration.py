"""Produce an inspectable SPIRE entry plan; never contact or modify a cluster."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

MAX_RENDER_BYTES = 4 * 1024 * 1024
COMPONENT = "app.kubernetes.io/component"
INSTANCE = "app.kubernetes.io/instance"
IDENTITY_FIELDS = {
    "backend": ("INTERNAL_HTTP_MTLS_ENABLED", "INTERNAL_HTTP_MTLS_SERVER_SPIFFE_ID"),
    "gateway": ("INTERNAL_HTTP_MTLS_ENABLED", "SPIFFE_MY_ID"),
    "ws-hub": ("SPIFFE_ENABLED", "SPIFFE_MY_ID"),
    "file-processor": ("FP_INTERNAL_HTTP_MTLS_ENABLED", "FP_SPIFFE_MY_ID"),
}
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_DOMAIN = (
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
_SERVICE_ACCOUNT = re.compile(
    r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?(?:\.[a-z0-9](?:[-a-z0-9]*[a-z0-9])?)*"
)
_IDENTITY = re.compile(rf"spiffe://{_DOMAIN}(?:/[A-Za-z0-9._~-]+)+")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_AGENT_PATH = re.compile(rf"/spire/agent/k8s_psat/[A-Za-z0-9._~-]+/(?:pod/)?{_UUID}")


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys instead of silently taking the last."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError("rendered YAML requires unique string mapping keys")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("rendered workload contains a missing or invalid mapping")
    return value


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _LABEL.fullmatch(value):
        raise ValueError(f"{field} must be an explicit Kubernetes DNS label")
    return value


def _identity(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or not _IDENTITY.fullmatch(value)
        or len(urlsplit(value).netloc) > 253
        or any(part in {".", ".."} for part in value.split("/")[3:])
    ):
        raise ValueError("identity must be an exact canonical SPIFFE URI")
    return value


def _service_account(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 253
        or not _SERVICE_ACCOUNT.fullmatch(value)
    ):
        raise ValueError(
            "serviceAccountName must be an explicit Kubernetes DNS subdomain"
        )
    return value


def _environment(container: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    entries = container.get("env", [])
    if not isinstance(entries, list):
        raise ValueError("container env must be a list")
    for raw in entries:
        entry = _mapping(raw)
        name = entry.get("name")
        if not isinstance(name, str) or name in result:
            raise ValueError("container environment names must be unique strings")
        # Resolve only literal non-secret identity configuration. Secret references
        # are deliberately not read or copied into the plan.
        value = entry.get("value")
        result[name] = value if isinstance(value, str) else ""
    return result


def build_plan(
    documents: Sequence[Any], *, namespace: str, release: str, parent_id: str
) -> dict[str, Any]:
    """Bind logical identities to actual rendered namespace/SA selectors.

    The operator supplies an already-attested concrete node/pod parent ID.
    Parsing it is not proof of attestation; verify it against `agent list` before
    applying any separately reviewed command. No aliases or parent are invented.
    """
    namespace = _name(namespace, "namespace")
    release = _name(release, "release")
    parent_id = _identity(parent_id)
    parent = urlsplit(parent_id)
    if not _AGENT_PATH.fullmatch(parent.path):
        raise ValueError("parent must be a concrete k8s_psat node/pod agent ID")
    workloads: dict[str, tuple[str, str, dict[str, str]]] = {}
    seen_components: set[str] = set()
    for raw in documents:
        if raw is None:
            continue
        document = _mapping(raw)
        if document.get("kind") != "Deployment":
            continue
        metadata = _mapping(document.get("metadata"))
        labels = _mapping(metadata.get("labels"))
        component = labels.get(COMPONENT)
        if (
            labels.get(INSTANCE) != release
            or not isinstance(component, str)
            or component not in IDENTITY_FIELDS
        ):
            continue
        if metadata.get("namespace") != namespace or component in seen_components:
            raise ValueError(
                "selected release has wrong namespace or duplicate component"
            )
        seen_components.add(component)
        spec = _mapping(
            _mapping(_mapping(document.get("spec")).get("template")).get("spec")
        )
        service_account = _service_account(spec.get("serviceAccountName"))
        containers = spec.get("containers")
        if not isinstance(containers, list) or len(containers) != 1:
            raise ValueError("identity planning requires exactly one main container")
        environ = _environment(_mapping(containers[0]))
        flag, identity_field = IDENTITY_FIELDS[component]
        if environ.get(flag) != "true":
            if component == "file-processor" and flag not in environ:
                continue  # Public JWKS override has no HTTP Workload API client.
            raise ValueError(
                "selected workload must render its explicit mTLS flag true"
            )
        identity = _identity(environ.get(identity_field))
        if urlsplit(identity).netloc != parent.netloc:
            raise ValueError("workload and attested parent must share the trust domain")
        workloads[component] = (identity, service_account, environ)
    if not {"backend", "gateway"}.issubset(workloads):
        raise ValueError("complete backend and gateway chain is required")
    identities = [item[0] for item in workloads.values()]
    accounts = [item[1] for item in workloads.values()]
    if len(set(identities)) != len(identities) or len(set(accounts)) != len(accounts):
        raise ValueError("workloads require distinct identities and service accounts")
    backend_id, _, backend_environment = workloads["backend"]
    allowed = backend_environment.get(
        "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS", ""
    ).split(",")
    if len(set(allowed)) != len(allowed) or set(allowed) != set(identities):
        raise ValueError(
            "backend allowlist must exactly match active identities including its probe"
        )
    for component, (_, _, environ) in workloads.items():
        if component == "backend":
            continue
        field = (
            "FP_BACKEND_SPIFFE_ID"
            if component == "file-processor"
            else "BACKEND_SPIFFE_ID"
        )
        if environ.get(field) != backend_id:
            raise ValueError(
                "client peer identity differs from issued backend identity"
            )
    entries = []
    for component, (identity, account, _) in sorted(workloads.items()):
        entries.append(
            {
                "component": component,
                "namespace": namespace,
                "service_account": account,
                "spiffe_id": identity,
                "argv": [
                    "/opt/spire/bin/spire-server",
                    "entry",
                    "create",
                    "-parentID",
                    parent_id,
                    "-spiffeID",
                    identity,
                    "-selector",
                    f"k8s:ns:{namespace}",
                    "-selector",
                    f"k8s:sa:{account}",
                    "-x509SVIDTTL",
                    "3600",
                ],
            }
        )
    return {
        "mode": "plan-only",
        "release": release,
        "parent_id": parent_id,
        "entries": entries,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--parent-id", required=True)
    args = parser.parse_args(argv)
    try:
        with args.rendered.open("rb") as stream:
            data = stream.read(MAX_RENDER_BYTES + 1)
        if len(data) > MAX_RENDER_BYTES:
            raise ValueError("rendered manifest exceeds 4 MiB")
        documents = list(yaml.load_all(data.decode("utf-8"), Loader=UniqueKeyLoader))
        plan = build_plan(
            documents,
            namespace=args.namespace,
            release=args.release,
            parent_id=args.parent_id,
        )
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        # YAML parser errors can contain source snippets, including unrelated
        # inline credentials. Never echo the rendered deployment on failure.
        sys.stderr.write(
            "registration plan rejected: check rendered identities and arguments\n"
        )
        return 2
    plan["rendered_sha256"] = hashlib.sha256(data).hexdigest()
    json.dump(plan, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
