"""AUD-167: Compose must pass the selected edge peers to the WebSocket hub."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "compose_file", [ROOT / "docker-compose.full.yml", ROOT / "docker-compose.go.yml"]
)
def test_ws_hub_receives_explicit_proxy_peers_or_loopback_only_default(
    compose_file: Path,
) -> None:
    compose = yaml.safe_load(
        compose_file.read_text(encoding="utf-8")
        .replace("!override", "")
        .replace("!reset", "")
    )
    hub_environment = compose["services"]["ws-hub"]["environment"]

    assert hub_environment.get("TRUSTED_PROXIES") == (
        "${WS_HUB_TRUSTED_PROXIES:-127.0.0.1,::1}"
    )
