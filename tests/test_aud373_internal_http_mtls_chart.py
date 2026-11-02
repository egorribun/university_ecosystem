"""AUD-373: Helm contract for SPIFFE mTLS on token-bearing backend HTTP hops."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

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

    backend = _deployment(resources, "-backend")
    backend_container = _main_container(backend)
    backend_env = _env(backend_container)
    assert backend_env["INTERNAL_HTTP_MTLS_ENABLED"] == "true"
    assert (
        backend_env["INTERNAL_HTTP_MTLS_CERT_FILE"]
        == "/run/secrets/internal-http-mtls/tls.crt"
    )
    assert (
        backend_env["INTERNAL_HTTP_MTLS_KEY_FILE"]
        == "/run/secrets/internal-http-mtls/tls.key"
    )
    assert (
        backend_env["INTERNAL_HTTP_MTLS_CA_FILE"]
        == "/run/secrets/internal-http-mtls/ca.crt"
    )
    assert (
        backend_env["GUNICORN_CMD_ARGS"] == "--config=python:app.server.gunicorn_conf"
    )
    mounts = {
        item["name"]: item["mountPath"] for item in backend_container["volumeMounts"]
    }
    assert mounts["internal-http-mtls"] == "/run/secrets/internal-http-mtls"
    secret_volume = _volume(backend, "internal-http-mtls")
    assert secret_volume is not None
    assert (
        secret_volume["secret"]["secretName"]
        == staging["backendServer"]["existingSecret"]
    )
    assert {item["path"] for item in secret_volume["secret"]["items"]} == {
        "tls.crt",
        "tls.key",
        "ca.crt",
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
    assert _env(_main_container(file_processor))["FP_JWKS_URL"].startswith("https://")


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
            "internalHttpMTLS.backendServer.existingSecret=",
            "internalHttpMTLS.backendServer.existingSecret is required",
        ),
        ("internalHttpMTLS.trustDomain=", "internalHttpMTLS.trustDomain is required"),
    ],
)
def test_flag_on_requires_identities_and_backend_secret(
    override: str, message: str
) -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(*_enabled_args("--set", override))

    assert message in error.value.stderr


def test_values_schema_rejects_unknown_internal_http_mtls_keys() -> None:
    with pytest.raises(subprocess.CalledProcessError) as error:
        _render_staging(*_enabled_args("--set", "internalHttpMTLS.unexpected=true"))

    assert "unexpected" in error.value.stderr
