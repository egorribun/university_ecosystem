"""ws-hub revocation replay window is bounded by the access-token lifetime and stream retention."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import Mock

import pytest

from tests import test_helm_staging_contract as staging_contract
from tests.test_helm_staging_contract import _component_resource, _render_staging

# The CACHE_INVALIDATIONS stream retains cache.revoke messages for seven days.
# A late-starting replica cannot replay anything older than that, so a larger
# window would only pretend to cover revocations that the stream has discarded.
_STREAM_RETENTION_SECONDS = 604_800
_ACCESS_TOKEN_LIFETIME_SECONDS = 3_600


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
    resources = _render_staging(
        "--set",
        f"wsHub.config.revocationReplayWindowSeconds={window}",
        release_name="ws-hub-replay-window",
    )

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
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--set",
            f"wsHub.config.revocationReplayWindowSeconds={window}",
            release_name="ws-hub-replay-window",
        )

    assert exc_info.value.returncode != 0
    assert expected_message in exc_info.value.stderr


def test_template_rejects_a_replay_window_beyond_stream_retention_without_schema() -> (
    None
):
    # The schema maximum is the first guard; this exercises the template rule
    # directly so the render still fails closed if the schema bound is relaxed.
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(
            "--skip-schema-validation",
            "--set",
            f"wsHub.config.revocationReplayWindowSeconds={_STREAM_RETENTION_SECONDS + 1}",
            release_name="ws-hub-replay-window",
        )

    assert exc_info.value.returncode != 0
    assert "must not exceed the 604800-second" in exc_info.value.stderr


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


def test_shared_staging_render_has_a_bounded_checked_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = [
        "/synthetic/helm",
        "template",
        "ws-hub-replay-window",
        str(staging_contract.CHART),
        "--dependency-update=false",
        "--namespace",
        "university-ecosystem",
        "--values",
        str(staging_contract.STAGING_VALUES),
        *staging_contract._resolved_staging_args(),
        "--set",
        "wsHub.config.revocationReplayWindowSeconds=3600",
    ]
    completed = subprocess.CompletedProcess(
        command,
        0,
        stdout="apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: bounded-render\n",
        stderr="",
    )
    run = Mock(return_value=completed)
    monkeypatch.setattr(staging_contract, "_helm", lambda: "/synthetic/helm")
    monkeypatch.setattr(staging_contract.subprocess, "run", run)

    resources = _render_staging(
        "--set",
        "wsHub.config.revocationReplayWindowSeconds=3600",
        release_name="ws-hub-replay-window",
    )

    assert resources == [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "bounded-render"},
        }
    ]
    run.assert_called_once_with(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def test_shared_staging_render_preserves_process_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = subprocess.CalledProcessError(
        1, ["/synthetic/helm"], stderr="bounded-render rejection"
    )
    run = Mock(side_effect=error)
    monkeypatch.setattr(staging_contract, "_helm", lambda: "/synthetic/helm")
    monkeypatch.setattr(staging_contract.subprocess, "run", run)

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _render_staging(release_name="ws-hub-replay-window")

    assert exc_info.value is error
    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "bounded-render rejection"
    assert run.call_count == 1
    assert run.call_args.kwargs["check"] is True
    assert run.call_args.kwargs["timeout"] == 60


@pytest.mark.parametrize("without_schema", [False, True])
def test_replay_window_negative_oracles_do_not_accept_timeout(
    monkeypatch: pytest.MonkeyPatch, without_schema: bool
) -> None:
    error = subprocess.TimeoutExpired(["/synthetic/helm"], 60)
    run = Mock(side_effect=error)
    monkeypatch.setattr(staging_contract, "_helm", lambda: "/synthetic/helm")
    monkeypatch.setattr(staging_contract.subprocess, "run", run)

    with pytest.raises(subprocess.TimeoutExpired) as exc_info:
        if without_schema:
            rejection_oracle = test_template_rejects_a_replay_window_beyond_stream_retention_without_schema
            rejection_oracle()
        else:
            test_replay_window_outside_the_supported_range_fails_the_render(
                _ACCESS_TOKEN_LIFETIME_SECONDS - 1, "must be at least"
            )

    assert exc_info.value is error
    assert run.call_count == 1
    assert run.call_args.kwargs["check"] is True
    assert run.call_args.kwargs["timeout"] == 60
