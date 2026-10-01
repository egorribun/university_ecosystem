"""Additional rendered contracts for Envoy Gateway API routing safety."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
HELM = shutil.which("helm")
API_VERSIONS = (
    "gateway.networking.k8s.io/v1/Gateway",
    "gateway.networking.k8s.io/v1/HTTPRoute",
    "gateway.envoyproxy.io/v1alpha1/ClientTrafficPolicy",
    "gateway.envoyproxy.io/v1alpha1/BackendTrafficPolicy",
    "cert-manager.io/v1/Certificate",
)


def _render_gateway_api_template(*overrides: str) -> subprocess.CompletedProcess[str]:
    assert HELM is not None, "Helm-dependent tests must be marked at collection"

    with tempfile.TemporaryDirectory(prefix="gateway-api-security-contract-") as temp:
        test_chart = Path(temp)
        templates = test_chart / "templates"
        templates.mkdir()
        (test_chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\n",
            encoding="utf-8",
        )
        for filename in ("values.yaml", "values.schema.json"):
            shutil.copy2(CHART / filename, test_chart / filename)
        for filename in ("_helpers.tpl", "gateway-api.yaml", "network-policy.yaml"):
            shutil.copy2(CHART / "templates" / filename, templates / filename)

        command = [
            HELM,
            "template",
            "gateway-security-contract",
            str(test_chart),
            "--namespace",
            "university-ecosystem",
            "--set-string",
            "applicationSecrets.existingSecret=render-contract-existing-secret",
            "--set",
            "gatewayApi.enabled=true",
            "--set",
            "ingress.enabled=false",
            "--set-string",
            r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
            "--set-string",
            r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
        ]
        for api_version in API_VERSIONS:
            command.extend(("--api-versions", api_version))
        command.extend(overrides)
        return subprocess.run(  # noqa: S603 - fixed local Helm rendering command
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_rendered_gateway_api_route_names_remain_unique_at_max_fullname_length() -> (
    None
):
    long_fullname = "a" * 63
    result = _render_gateway_api_template(
        "--set-string",
        f"fullnameOverride={long_fullname}",
    )

    assert result.returncode == 0, result.stderr
    resources = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]
    metadata_names = [
        resource["metadata"]["name"]
        for resource in resources
        if isinstance(resource.get("metadata"), dict)
        and resource["metadata"].get("name")
    ]
    http_routes = [
        resource for resource in resources if resource.get("kind") == "HTTPRoute"
    ]
    names = [resource["metadata"]["name"] for resource in http_routes]

    assert len(names) == 5
    assert all(0 < len(name) <= 63 for name in names)
    assert len(names) == len(set(names)), f"duplicate HTTPRoute names: {names}"
    assert len(metadata_names) == len(set(metadata_names)), (
        f"duplicate rendered metadata.name values: {metadata_names}"
    )


def _path_match(request_path: str, match: dict[str, Any]) -> bool:
    path = match["path"]
    if path["type"] == "Exact":
        return request_path == path["value"]
    if path["type"] != "PathPrefix":
        return False
    prefix = path["value"]
    return (
        prefix == "/"
        or request_path == prefix
        or request_path.startswith(prefix.rstrip("/") + "/")
    )


def _selected_https_route(
    routes: list[dict[str, Any]], hostname: str, request_path: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[tuple[int, int], dict[str, Any], dict[str, Any]]] = []
    for route in routes:
        if hostname not in route["spec"].get("hostnames", []):
            continue
        if not any(
            parent.get("sectionName", "").startswith("https-")
            for parent in route["spec"].get("parentRefs", [])
        ):
            continue
        for rule in route["spec"].get("rules", []):
            for match in rule.get("matches", []):
                if not _path_match(request_path, match):
                    continue
                path = match["path"]
                rank = (2 if path["type"] == "Exact" else 1, len(path["value"]))
                candidates.append((rank, route, rule))
    if not candidates:
        raise AssertionError(f"no HTTPS route matched {hostname}{request_path}")
    _, route, rule = max(candidates, key=lambda candidate: candidate[0])
    return route, rule


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_rendered_gateway_routes_preserve_edge_precedence_and_internal_grpc() -> None:
    result = _render_gateway_api_template()
    assert result.returncode == 0, result.stderr
    resources = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]
    routes = [resource for resource in resources if resource.get("kind") == "HTTPRoute"]

    expected_dispatch = (
        ("university.example.com", "/home", "frontend"),
        ("api.university.example.com", "/api/v1/profile", "gateway"),
        ("api.university.example.com", "/api/v10/profile", "gateway"),
        ("api.university.example.com", "/.well-known/jwks.json", "backend"),
        ("api.university.example.com", "/ws/ticket", "gateway"),
        ("api.university.example.com", "/ws/chat", "ws-hub"),
        ("api.university.example.com", "/api/v1/files/process/sync", "gateway"),
    )
    for hostname, request_path, expected_service in expected_dispatch:
        route, rule = _selected_https_route(routes, hostname, request_path)
        backend = rule["backendRefs"][0]
        assert backend["name"].endswith(f"-{expected_service}"), (
            hostname,
            request_path,
            backend,
        )
        if request_path == "/api/v1/profile":
            assert "-api-" in route["metadata"]["name"]
        elif request_path == "/api/v10/profile":
            assert "-route-" in route["metadata"]["name"]

    assert all(
        backend["port"] != 50051 and not backend["name"].endswith("-file-processor")
        for route in routes
        for rule in route["spec"].get("rules", [])
        for backend in rule.get("backendRefs", [])
    ), "gRPC file-processor must remain an internal gateway-to-service call"

    policies = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
    }
    gateway_egress = policies["gateway-security-contract-gateway-policy"]["spec"][
        "egress"
    ]
    assert any(
        any(
            peer.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "file-processor"
            for peer in rule.get("to", [])
        )
        and {port["port"] for port in rule.get("ports", [])} == {50051}
        for rule in gateway_egress
    ), "gateway must retain its narrowly scoped internal gRPC egress"

    file_processor_ingress = policies[
        "gateway-security-contract-file-processor-policy"
    ]["spec"]["ingress"]
    assert any(
        {port["port"] for port in rule.get("ports", [])} == {50051}
        and any(
            peer.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "gateway"
            for peer in rule.get("from", [])
        )
        for rule in file_processor_ingress
    )
