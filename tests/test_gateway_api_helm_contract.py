"""Helm contracts for the fail-closed Envoy Gateway API preview."""

from __future__ import annotations

import json
import re
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


def _helm() -> str:
    assert HELM is not None, "Helm-dependent tests must be marked at collection"
    return HELM


def _render(
    *overrides: str,
    with_apis: bool = True,
    omitted_apis: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    command = [
        _helm(),
        "template",
        "gateway-contract",
        str(CHART),
        "--namespace",
        "university-ecosystem",
        "--set-string",
        "applicationSecrets.existingSecret=render-contract-existing-secret",
        "--set",
        "redis.enabled=false",
        "--set",
        "nats.enabled=false",
    ]
    if with_apis:
        for api_version in API_VERSIONS:
            if api_version not in omitted_apis:
                command.extend(("--api-versions", api_version))
    command.extend(overrides)
    return subprocess.run(  # noqa: S603 - fixed local Helm contract command
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _resources(*overrides: str) -> list[dict[str, Any]]:
    result = _render(*overrides)
    assert result.returncode == 0, result.stderr
    return [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]


def _render_gateway_template_isolated(
    *overrides: str,
    client_ip_detection: str = '{"directSourceIP":{}}',
) -> subprocess.CompletedProcess[str]:
    """Render the production Gateway template without the chart-wide fail gate.

    The full chart deliberately refuses Gateway API activation while parity
    gaps remain. This isolated chart still evaluates the exact shipped values,
    schema, helper, and Gateway template so the dormant policy is render-tested
    without bypassing that release guard.
    """
    with tempfile.TemporaryDirectory(prefix="gateway-api-template-") as temp_dir:
        test_chart = Path(temp_dir)
        templates = test_chart / "templates"
        templates.mkdir()
        (test_chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\n",
            encoding="utf-8",
        )
        shutil.copy2(CHART / "values.yaml", test_chart / "values.yaml")
        shutil.copy2(CHART / "values.schema.json", test_chart / "values.schema.json")
        shutil.copy2(CHART / "templates" / "_helpers.tpl", templates / "_helpers.tpl")
        shutil.copy2(
            CHART / "templates" / "gateway-api.yaml", templates / "gateway-api.yaml"
        )

        command = [
            _helm(),
            "template",
            "gateway-contract",
            str(test_chart),
            "--namespace",
            "university-ecosystem",
            "--set-string",
            "applicationSecrets.existingSecret=render-contract-existing-secret",
            "--set",
            "gatewayApi.enabled=true",
            "--set",
            "ingress.enabled=false",
            "--set-json",
            f"gatewayApi.clientIPDetection={client_ip_detection}",
            "--set-string",
            r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
            "--set-string",
            r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
        ]
        for api_version in API_VERSIONS:
            command.extend(("--api-versions", api_version))
        command.extend(overrides)
        return subprocess.run(  # noqa: S603 - fixed local Helm contract command
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


def _render_network_policy_template_isolated(
    *overrides: str,
) -> subprocess.CompletedProcess[str]:
    """Render the shipped NetworkPolicy template without unrelated chart gates."""
    with tempfile.TemporaryDirectory(prefix="gateway-api-network-policy-") as temp_dir:
        test_chart = Path(temp_dir)
        templates = test_chart / "templates"
        templates.mkdir()
        (test_chart / "Chart.yaml").write_text(
            "apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\n",
            encoding="utf-8",
        )
        shutil.copy2(CHART / "values.yaml", test_chart / "values.yaml")
        shutil.copy2(CHART / "values.schema.json", test_chart / "values.schema.json")
        shutil.copy2(CHART / "templates" / "_helpers.tpl", templates / "_helpers.tpl")
        shutil.copy2(
            CHART / "templates" / "network-policy.yaml",
            templates / "network-policy.yaml",
        )

        command = [
            _helm(),
            "template",
            "gateway-contract",
            str(test_chart),
            "--namespace",
            "university-ecosystem",
        ]
        command.extend(overrides)
        return subprocess.run(  # noqa: S603 - fixed local Helm contract command
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )


def _conditional_bodies(template: str, expression: str) -> list[str]:
    """Extract balanced Go-template if bodies, including nested range blocks."""
    actions = list(re.finditer(r"\{\{-?\s*(.*?)\s*-?\}\}", template, re.DOTALL))
    bodies: list[str] = []
    for index, opening in enumerate(actions):
        if opening.group(1).strip() != f"if {expression}":
            continue
        depth = 1
        body_start = opening.end()
        for action in actions[index + 1 :]:
            expression_text = action.group(1).strip()
            if expression_text.startswith(("if ", "range ", "with ")):
                depth += 1
            elif expression_text == "end":
                depth -= 1
                if depth == 0:
                    bodies.append(template[body_start : action.start()])
                    break
    return bodies


def _gateway_api_overrides(*extra: str) -> tuple[str, ...]:
    return (
        "--set",
        "gatewayApi.enabled=true",
        "--set-json",
        'gatewayApi.clientIPDetection={"directSourceIP":{}}',
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
        *extra,
    )


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_is_disabled_by_default() -> None:
    resources = _resources()

    assert not any(
        resource.get("kind")
        in {
            "Gateway",
            "HTTPRoute",
            "ClientTrafficPolicy",
            "BackendTrafficPolicy",
            "Certificate",
        }
        for resource in resources
    )


def test_gateway_api_route_values_keep_api_auth_and_ws_ownership_distinct() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    api_host = values["ingress"]["hosts"][1]
    assert api_host["host"] == "api.university.example.com"
    assert [
        (path["path"], path["pathType"], path["service"]) for path in api_host["paths"]
    ] == [
        ("/ws/ticket", "Exact", "gateway"),
        ("/ws/chat", "Exact", "ws-hub"),
        ("/", "Prefix", "gateway"),
        ("/.well-known", "Prefix", "backend"),
    ]
    assert [
        (path["path"], path["pathType"], path["service"])
        for path in values["ingress"]["hosts"][0]["paths"]
    ] == [
        ("/api", "Prefix", "gateway"),
        ("/graphql", "Exact", "gateway"),
        ("/ws/ticket", "Exact", "gateway"),
        ("/ws/chat", "Exact", "ws-hub"),
        ("/static", "Prefix", "backend"),
        ("/.well-known", "Prefix", "backend"),
        ("/", "Prefix", "frontend"),
    ]


def test_gateway_api_template_keeps_buffer_route_scoped_and_rate_client_distinct() -> (
    None
):
    template = (CHART / "templates" / "gateway-api.yaml").read_text(encoding="utf-8")

    # Body buffering stays on the isolated versioned API route. The rate
    # policy targets the Gateway so Envoy Gateway applies its local counters
    # to each route, with distinct source-IP buckets.
    assert "kind: BackendTrafficPolicy" in template
    assert "kind: HTTPRoute" in template
    assert "value: /api/v1" in template
    assert "targetRefs:" in template
    assert "requestBuffer:" in template
    assert "rateLimit:" in template
    assert "kind: Gateway" in template
    assert "type: Distinct" in template
    assert "connectionLimit:" not in template


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_request_buffer_is_attached_only_to_isolated_api_route() -> None:
    result = _render_gateway_template_isolated()
    assert result.returncode == 0, result.stderr
    resources = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]

    routes = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "HTTPRoute"
    }
    policies = [
        resource
        for resource in resources
        if resource.get("kind") == "BackendTrafficPolicy"
        and "requestBuffer" in resource.get("spec", {})
    ]
    assert len(policies) == 1
    policy = policies[0]
    target = policy["spec"]["targetRefs"]
    assert len(target) == 1
    assert target[0]["group"] == "gateway.networking.k8s.io"
    assert target[0]["kind"] == "HTTPRoute"
    assert target[0]["name"] in routes
    assert policy["spec"]["requestBuffer"] == {"limit": "50Mi"}

    api_route = routes[target[0]["name"]]
    assert api_route["spec"]["hostnames"] == ["api.university.example.com"]
    assert api_route["spec"]["rules"] == [
        {
            "matches": [{"path": {"type": "PathPrefix", "value": "/api/v1"}}],
            "backendRefs": [
                {
                    "group": "",
                    "kind": "Service",
                    "name": "gateway-contract-university-ecosystem-gateway",
                    "port": 8080,
                }
            ],
        }
    ]

    catch_all = routes["gateway-contract-university-ecosystem-route-1"]
    catch_all_matches = [
        match for rule in catch_all["spec"]["rules"] for match in rule["matches"]
    ]
    assert {match["path"]["value"] for match in catch_all_matches} == {
        "/ws/ticket",
        "/ws/chat",
        "/",
        "/.well-known",
    }


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_renders_per_source_ip_local_rate_policy_and_selected_ip_mode() -> (
    None
):
    result = _render_gateway_template_isolated()
    assert result.returncode == 0, result.stderr
    resources = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]

    rate_policies = [
        resource
        for resource in resources
        if resource.get("kind") == "BackendTrafficPolicy"
        and "rateLimit" in resource.get("spec", {})
    ]
    assert len(rate_policies) == 1
    policy = rate_policies[0]
    assert policy["spec"]["targetRefs"] == [
        {
            "group": "gateway.networking.k8s.io",
            "kind": "Gateway",
            "name": "gateway-contract-university-ecosystem",
        }
    ]
    rules = policy["spec"]["rateLimit"]["local"]["rules"]
    assert len(rules) == 2
    assert [rule["clientSelectors"][0]["sourceCIDR"] for rule in rules] == [
        {"type": "Distinct", "value": "0.0.0.0/0"},
        {"type": "Distinct", "value": "::/0"},
    ]
    assert [rule["limit"] for rule in rules] == [
        {"requests": 50, "unit": "Second"},
        {"requests": 50, "unit": "Second"},
    ]
    assert all("burst" not in rule["limit"] for rule in rules)

    client_policies = [
        resource
        for resource in resources
        if resource.get("kind") == "ClientTrafficPolicy"
    ]
    tls_policy = next(
        resource
        for resource in client_policies
        if resource["metadata"]["name"].endswith("-tls-policy")
    )
    http_client_ip_policy = next(
        resource
        for resource in client_policies
        if "-cip-" in resource["metadata"]["name"]
    )
    assert tls_policy["spec"]["clientIPDetection"] == {"directSourceIP": {}}
    assert tls_policy["spec"]["tls"] == {"minVersion": "1.3"}
    assert {
        target["sectionName"] for target in http_client_ip_policy["spec"]["targetRefs"]
    } == {"http-0", "http-1"}
    assert http_client_ip_policy["spec"]["clientIPDetection"] == {"directSourceIP": {}}


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_renders_operator_selected_trusted_xff_mode() -> None:
    result = _render_gateway_template_isolated(
        client_ip_detection='{"xForwardedFor":{"numTrustedHops":2}}'
    )
    assert result.returncode == 0, result.stderr
    resources = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict)
    ]
    policies = [
        resource
        for resource in resources
        if resource.get("kind") == "ClientTrafficPolicy"
    ]
    assert len(policies) == 2
    assert all(
        policy["spec"]["clientIPDetection"] == {"xForwardedFor": {"numTrustedHops": 2}}
        for policy in policies
    )


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_renders_operator_selected_trusted_xff_cidrs_for_each_listener() -> (
    None
):
    selected_mode = {
        "xForwardedFor": {"trustedCIDRs": ["192.0.2.0/24", "2001:db8::/32"]}
    }
    result = _render_gateway_template_isolated(
        client_ip_detection=json.dumps(selected_mode, separators=(",", ":"))
    )
    assert result.returncode == 0, result.stderr
    policies = [
        resource
        for resource in yaml.safe_load_all(result.stdout)
        if isinstance(resource, dict) and resource.get("kind") == "ClientTrafficPolicy"
    ]
    assert len(policies) == 2
    https_policy = next(
        policy
        for policy in policies
        if policy["metadata"]["name"].endswith("-tls-policy")
    )
    http_policy = next(
        policy for policy in policies if "-cip-" in policy["metadata"]["name"]
    )
    assert https_policy["spec"]["clientIPDetection"] == selected_mode
    assert http_policy["spec"]["clientIPDetection"] == selected_mode
    assert {target["sectionName"] for target in https_policy["spec"]["targetRefs"]} == {
        "https-0",
        "https-1",
    }
    assert {target["sectionName"] for target in http_policy["spec"]["targetRefs"]} == {
        "http-0",
        "http-1",
    }
    assert all(
        target["kind"] == "Gateway" and target["group"] == "gateway.networking.k8s.io"
        for policy in policies
        for target in policy["spec"]["targetRefs"]
    )


