"""ws-hub revocation replay window is bounded by the access-token lifetime and stream retention."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
import yaml

from tests.test_helm_staging_contract import (
    CHART,
    STAGING_VALUES,
    _component_resource,
    _helm,
    _render_staging,
    _resolved_staging_args,
)

# The CACHE_INVALIDATIONS stream retains cache.revoke messages for seven days.
# A late-starting replica cannot replay anything older than that, so a larger
# window would only pretend to cover revocations that the stream has discarded.
_STREAM_RETENTION_SECONDS = 604_800
_ACCESS_TOKEN_LIFETIME_SECONDS = 3_600


def _render_result(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed local Helm contract command
        [
            _helm(),
            "template",
            "ws-hub-replay-window",
            str(CHART),
            "--dependency-update=false",
            "--namespace",
            "university-ecosystem",
            "--values",
            str(STAGING_VALUES),
            *_resolved_staging_args(),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _ws_hub_environment(resources: list[dict[str, Any]]) -> dict[str, str]:
    ws_hub = _component_resource(resources, "Deployment", "ws-hub")
    container = ws_hub["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: str(item.get("value")) for item in container["env"]}


def test_default_replay_window_covers_the_access_token_lifetime() -> None:
    resources = _render_staging(release_name="ws-hub-replay-window")
    environment = _ws_hub_environment(resources)

    assert environment["WS_REVOCATION_REPLAY_WINDOW_SECONDS"] == str(
        _ACCESS_TOKEN_LIFETIME_SECONDS
    )
    backend = _component_resource(resources, "Deployment", "backend")
    backend_environment = {
        item["name"]: item.get("value")
        for item in backend["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert backend_environment["ACCESS_TOKEN_EXPIRE_MINUTES"] == "60"


@pytest.mark.parametrize("window", [3_600, _STREAM_RETENTION_SECONDS])
def test_replay_window_accepts_the_inclusive_supported_range(window: int) -> None:
    result = _render_result(
        "--set", f"wsHub.config.revocationReplayWindowSeconds={window}"
    )

    assert result.returncode == 0, result.stderr
    resources = [item for item in yaml.safe_load_all(result.stdout) if item]
    assert _ws_hub_environment(resources)["WS_REVOCATION_REPLAY_WINDOW_SECONDS"] == str(
        window
    )


@pytest.mark.parametrize(
    ("window", "expected_message"),
    [
        (_ACCESS_TOKEN_LIFETIME_SECONDS - 1, "must be at least"),
        (_STREAM_RETENTION_SECONDS + 1, "maximum"),
        (0, "revocationReplayWindowSeconds"),
        (-1, "revocationReplayWindowSeconds"),
    ],
)
def test_replay_window_outside_the_supported_range_fails_the_render(
    window: int, expected_message: str
) -> None:
    result = _render_result(
        "--set", f"wsHub.config.revocationReplayWindowSeconds={window}"
    )

    assert result.returncode != 0
    assert expected_message in result.stderr


def test_template_rejects_a_replay_window_beyond_stream_retention_without_schema() -> (
    None
):
    # The schema maximum is the first guard; this exercises the template rule
    # directly so the render still fails closed if the schema bound is relaxed.
    result = _render_result(
        "--skip-schema-validation",
        "--set",
        f"wsHub.config.revocationReplayWindowSeconds={_STREAM_RETENTION_SECONDS + 1}",
    )

    assert result.returncode != 0
    assert "must not exceed the 604800-second" in result.stderr


def test_ws_hub_liveness_and_startup_never_depend_on_revocation_replay() -> None:
    # The replay barrier flips /health/ready to 503 while the cache.revoke consumer
    # drains. Restart decisions must stay on /health/live so a long drain only
    # removes the replica from service instead of restarting it.
    resources = _render_staging(release_name="ws-hub-replay-window")
    container = _component_resource(resources, "Deployment", "ws-hub")["spec"][
        "template"
    ]["spec"]["containers"][0]

    assert container["startupProbe"]["httpGet"]["path"] == "/health/live"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
