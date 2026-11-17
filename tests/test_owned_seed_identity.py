"""Source and pure-function contracts for explicit owned-live tenant routing."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
import yaml
from yaml.nodes import MappingNode, Node, ScalarNode

from scripts import live_stand
from scripts.seed_identity import owned_seed_tenant_id

PROJECT = "ue-live-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[1]


def _yaml_mapping(node: Node) -> dict[str, Node]:
    assert isinstance(node, MappingNode)
    result: dict[str, Node] = {}
    for key, value in node.value:
        assert isinstance(key, ScalarNode)
        assert key.value not in result
        result[key.value] = value
    return result


def test_live_overlay_binds_owned_tenant_to_backend_and_workers() -> None:
    document = yaml.compose(
        (ROOT / "docker-compose.live.yml").read_text(encoding="utf-8")
    )
    assert document is not None
    services = _yaml_mapping(_yaml_mapping(document)["services"])
    backend_environment = _yaml_mapping(services["backend"])["environment"]
    tenant = _yaml_mapping(backend_environment)["MVP_TENANT_ID"]
    assert isinstance(tenant, ScalarNode)
    assert tenant.value == "${MVP_TENANT_ID:?set by scripts/live_stand.py}"
    for worker in ("outbox-worker", "notifications-worker"):
        assert _yaml_mapping(services[worker])["environment"] is backend_environment
    injected = {
        name
        for name, service in services.items()
        if isinstance(
            environment := _yaml_mapping(service).get("environment"), MappingNode
        )
        and "MVP_TENANT_ID" in _yaml_mapping(environment)
    }
    assert injected == {"backend", "outbox-worker", "notifications-worker"}


def test_owned_environment_pins_explicit_tenant(monkeypatch) -> None:
    monkeypatch.delenv("MVP_TENANT_ID", raising=False)
    environment = live_stand.stand_environment(
        {"public": "public", "private": "private"}, PROJECT
    )
    assert environment["MVP_TENANT_ID"] == str(owned_seed_tenant_id(PROJECT))
    assert owned_seed_tenant_id(PROJECT) == uuid5(
        NAMESPACE_URL, f"urn:university-ecosystem:owned-seed:{PROJECT}"
    )


@pytest.mark.parametrize(
    "value", ["", "invalid", "00000000-0000-4000-8000-000000000001"]
)
def test_owned_environment_rejects_ambient_tenant_mismatch(monkeypatch, value) -> None:
    monkeypatch.setenv("MVP_TENANT_ID", value)
    with pytest.raises(live_stand.StandError, match="MVP_TENANT_ID"):
        live_stand.stand_environment(
            {"public": "public", "private": "private"}, PROJECT
        )


def test_owned_environment_accepts_matching_explicit_tenant(monkeypatch) -> None:
    expected = str(owned_seed_tenant_id(PROJECT))
    monkeypatch.setenv("MVP_TENANT_ID", expected)
    assert (
        live_stand.stand_environment(
            {"public": "public", "private": "private"}, PROJECT
        )["MVP_TENANT_ID"]
        == expected
    )


def test_launcher_persists_owned_identity_before_worker_environment_and_start() -> None:
    script = (ROOT / "start-docker.ps1").read_text()
    function = script.split("function Ensure-OwnedLiveTenantEnvironment {", 1)[1].split(
        "\nfunction ", 1
    )[0]
    assert '$ExtraCompose[0] -cne "docker-compose.live.yml"' in function
    assert "$owner.project_name -cne $project" in function
    assert "Get-OwnedSeedTenantId" in function
    assert 'throw "Owned live MVP_TENANT_ID' in function
    assert "foreach ($path in @($EnvFile, $EnvCompose))" in function
    tenant_initialization = script.index("\nEnsure-OwnedLiveTenantEnvironment\n")
    worker_environment = script.index("\nWrite-WorkerEnvironmentFile\n")
    assert tenant_initialization < worker_environment
    for startup in (
        "docker compose @ComposeArgs --env-file $EnvFile up --wait --wait-timeout 300 temporal",
        "docker compose @ComposeArgs --env-file $EnvFile up -d @liveAcceptanceRootArgs",
        "docker compose @ComposeArgs --env-file $EnvFile up -d $CoreBootstrapServices",
        "\n    docker compose @ComposeArgs --env-file $EnvFile up -d\n",
    ):
        assert worker_environment < script.index(startup)