def test_gateway_api_template_preserves_tls_redirect_and_route_dispatch() -> None:
    template = (CHART / "templates" / "gateway-api.yaml").read_text(encoding="utf-8")

    # Enabling the preview is intentionally blocked until its edge-limit
    # policies are enforceable; keep the dormant route template aligned with
    # the existing HTTPS and ingress path contracts in the meantime.
    assert "kind: Certificate" in template
    assert "secretName: {{ $tls.secretName }}" in template
    assert "name: {{ $root.Values.ingress.issuer.name }}" in template
    assert "dnsNames:" in template
    assert "kind: Gateway" in template
    assert "port: 80" in template
    assert "protocol: HTTP" in template
    assert "port: 443" in template
    assert "protocol: HTTPS" in template
    assert "mode: Terminate" in template
    assert 'minVersion: "1.3"' in template

    assert "range $hostIndex, $host := .Values.ingress.hosts" in template
    assert "range $path := $host.paths" in template
    assert (
        'type: {{ if eq $path.pathType "Exact" }}Exact{{ else }}PathPrefix{{ end }}'
        in template
    )
    assert 'name: {{ printf "%s-%s" $fullname $path.service }}' in template
    service_port_keys = {
        "backend": "backend",
        "gateway": "gateway",
        "frontend": "frontend",
        "ws-hub": "wsHub",
    }
    for service, values_key in service_port_keys.items():
        expected_mapping = (
            f'eq $path.service "{service}" '
            + "}}{{ "
            + f"$root.Values.{values_key}.service.port"
        )
        assert expected_mapping in template

    assert "kind: HTTPRoute" in template
    assert "sectionName: http-{{ $hostIndex }}" in template
    assert "type: RequestRedirect" in template
    assert "scheme: https" in template
    assert "statusCode: 301" in template


