"""AUD-373: Helm contract for SPIFFE mTLS on token-bearing backend HTTP hops."""

from __future__ import annotations

import subprocess
from typing import Any
from uuid import UUID

import pytest

from scripts.plan_spire_registration import build_plan
from tests.test_helm_staging_contract import (
    CHART,
    STAGING_VALUES,
    _render_staging,
    _values,
)

SPIFFE_SOCKET = "unix:///spiffe-workload-api/agent.sock"


def _deployment(resources: list[dict[str, Any]], name_suffix: str) -> dict[str, Any]:
    matches = [
        resource
        for resource in resources
        if resource["kind"] == "Deployment"
        and resource["metadata"]["name"].endswith(name_suffix)
    ]
    assert len(matches) == 1, name_suffix
    return matches[0]


def _pod_spec(deployment: dict[str, Any]) -> dict[str, Any]:
    return deployment["spec"]["template"]["spec"]


def _main_container(deployment: dict[str, Any]) -> dict[str, Any]:
    containers = _pod_spec(deployment)["containers"]
    assert len(containers) == 1
    return containers[0]


def _env(container: dict[str, Any]) -> dict[str, str]:
    return {item["name"]: item.get("value", "") for item in container.get("env", [])}


def _volume(deployment: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next(
        (item for item in _pod_spec(deployment)["volumes"] if item["name"] == name),
        None,
    )


def _backend_route_overrides() -> list[str]:
    """Route the public /static and /.well-known paths through the gateway instead of the backend Service."""
    overrides: list[str] = []
    for host_index, host in enumerate(_values(STAGING_VALUES)["ingress"]["hosts"]):
        for path_index, path in enumerate(host["paths"]):
            if path["service"] == "backend":
                overrides.extend(
                    [
                        "--set",
                        f"ingress.hosts[{host_index}].paths[{path_index}].service=gateway",
                    ]
                )
    return overrides


def _enabled_args(*extra: str) -> list[str]:
    return [
        "--set",
        "internalHttpMTLS.enabled=true",
        *_backend_route_overrides(),
        *extra,
    ]


def test_chart_default_keeps_mtls_disabled() -> None:
    values = _values(CHART / "values.yaml")

    assert values["internalHttpMTLS"]["enabled"] is False


def test_flag_off_keeps_plaintext_backend_contract() -> None:
    resources = _render_staging()

    backend = _deployment(resources, "-backend")
    container = _main_container(backend)
    assert container["startupProbe"]["httpGet"]["path"] == "/health/ready"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert "exec" not in container["readinessProbe"]
    assert "GUNICORN_CMD_ARGS" not in _env(container)
    assert _volume(backend, "internal-http-mtls") is None

    gateway_env = _env(_main_container(_deployment(resources, "-gateway")))
    assert gateway_env["BACKEND_URL"].startswith("http://")
    assert "INTERNAL_HTTP_MTLS_ENABLED" not in gateway_env
    ws_hub_env = _env(_main_container(_deployment(resources, "-ws-hub")))
    assert ws_hub_env["BACKEND_INTERNAL_URL"].startswith("http://")
    assert "SPIFFE_ENABLED" not in ws_hub_env


def test_flag_on_is_refused_while_public_routes_target_the_plaintext_backend() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging("--set", "internalHttpMTLS.enabled=true")

    assert "targets the backend Service" in error.value.stderr


def test_flag_on_wires_backend_listener_probes_and_spiffe_clients() -> None:
    resources = _render_staging(*_enabled_args())
    staging = _values(STAGING_VALUES)["internalHttpMTLS"]
    for suffix in ("-backend", "-gateway", "-ws-hub", "-file-processor"):
        assert _deployment(resources, suffix)["metadata"]["namespace"] == (
            "university-ecosystem"
        )

    backend = _deployment(resources, "-backend")
    backend_container = _main_container(backend)
    backend_env = _env(backend_container)
    assert backend_env["INTERNAL_HTTP_MTLS_ENABLED"] == "true"
    assert (
        backend_env["INTERNAL_HTTP_MTLS_SERVER_SPIFFE_ID"] == staging["backendSpiffeID"]
    )
    assert set(
        backend_env["INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"].split(",")
    ) == {
        staging["backendSpiffeID"],
        staging["gatewaySpiffeID"],
        staging["wsHubSpiffeID"],
        staging["fileProcessorSpiffeID"],
    }
    assert backend_env["SPIFFE_ENDPOINT_SOCKET"] == SPIFFE_SOCKET
    assert "INTERNAL_HTTP_MTLS_CERT_FILE" not in backend_env
    assert "GUNICORN_CMD_ARGS" not in backend_env
    mounts = {item["name"]: item for item in backend_container["volumeMounts"]}
    assert mounts["spiffe-workload-api"]["mountPath"] == "/spiffe-workload-api"
    assert mounts["spiffe-workload-api"]["readOnly"] is True
    assert _volume(backend, "internal-http-mtls") is None
    assert _volume(backend, "spiffe-workload-api") == {
        "name": "spiffe-workload-api",
        "csi": {"driver": "csi.spiffe.io", "readOnly": True},
    }
    for probe_name in ("startupProbe", "livenessProbe", "readinessProbe"):
        probe = backend_container[probe_name]
        assert "httpGet" not in probe, probe_name
        assert probe["exec"]["command"][:4] == [
            "python",
            "-m",
            "app.server.internal_mtls",
            "probe",
        ]
        assert probe["exec"]["command"][-2:] == ["--port", "8000"]
    assert backend_container["readinessProbe"]["timeoutSeconds"] == 5

    gateway = _deployment(resources, "-gateway")
    gateway_container = _main_container(gateway)
    gateway_env = _env(gateway_container)
    assert gateway_env["BACKEND_URL"] == "https://university-ecosystem-backend:8000"
    assert gateway_env["INTERNAL_HTTP_MTLS_ENABLED"] == "true"
    assert gateway_env["BACKEND_SPIFFE_ID"] == staging["backendSpiffeID"]
    assert gateway_env["SPIFFE_ENDPOINT_SOCKET"] == SPIFFE_SOCKET
    assert gateway_env["SPIFFE_MY_ID"] == staging["gatewaySpiffeID"]
    assert "SPIFFE_ENABLED" not in gateway_env, (
        "gRPC file-processor transport must keep its own contract"
    )
    assert gateway_env["JWKS_ENDPOINT"].startswith("https://")
    socket_volume = _volume(gateway, "spiffe-workload-api")
    assert socket_volume == {
        "name": "spiffe-workload-api",
        "csi": {"driver": "csi.spiffe.io", "readOnly": True},
    }
    gateway_mounts = {item["name"]: item for item in gateway_container["volumeMounts"]}
    assert gateway_mounts["spiffe-workload-api"]["mountPath"] == "/spiffe-workload-api"
    assert gateway_mounts["spiffe-workload-api"]["readOnly"] is True

    ws_hub = _deployment(resources, "-ws-hub")
    ws_hub_env = _env(_main_container(ws_hub))
    assert (
        ws_hub_env["BACKEND_INTERNAL_URL"]
        == "https://university-ecosystem-backend:8000"
    )
    assert (
        ws_hub_env["JWKS_URL"]
        == "https://university-ecosystem-backend:8000/.well-known/jwks.json"
    )
    assert ws_hub_env["SPIFFE_ENABLED"] == "true"
    assert ws_hub_env["SPIFFE_ENDPOINT_SOCKET"] == SPIFFE_SOCKET
    assert ws_hub_env["SPIFFE_MY_ID"] == staging["wsHubSpiffeID"]
    assert ws_hub_env["BACKEND_SPIFFE_ID"] == staging["backendSpiffeID"]
    assert _volume(ws_hub, "spiffe-workload-api") is not None

    file_processor = _deployment(resources, "-file-processor")
    fp_container = _main_container(file_processor)
    fp_env = _env(fp_container)
    assert fp_env["FP_JWKS_URL"].startswith("https://")
    assert fp_env["FP_INTERNAL_HTTP_MTLS_ENABLED"] == "true"
    assert fp_env["FP_BACKEND_SPIFFE_ID"] == staging["backendSpiffeID"]
    assert fp_env["FP_SPIFFE_MY_ID"] == staging["fileProcessorSpiffeID"]
    assert fp_env["FP_SPIFFE_ENDPOINT_SOCKET"] == SPIFFE_SOCKET
    assert "FP_SPIFFE_ENABLED" not in fp_env
    assert _volume(file_processor, "spiffe-workload-api") == socket_volume
    for name in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert fp_container[name]["tcpSocket"] == {"port": "grpc"}


def test_public_jwks_override_does_not_receive_internal_workload_identity() -> None:
    endpoint = "https://issuer.example/.well-known/jwks.json"
    resources = _render_staging(
        *_enabled_args("--set", f"fileProcessor.config.jwksURL={endpoint}")
    )
    processor = _deployment(resources, "-file-processor")
    environ = _env(_main_container(processor))
    assert environ["FP_JWKS_URL"] == endpoint
    assert "FP_INTERNAL_HTTP_MTLS_ENABLED" not in environ
    assert "FP_SPIFFE_ENABLED" not in environ
    assert _volume(processor, "spiffe-workload-api") is None
    backend = _deployment(resources, "-backend")
    allowed = _env(_main_container(backend))[
        "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"
    ].split(",")
    staging = _values(STAGING_VALUES)["internalHttpMTLS"]
    assert set(allowed) == {
        staging["backendSpiffeID"],
        staging["gatewaySpiffeID"],
        staging["wsHubSpiffeID"],
    }


def test_explicit_internal_jwks_preserves_exact_tcp_network_policy() -> None:
    endpoint = "https://university-ecosystem-backend:8000/.well-known/jwks.json"
    resources = _render_staging(
        *_enabled_args("--set", f"fileProcessor.config.jwksURL={endpoint}"),
        release_name="university-ecosystem",
    )
    processor = _deployment(resources, "-file-processor")
    assert _env(_main_container(processor))["FP_INTERNAL_HTTP_MTLS_ENABLED"] == "true"
    policies = {
        resource["metadata"]["name"]: resource["spec"]
        for resource in resources
        if resource["kind"] == "NetworkPolicy"
    }
    rules = policies["university-ecosystem-file-processor-policy"]["egress"]
    backend_rules = [
        rule
        for rule in rules
        if any(
            peer.get("podSelector", {})
            .get("matchLabels", {})
            .get("app.kubernetes.io/component")
            == "backend"
            for peer in rule.get("to", [])
        )
    ]
    assert len(backend_rules) == 1
    assert backend_rules[0]["ports"] == [{"protocol": "TCP", "port": 8000}]
    assert (
        backend_rules[0]["to"][0]["podSelector"]["matchLabels"][
            "app.kubernetes.io/instance"
        ]
        == "university-ecosystem"
    )


def test_disabled_optional_workloads_receive_no_backend_identity_authority() -> None:
    resources = _render_staging(
        *_enabled_args(
            "--set",
            "global.environment=development",
            "--set",
            "wsHub.enabled=false",
            "--set",
            "fileProcessor.enabled=false",
        )
    )
    backend = _deployment(resources, "-backend")
    allowed = _env(_main_container(backend))[
        "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"
    ].split(",")
    staging = _values(STAGING_VALUES)["internalHttpMTLS"]
    assert set(allowed) == {
        staging["backendSpiffeID"],
        staging["gatewaySpiffeID"],
    }


@pytest.mark.parametrize(
    ("overrides", "components"),
    [
        ((), {"backend", "gateway", "ws-hub", "file-processor"}),
        (
            ("--set", "fileProcessor.config.jwksURL=https://issuer.example/jwks"),
            {"backend", "gateway", "ws-hub"},
        ),
        (
            (
                "--set",
                "global.environment=development",
                "--set",
                "wsHub.enabled=false",
                "--set",
                "fileProcessor.enabled=false",
            ),
            {"backend", "gateway"},
        ),
    ],
)
def test_rendered_workloads_produce_only_exact_active_registration_entries(
    overrides: tuple[str, ...], components: set[str]
) -> None:
    resources = _render_staging(*_enabled_args(*overrides))
    parent = (
        "spiffe://university.ecosystem/spire/agent/k8s_psat/"
        f"university-cluster/{UUID(int=1)}"
    )
    plan = build_plan(
        resources,
        namespace="university-ecosystem",
        release="staging-contract",
        parent_id=parent,
    )
    assert plan["mode"] == "plan-only"
    assert {entry["component"] for entry in plan["entries"]} == components
    for entry in plan["entries"]:
        workload = _deployment(resources, f"-{entry['component']}")
        assert entry["service_account"] == _pod_spec(workload)["serviceAccountName"]
        assert entry["namespace"] == workload["metadata"]["namespace"]
        assert entry["argv"][3:5] == ["-parentID", parent]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        # Malformed identifiers are rejected by values.schema.json before templating runs,
        # so the assertion names the offending JSON pointer rather than the template message.
        (
            "internalHttpMTLS.gatewaySpiffeID=not-a-spiffe-id",
            "/internalHttpMTLS/gatewaySpiffeID",
        ),
        (
            "internalHttpMTLS.backendSpiffeID=spiffe://university.ecosystem/ns/x/sa/app/extra/../",
            "/internalHttpMTLS/backendSpiffeID",
        ),
        (
            "internalHttpMTLS.workloadAPI.csiDriver=",
            "/internalHttpMTLS/workloadAPI/csiDriver",
        ),
        ("internalHttpMTLS.trustDomain=", "internalHttpMTLS.trustDomain is required"),
        (
            "internalHttpMTLS.fileProcessorSpiffeID=",
            "internalHttpMTLS.fileProcessorSpiffeID must be a canonical SPIFFE ID",
        ),
    ],
)
def test_flag_on_requires_identities_and_workload_api(
    override: str, message: str
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(*_enabled_args("--set", override))

    assert message in error.value.stderr


def test_values_schema_rejects_unknown_internal_http_mtls_keys() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(*_enabled_args("--set", "internalHttpMTLS.unexpected=true"))

    assert "unexpected" in error.value.stderr
