"""Render origin wiring without treating the dormant Gateway preview as deployable."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.test_gateway_api_helm_contract import CHART, HELM, _render

pytestmark = pytest.mark.skipif(HELM is None, reason="Helm is not installed")
ORIGIN_VARIABLES = ("APP_BASE_URL", "FRONTEND_ORIGIN", "FRONTEND_ORIGINS")
EDGE_MODES = ((True, False), (False, True), (False, False))


@pytest.fixture
def origin_consumers_chart(tmp_path: Path) -> Path:
    """Copy shipped origin consumers; never remove the real chart's release gate.

    This renders only the backend/Gateway Deployments, exact helpers and values/schema.
    It proves environment-variable wiring, not whole-chart acceptance or CORS
    behavior of a running backend. Full-chart activation remains blocked below.
    """
    templates = tmp_path / "templates"
    templates.mkdir()
    (tmp_path / "Chart.yaml").write_text(
        'apiVersion: v2\nname: university-ecosystem\nversion: 0.1.0\nappVersion: "1.0.0"\n',
        encoding="utf-8",
    )
    for name in ("values.yaml", "values.schema.json"):
        shutil.copy2(CHART / name, tmp_path / name)
    for name in (
        "_helpers.tpl",
        "_secret-volumes.tpl",
        "backend-deployment.yaml",
        "gateway-deployment.yaml",
    ):
        shutil.copy2(CHART / "templates" / name, templates / name)
    return tmp_path


def _origin_env(chart: Path, *overrides: str) -> dict[str, str]:
    result = _render(*overrides, chart=chart)
    assert result.returncode == 0, result.stderr
    deployments = list(yaml.safe_load_all(result.stdout))
    assert len(deployments) == 2
    assert {
        item["metadata"]["labels"]["app.kubernetes.io/component"]
        for item in deployments
    } == {"backend", "gateway"}
    origin_env = []
    for deployment in deployments:
        assert deployment["kind"] == "Deployment"
        component = deployment["metadata"]["labels"]["app.kubernetes.io/component"]
        containers = deployment["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 1
        assert containers[0]["name"] == component
        component_origins = [
            item
            for item in containers[0]["env"]
            if item["name"] in (*ORIGIN_VARIABLES, "ALLOWED_ORIGINS")
        ]
        expected_names = (
            ORIGIN_VARIABLES if component == "backend" else ("ALLOWED_ORIGINS",)
        )
        assert all(item["name"] in expected_names for item in component_origins)
        origin_env.extend(component_origins)
    assert len({item["name"] for item in origin_env}) == len(origin_env)
    return {item["name"]: item["value"] for item in origin_env}


def _edge_overrides(ingress: bool, gateway: bool) -> tuple[str, ...]:
    return (
        "--set",
        f"ingress.enabled={str(ingress).lower()}",
        "--set",
        f"gatewayApi.enabled={str(gateway).lower()}",
    )


@pytest.mark.parametrize(("ingress", "gateway"), EDGE_MODES[:2])
@pytest.mark.parametrize(
    "hosts",
    (
        None,
        ("frontend.example.test", "api.example.test"),
        ("second.example.test", "first.example.test"),
    ),
)
def test_public_edge_derives_origin_from_first_host(
    origin_consumers_chart: Path,
    ingress: bool,
    gateway: bool,
    hosts: tuple[str, str] | None,
) -> None:
    overrides = list(_edge_overrides(ingress, gateway))
    expected = "https://university.example.com"
    if hosts is not None:
        host_values = [
            {
                "host": host,
                "paths": [{"path": "/", "pathType": "Prefix", "service": "gateway"}],
            }
            for host in hosts
        ]
        overrides.extend(("--set-json", f"ingress.hosts={json.dumps(host_values)}"))
        expected = f"https://{hosts[0]}"

    assert _origin_env(origin_consumers_chart, *overrides) == dict.fromkeys(
        (*ORIGIN_VARIABLES, "ALLOWED_ORIGINS"), expected
    )


@pytest.mark.parametrize(("ingress", "gateway"), EDGE_MODES)
@pytest.mark.parametrize(
    "explicit", ("https://explicit.example.test", "https://explicit.example.test/")
)
@pytest.mark.parametrize("empty_hosts", (False, True))
def test_explicit_origin_keeps_precedence_and_trailing_slash_behavior(
    origin_consumers_chart: Path,
    ingress: bool,
    gateway: bool,
    explicit: str,
    empty_hosts: bool,
) -> None:
    hosts_override = ("--set-json", "ingress.hosts=[]") if empty_hosts else ()
    actual = _origin_env(
        origin_consumers_chart,
        *_edge_overrides(ingress, gateway),
        "--set-string",
        f"backend.config.frontendOrigin={explicit}",
        *hosts_override,
    )
    assert actual == dict.fromkeys(
        (*ORIGIN_VARIABLES, "ALLOWED_ORIGINS"), "https://explicit.example.test"
    )


@pytest.mark.parametrize(("ingress", "gateway"), EDGE_MODES)
def test_empty_hosts_without_explicit_origin_remain_unset(
    origin_consumers_chart: Path, ingress: bool, gateway: bool
) -> None:
    assert _origin_env(
        origin_consumers_chart,
        *_edge_overrides(ingress, gateway),
        "--set-json",
        "ingress.hosts=[]",
    ) == {"ALLOWED_ORIGINS": ""}


def test_disabled_edges_do_not_derive_origin_from_remaining_hosts(
    origin_consumers_chart: Path,
) -> None:
    assert _origin_env(origin_consumers_chart, *_edge_overrides(False, False)) == {
        "ALLOWED_ORIGINS": ""
    }


@pytest.mark.parametrize("explicit", ("", "https://university.example.com/"))
def test_origin_preparation_preserves_full_chart_gateway_activation_block(
    explicit: str,
) -> None:
    overrides = [
        *_edge_overrides(False, True),
        "--set-string",
        f"backend.config.frontendOrigin={explicit}",
        "--set-json",
        'gatewayApi.clientIPDetection={"directSourceIP":{}}',
        "--set-string",
        r"gatewayApi.networkPolicy.namespaceSelector.kubernetes\.io/metadata\.name=envoy-gateway-system",
        "--set-string",
        r"gatewayApi.networkPolicy.podSelector.app\.kubernetes\.io/name=envoyproxy",
    ]
    result = _render(*overrides)

    assert result.returncode != 0
    assert "gatewayApi.enabled is blocked" in result.stderr
    assert "50 requests/second with 5x per-client burst" in result.stderr
    assert "20 concurrent connections per client" in result.stderr
    assert "concurrent-buffer memory budget" in result.stderr