def test_gateway_api_blocker_matches_the_retained_ingress_limit_contract() -> None:
    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    annotations = values["ingress"]["annotations"]
    assert annotations == {
        "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        "nginx.ingress.kubernetes.io/ssl-protocols": "TLSv1.3",
        "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
        "nginx.ingress.kubernetes.io/limit-rps": "50",
        "nginx.ingress.kubernetes.io/limit-burst-multiplier": "5",
        "nginx.ingress.kubernetes.io/limit-connections": "20",
    }

    validation = (CHART / "templates" / "validate-config.yaml").read_text(
        encoding="utf-8"
    )
    assert "gatewayApi.enabled is blocked" in validation
    assert "isolated /api/v1 HTTPRoute" in validation
    assert "concurrent-buffer memory budget" in validation
    assert "50 requests/second with 5x per-client burst" in validation
    assert "20 concurrent connections per client" in validation
    assert "local sourceCIDR Distinct rule rendered here" in validation
    assert "per Envoy proxy and per route" in validation
    assert "RateLimitValue has no burst field" in validation


def test_gateway_api_v19_buffer_memory_and_scope_limitations_are_documented() -> None:
    documentation = (CHART / "README.md").read_text(encoding="utf-8")

    assert "v1.9.2" in documentation
    assert "BackendTrafficPolicy.requestBuffer" in documentation
    assert "fully buffers each request" in documentation
    assert "concurrent-buffer memory budget" in documentation
    assert "sourceCIDR.type: Distinct" in documentation
    assert "gatewayApi.clientIPDetection" in documentation
    assert "do not establish the ingress-wide 50/250" in documentation
    assert "local-rate-limit" in documentation


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_network_policy_changes_keep_default_deny_and_narrow_peers() -> (
    None
):
    resources = _resources("--set", "ingress.enabled=true")
    policies = {
        resource["metadata"]["name"]: resource
        for resource in resources
        if resource.get("kind") == "NetworkPolicy"
    }
    default_deny = policies["gateway-contract-default-deny"]
    assert set(default_deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert (
        default_deny["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/instance"]
        == "gateway-contract"
    )

    values = yaml.safe_load((CHART / "values.yaml").read_text(encoding="utf-8"))
    expected_ports = {
        "gateway": 8080,
        "ws-hub": values["wsHub"]["service"]["port"],
        "backend": values["backend"]["service"]["port"],
        "frontend": values["frontend"]["service"]["port"],
    }
    for component, port in expected_ports.items():
        policy = policies[f"gateway-contract-{component}-policy"]
        controller_rules = [
            rule
            for rule in policy["spec"]["ingress"]
            if any(
                peer.get("namespaceSelector", {}).get("matchLabels", {})
                == {"kubernetes.io/metadata.name": "ingress-nginx"}
                and peer.get("podSelector", {})
                .get("matchLabels", {})
                .get("app.kubernetes.io/name")
                == "ingress-nginx"
                for peer in rule.get("from", [])
            )
        ]
        assert len(controller_rules) == 1
        assert controller_rules[0]["ports"] == [{"protocol": "TCP", "port": port}]

    # The Gateway API exception must stay limited to these four edge workloads,
    # use both operator-supplied selectors in one NetworkPolicy peer, and open
    # only each service's application port.
    network_policy_template = (CHART / "templates" / "network-policy.yaml").read_text(
        encoding="utf-8"
    )
    envoy_ingress_blocks = _conditional_bodies(
        network_policy_template, ".Values.gatewayApi.enabled"
    )
    assert len(envoy_ingress_blocks) == 4
    expected_port_templates = (
        "port: 8080",
        "port: {{ .Values.wsHub.service.port }}",
        "port: 8000",
        "port: {{ .Values.frontend.service.port }}",
    )
    for block, expected_port in zip(
        envoy_ingress_blocks, expected_port_templates, strict=True
    ):
        assert block.count("- from:") == 1
        assert block.count("namespaceSelector:") == 1
        assert block.count("podSelector:") == 1
        assert block.index("        - namespaceSelector:") < block.index(
            "          podSelector:"
        )
        assert ".Values.gatewayApi.networkPolicy.namespaceSelector" in block
        assert ".Values.gatewayApi.networkPolicy.podSelector" in block
        assert expected_port in block
        assert "to:" not in block


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_network_policy_replaces_the_legacy_ingress_peer() -> None:
    ingress_result = _render_network_policy_template_isolated(
        "--set", "ingress.enabled=true"
    )
    gateway_result = _render_network_policy_template_isolated(
        "--set",
        "ingress.enabled=false",
        "--set",
        "gatewayApi.enabled=true",
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
    )
    assert ingress_result.returncode == 0, ingress_result.stderr
    assert gateway_result.returncode == 0, gateway_result.stderr

    def policy_peers(
        rendered: str,
    ) -> dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
        resources = [
            resource
            for resource in yaml.safe_load_all(rendered)
            if isinstance(resource, dict)
        ]
        result: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
        for component in ("gateway", "ws-hub", "backend", "frontend"):
            policy = next(
                resource
                for resource in resources
                if resource.get("kind") == "NetworkPolicy"
                and resource["metadata"]["name"]
                == f"gateway-contract-{component}-policy"
            )
            ingress = policy["spec"].get("ingress") or []
            legacy = [
                peer
                for rule in ingress
                for peer in rule.get("from", [])
                if peer.get("namespaceSelector", {})
                .get("matchLabels", {})
                .get("kubernetes.io/metadata.name")
                == "ingress-nginx"
            ]
            envoy = [
                peer
                for rule in ingress
                for peer in rule.get("from", [])
                if peer.get("namespaceSelector", {})
                .get("matchLabels", {})
                .get("kubernetes.io/metadata.name")
                == "envoy-gateway-system"
            ]
            result[component] = (legacy, envoy)
        return result

    ingress_peers = policy_peers(ingress_result.stdout)
    gateway_peers = policy_peers(gateway_result.stdout)
    for component in ("gateway", "ws-hub", "backend", "frontend"):
        assert len(ingress_peers[component][0]) == 1
        assert ingress_peers[component][1] == []
        assert gateway_peers[component][0] == []
        assert len(gateway_peers[component][1]) == 1


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
@pytest.mark.parametrize(
    "client_ip_detection",
    [
        '{"directSourceIP":{}}',
        '{"xForwardedFor":{"trustedCIDRs":["192.0.2.0/24","2001:db8::/32"]}}',
    ],
    ids=("direct-source", "trusted-xff-cidrs"),
)
def test_gateway_api_fails_closed_until_per_client_policy_parity_is_implemented(
    client_ip_detection: str,
) -> None:
    result = _render(
        *_gateway_api_overrides(
            "--set",
            "ingress.enabled=false",
            "--set-json",
            f"gatewayApi.clientIPDetection={client_ip_detection}",
        )
    )

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert "clientIPDetection" not in result.stderr
    assert "isolated /api/v1 HTTPRoute" in result.stderr
    assert "concurrent-buffer memory budget" in result.stderr
    assert "50 requests/second with 5x per-client burst" in result.stderr
    assert "20 concurrent connections per client" in result.stderr
    assert "source-CIDR" in result.stderr
    assert "requestBuffer" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_requires_proxy_selectors_and_is_exclusive_with_ingress() -> None:
    missing_selectors = _render(
        "--set",
        "gatewayApi.enabled=true",
        "--set",
        "ingress.enabled=false",
    )
    both_controllers = _render(*_gateway_api_overrides("--set", "ingress.enabled=true"))

    assert missing_selectors.returncode != 0
    assert "gatewayApi.networkPolicy namespaceSelector and podSelector" in (
        missing_selectors.stderr
    )
    assert both_controllers.returncode != 0
    assert "gatewayApi.enabled and ingress.enabled cannot both be true" in (
        both_controllers.stderr
    )


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_requires_operator_selected_client_ip_detection() -> None:
    result = _render(
        "--set",
        "gatewayApi.enabled=true",
        "--set",
        "ingress.enabled=false",
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
    )

    assert result.returncode != 0
    assert "gatewayApi.clientIPDetection must select exactly one" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_schema_rejects_conflicting_client_ip_modes() -> None:
    result = _render(
        "--set-json",
        'gatewayApi.clientIPDetection={"directSourceIP":{},"xForwardedFor":{"numTrustedHops":1}}',
    )

    assert result.returncode != 0
    assert "clientIPDetection" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
@pytest.mark.parametrize(
    "client_ip_detection",
    [
        '{"xForwardedFor":{"numTrustedHops":2,"trustedCIDRs":["192.0.2.0/24"]}}',
        '{"xForwardedFor":{}}',
    ],
    ids=("hops-and-cidrs", "empty-x-forwarded-for"),
)
def test_gateway_api_schema_rejects_ambiguous_or_empty_xff_configuration(
    client_ip_detection: str,
) -> None:
    result = _render(
        "--set-json", f"gatewayApi.clientIPDetection={client_ip_detection}"
    )

    assert result.returncode != 0
    assert "clientIPDetection" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_rejects_ingress_only_path_types() -> None:
    result = _render(
        *_gateway_api_overrides(
            "--set",
            "ingress.enabled=false",
            "--set-string",
            "ingress.hosts[0].host=university.example.com",
            "--set-string",
            "ingress.hosts[0].paths[0].path=/",
            "--set-string",
            "ingress.hosts[0].paths[0].service=frontend",
            "--set-string",
            "ingress.hosts[0].paths[0].pathType=ImplementationSpecific",
        )
    )

    assert result.returncode != 0
    assert "supports only Exact and Prefix ingress pathTypes" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_requires_its_controller_crds() -> None:
    result = _render(
        *_gateway_api_overrides("--set", "ingress.enabled=false"),
        with_apis=False,
    )

    assert result.returncode != 0
    assert "Gateway API and Envoy Gateway CRDs must be installed" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_requires_backend_traffic_policy_crd_for_request_buffer() -> None:
    result = _render(
        *_gateway_api_overrides("--set", "ingress.enabled=false"),
        omitted_apis=("gateway.envoyproxy.io/v1alpha1/BackendTrafficPolicy",),
    )

    assert result.returncode != 0
    assert "Gateway API and Envoy Gateway CRDs must be installed" in result.stderr


def test_gateway_api_values_schema_is_typed_and_closed() -> None:
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    gateway_api = schema["properties"]["gatewayApi"]
    assert gateway_api["additionalProperties"] is False
    assert gateway_api["required"] == [
        "enabled",
        "gatewayClassName",
        "clientIPDetection",
        "rateLimit",
        "requestBuffer",
        "networkPolicy",
    ]
    assert gateway_api["properties"]["enabled"]["type"] == "boolean"
    assert gateway_api["properties"]["clientIPDetection"]["maxProperties"] == 1
    assert gateway_api["properties"]["clientIPDetection"]["properties"].keys() == {
        "directSourceIP",
        "xForwardedFor",
    }
    assert gateway_api["properties"]["rateLimit"]["properties"]["requests"]["enum"] == [
        50
    ]
    assert "securityPolicyParityConfirmed" not in gateway_api["properties"]
    assert gateway_api["properties"]["requestBuffer"]["required"] == ["limit"]
    assert gateway_api["properties"]["requestBuffer"]["properties"]["limit"][
        "enum"
    ] == ["50Mi"]
    assert gateway_api["properties"]["networkPolicy"]["required"] == [
        "namespaceSelector",
        "podSelector",
    ]


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_rejects_body_limit_drift_from_ingress_contract() -> None:
    result = _render(
        "--set-string",
        "gatewayApi.requestBuffer.limit=60Mi",
    )

    assert result.returncode != 0
    assert "50Mi" in result.stderr


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_gateway_api_rejects_the_removed_self_attested_parity_toggle() -> None:
    result = _render(
        "--set",
        "gatewayApi.securityPolicyParityConfirmed=true",
    )

    assert result.returncode != 0
    assert "securityPolicyParityConfirmed" in result.stderr
