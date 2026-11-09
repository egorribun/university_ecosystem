"""Source and pure-function contracts for explicit owned-live tenant routing."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from scripts import live_stand
from scripts.seed_identity import owned_seed_tenant_id

PROJECT = "ue-live-0123456789abcdef"
ROOT = Path(__file__).resolve().parents[1]


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
    assert "$script:LiveStandOwner.project_name" in function
    assert "Get-OwnedSeedTenantId" in function
    assert 'throw "Owned live MVP_TENANT_ID' in function
    assert "foreach ($path in @($EnvFile, $EnvCompose))" in function
    assert script.index("\nEnsure-OwnedLiveTenantEnvironment\n") < script.index(
        "\nWrite-WorkerEnvironmentFile\n"
    )
