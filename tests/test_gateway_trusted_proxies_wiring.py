"""Contracts for explicit, fail-closed Gateway proxy trust configuration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "university-ecosystem"
HELM = shutil.which("helm")


class _ComposeLoader(yaml.SafeLoader):
    pass


def _construct_compose_tag(loader: _ComposeLoader, _tag: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_ComposeLoader.add_multi_constructor("!", _construct_compose_tag)


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.load(
        path.read_text(encoding="utf-8"),
        Loader=_ComposeLoader,  # noqa: S506 - SafeLoader constructs only YAML primitives
    )
    assert isinstance(loaded, dict)
    return loaded


def _helm() -> str:
    assert HELM is not None, "Helm-dependent tests must be marked at collection"
    return HELM


def _render_gateway_deployment(*overrides: str) -> dict[str, Any]:
    command = [
        _helm(),
        "template",
        "trusted-proxy-contract",
        str(CHART),
        "--namespace",
        "university-ecosystem",
        "--show-only",
        "templates/gateway-deployment.yaml",
        "--set-string",
        "applicationSecrets.existingSecret=trusted-proxy-contract-secret",
        "--set",
        "redis.enabled=false",
        "--set",
        "nats.enabled=false",
        *overrides,
    ]
    result = subprocess.run(  # noqa: S603 - fixed local Helm contract command
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    documents = [
        document
        for document in yaml.safe_load_all(result.stdout)
        if isinstance(document, dict) and document.get("kind") == "Deployment"
    ]
    assert len(documents) == 1
    return documents[0]


def _gateway_env(deployment: dict[str, Any]) -> dict[str, str]:
    containers = deployment["spec"]["template"]["spec"]["containers"]
    gateway = next(
        container for container in containers if container["name"] == "gateway"
    )
    return {entry["name"]: entry.get("value", "") for entry in gateway["env"]}


@pytest.mark.parametrize(
    "compose_file", ["docker-compose.full.yml", "docker-compose.go.yml"]
)
def test_compose_gateway_trusted_proxy_setting_defaults_empty_and_is_operator_supplied(
    compose_file: str,
) -> None:
    compose = _load_yaml(ROOT / compose_file)
    environment = compose["services"]["gateway"]["environment"]

    assert environment["GATEWAY_TRUSTED_PROXIES"] == "${GATEWAY_TRUSTED_PROXIES:-}"


@pytest.mark.parametrize(
    "compose_file", ["docker-compose.full.yml", "docker-compose.go.yml"]
)
def test_compose_gateway_requires_the_identity_assertion_secret(
    compose_file: str,
) -> None:
    compose = _load_yaml(ROOT / compose_file)
    environment = compose["services"]["gateway"]["environment"]

    assert environment["INTERNAL_HMAC_SECRET"].startswith("${INTERNAL_HMAC_SECRET:?")


def test_live_overlay_inherits_gateway_trust_setting_without_replacing_it() -> None:
    overlay = _load_yaml(ROOT / "docker-compose.live.yml")

    assert "GATEWAY_TRUSTED_PROXIES" not in overlay["services"]["gateway"].get(
        "environment", {}
    )


def test_helm_gateway_proxy_trust_is_typed_and_empty_by_default() -> None:
    values = _load_yaml(CHART / "values.yaml")
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))
    trusted_proxies = schema["properties"]["gateway"]["properties"]["config"][
        "properties"
    ]["trustedProxies"]

    assert values["gateway"]["config"]["trustedProxies"] == []
    assert trusted_proxies["type"] == "array"
    assert trusted_proxies["items"] == {"type": "string", "minLength": 1}


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_helm_gateway_proxy_trust_renders_empty_without_operator_input() -> None:
    deployment = _render_gateway_deployment()

    assert _gateway_env(deployment)["GATEWAY_TRUSTED_PROXIES"] == ""


@pytest.mark.skipif(HELM is None, reason="Helm is not installed")
def test_helm_gateway_proxy_trust_renders_only_explicit_operator_entries() -> None:
    # Documentation-only ranges make clear these are fixtures, not defaults.
    deployment = _render_gateway_deployment(
        "--set-string",
        "gateway.config.trustedProxies[0]=198.51.100.0/28",
        "--set-string",
        "gateway.config.trustedProxies[1]=203.0.113.11",
    )

    assert (
        _gateway_env(deployment)["GATEWAY_TRUSTED_PROXIES"]
        == "198.51.100.0/28,203.0.113.11"
    )
