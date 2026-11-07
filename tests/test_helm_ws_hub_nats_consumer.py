"""ws-hub durable NATS consumer contract (AUD-478) is rendered from the chart.

The cache-invalidation consumers take their ack policy, ack wait, max deliver and
inactive threshold from wsHub.config.natsConsumer. The chart must render exactly
those values, reject out-of-range values before the pod starts, and keep the code
defaults in services/ws-hub/pkg/config equal to the chart defaults.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_helm_staging_contract import _component_resource, _render_staging

REPO_ROOT = Path(__file__).resolve().parents[1]
WS_HUB_CONFIG = REPO_ROOT / "services" / "ws-hub" / "pkg" / "config" / "config.go"

_ENV_BY_KEY = {
    "ackPolicy": "WS_NATS_ACK_POLICY",
    "ackWaitSeconds": "WS_NATS_ACK_WAIT_SECONDS",
    "maxDeliver": "WS_NATS_MAX_DELIVER",
    "inactiveThresholdSeconds": "WS_NATS_INACTIVE_THRESHOLD_SECONDS",
}


def _ws_hub_environment(resources: list[dict[str, Any]]) -> dict[str, str]:
    ws_hub = _component_resource(resources, "Deployment", "ws-hub")
    container = ws_hub["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: str(item.get("value")) for item in container["env"]}


def _go_default(name: str) -> str:
    source = WS_HUB_CONFIG.read_text(encoding="utf-8")
    match = re.search(rf"\b{name}\s*=\s*(\S+)", source)
    assert match is not None, f"{name} is not declared in ws-hub config"
    return match.group(1).rstrip(",")


def test_default_consumer_contract_is_rendered_into_ws_hub() -> None:
    resources = _render_staging(release_name="ws-hub-nats-consumer")
    environment = _ws_hub_environment(resources)

    assert environment["WS_NATS_ACK_POLICY"] == "explicit"
    assert environment["WS_NATS_ACK_WAIT_SECONDS"] == "60"
    assert environment["WS_NATS_MAX_DELIVER"] == "20"
    assert environment["WS_NATS_INACTIVE_THRESHOLD_SECONDS"] == "300"


def test_chart_defaults_match_the_ws_hub_code_defaults() -> None:
    resources = _render_staging(release_name="ws-hub-nats-consumer")
    environment = _ws_hub_environment(resources)

    assert environment["WS_NATS_ACK_WAIT_SECONDS"] == _go_default(
        "DefaultNATSAckWaitSeconds"
    )
    assert environment["WS_NATS_MAX_DELIVER"] == _go_default("DefaultNATSMaxDeliver")
    assert environment["WS_NATS_INACTIVE_THRESHOLD_SECONDS"] == _go_default(
        "DefaultNATSInactiveThresholdSeconds"
    )
    assert environment["WS_NATS_ACK_POLICY"] == _go_default(
        "NATSAckPolicyExplicit"
    ).strip('"')


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ackWaitSeconds", 31),
        ("ackWaitSeconds", 600),
        ("maxDeliver", 5),
        ("maxDeliver", 100),
        ("inactiveThresholdSeconds", 60),
        ("inactiveThresholdSeconds", 86_400),
    ],
)
def test_consumer_bounds_render_inclusively(key: str, value: int) -> None:
    resources = _render_staging(
        "--set",
        f"wsHub.config.natsConsumer.{key}={value}",
        release_name="ws-hub-nats-consumer",
    )

    assert _ws_hub_environment(resources)[_ENV_BY_KEY[key]] == str(value)


_OUT_OF_CONTRACT = [
    ("ackWaitSeconds", "30", "ackWaitSeconds (30) must be between 31 and 600"),
    ("ackWaitSeconds", "601", "ackWaitSeconds (601) must be between 31 and 600"),
    ("maxDeliver", "1", "maxDeliver (1) must be between 5 and 100"),
    ("maxDeliver", "-1", "maxDeliver (-1) must be between 5 and 100"),
    ("maxDeliver", "101", "maxDeliver (101) must be between 5 and 100"),
    (
        "inactiveThresholdSeconds",
        "59",
        "inactiveThresholdSeconds (59) must be between 60 and 86400",
    ),
    (
        "inactiveThresholdSeconds",
        "86401",
        "inactiveThresholdSeconds (86401) must be between 60 and 86400",
    ),
]


@pytest.mark.parametrize(("key", "value", "_message"), _OUT_OF_CONTRACT)
def test_consumer_bounds_outside_the_contract_fail_the_render(
    key: str, value: str, _message: str
) -> None:
    # The values schema is the first guard and names the offending path.
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--set",
            f"wsHub.config.natsConsumer.{key}={value}",
            release_name="ws-hub-nats-consumer",
        )

    assert exc_info.value.returncode != 0
    assert f"natsConsumer/{key}" in exc_info.value.stderr


@pytest.mark.parametrize(("key", "value", "expected_message"), _OUT_OF_CONTRACT)
def test_template_guard_rejects_out_of_contract_values_without_schema(
    key: str, value: str, expected_message: str
) -> None:
    # The schema bound is relaxed only in this test, so the template rule must still
    # fail closed with the same message on its own.
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--skip-schema-validation",
            "--set",
            f"wsHub.config.natsConsumer.{key}={value}",
            release_name="ws-hub-nats-consumer",
        )

    assert exc_info.value.returncode != 0
    assert expected_message in exc_info.value.stderr


def test_unsupported_ack_policy_fails_the_render() -> None:
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--set",
            "wsHub.config.natsConsumer.ackPolicy=none",
            release_name="ws-hub-nats-consumer",
        )

    assert exc_info.value.returncode != 0
    assert "natsConsumer/ackPolicy" in exc_info.value.stderr


def test_template_guard_rejects_unsupported_ack_policy_without_schema() -> None:
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--skip-schema-validation",
            "--set",
            "wsHub.config.natsConsumer.ackPolicy=none",
            release_name="ws-hub-nats-consumer",
        )

    assert exc_info.value.returncode != 0
    assert 'natsConsumer.ackPolicy must be "explicit"' in exc_info.value.stderr
