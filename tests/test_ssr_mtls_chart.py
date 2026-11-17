"""SSR must reach the backend without weakening the SPIFFE boundary."""

import subprocess

import pytest

from tests.test_aud373_internal_http_mtls_chart import (
    SPIFFE_SOCKET,
    _deployment,
    _enabled_args,
    _env,
    _pod_spec,
)
from tests.test_helm_staging_contract import STAGING_VALUES, _render_staging, _values


def test_frontend_mtls_uses_an_isolated_loopback_proxy() -> None:
    resources = _render_staging(*_enabled_args())
    frontend = _deployment(resources, "-frontend")
    pod = _pod_spec(frontend)
    containers = {item["name"]: item for item in pod["containers"]}
    assert set(containers) == {"frontend", "ssr-proxy"}
    assert frontend["metadata"]["namespace"] == "university-ecosystem"
    assert _env(containers["frontend"])["BACKEND_ORIGIN"] == "http://127.0.0.1:18000"
    assert all(
        item["name"] != "spiffe-workload-api"
        for item in containers["frontend"]["volumeMounts"]
    )
    proxy = containers["ssr-proxy"]
    assert proxy["command"] == ["/ssr-proxy"]
    assert "ports" not in proxy
    assert proxy["securityContext"]["readOnlyRootFilesystem"] is True
    assert proxy["securityContext"]["allowPrivilegeEscalation"] is False
    assert proxy["securityContext"]["capabilities"]["drop"] == ["ALL"]
    identities = _values(STAGING_VALUES)["internalHttpMTLS"]
    assert _env(proxy) == {
        "SSR_MTLS_ENABLED": "true",
        "SSR_BACKEND_ORIGIN": "https://staging-contract-backend:8000",
        "SSR_SPIFFE_ID": identities["frontendSpiffeID"],
        "SSR_BACKEND_SPIFFE_ID": identities["backendSpiffeID"],
        "SSR_SPIFFE_TRUST_DOMAIN": identities["trustDomain"],
        "SPIFFE_ENDPOINT_SOCKET": SPIFFE_SOCKET,
    }
    assert proxy["volumeMounts"] == [
        {
            "name": "spiffe-workload-api",
            "mountPath": "/spiffe-workload-api",
            "readOnly": True,
        }
    ]
    for name in ("startupProbe", "readinessProbe"):
        assert proxy[name]["exec"]["command"] == ["/ssr-proxy", "probe"]
    gateway = _deployment(resources, "-gateway")
    assert proxy["image"] == _pod_spec(gateway)["containers"][0]["image"]
    backend = _deployment(resources, "-backend")
    allowed = _env(_pod_spec(backend)["containers"][0])[
        "INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS"
    ].split(",")
    assert allowed.count(identities["frontendSpiffeID"]) == 1


def test_frontend_plaintext_profile_has_no_identity_or_proxy() -> None:
    frontend = _deployment(_render_staging(), "-frontend")
    pod = _pod_spec(frontend)
    assert [item["name"] for item in pod["containers"]] == ["frontend"]
    assert _env(pod["containers"][0])["BACKEND_ORIGIN"].startswith("http://")
    assert all(item["name"] != "spiffe-workload-api" for item in pod["volumes"])


@pytest.mark.parametrize("enabled", [False, True])
def test_backend_admits_only_same_release_frontend_on_its_port(enabled: bool) -> None:
    resources = _render_staging(
        "--set", f"internalHttpMTLS.enabled={str(enabled).lower()}"
    )
    backend = next(
        item for item in resources
        if item["kind"] == "NetworkPolicy"
        and item["metadata"]["name"].endswith("-backend-policy")
    )
    rules = [
        rule for rule in backend["spec"]["ingress"]
        if any(
            peer.get("podSelector", {}).get("matchLabels", {}).get(
                "app.kubernetes.io/component"
            ) == "frontend"
            for peer in rule.get("from", [])
        )
    ]
    assert len(rules) == 1
    assert rules[0]["ports"] == [{"protocol": "TCP", "port": 8000}]
    assert rules[0]["from"] == [{
        "podSelector": {"matchLabels": {
            "app.kubernetes.io/name": "university-ecosystem",
            "app.kubernetes.io/instance": "staging-contract",
            "app.kubernetes.io/component": "frontend",
        }}
    }]


@pytest.mark.parametrize("identity", ["", "not-an-identity"])
def test_mtls_requires_a_valid_frontend_identity(identity: str) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        _render_staging(*_enabled_args(
            "--set-string", f"internalHttpMTLS.frontendSpiffeID={identity}"
        ))
