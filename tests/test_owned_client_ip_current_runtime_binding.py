"""Offline source-bound contracts over synthetic inspect records.

The fixture does not authenticate an owner, a daemon or a deployed topology.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import owned_client_ip_runtime as runtime
from tests.test_owned_client_ip_acceptance import _admitted, _pins
from tests.test_owned_client_ip_runtime_topology import (
    _derive,
    _expected_input,
    _inspect_fixture,
)


def _runtime_dockerfile_command() -> list[str]:
    source = (Path(__file__).resolve().parents[1] / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )
    match = re.search(r"(?ms)^CMD\s+(\[.*?\])\s*$", source)
    assert match is not None
    command = json.loads(match.group(1).replace("\\\n", ""))
    assert isinstance(command, list)
    assert command[:4] == [
        "gunicorn",
        "app.main:app",
        "--worker-class",
        "app.server.spiffe_worker.BackendWorker",
    ]
    return command


@pytest.mark.parametrize(
    "mode", [None, "", "private"], ids=["null", "empty", "private"]
)
def test_isolated_ipc_mode_is_accepted_in_synthetic_topology(mode: str | None) -> None:
    snapshot, _ = _inspect_fixture()
    snapshot["probe"]["HostConfig"]["IpcMode"] = mode

    assert _derive(runtime, snapshot) == _expected_input(snapshot)


@pytest.mark.parametrize(
    "mode",
    ["host", "shareable", "container:fixture", "private ", "Private", False, [], {}],
    ids=["host", "shareable", "container", "space", "case", "bool", "list", "dict"],
)
def test_shared_or_invalid_ipc_mode_is_rejected(mode: object) -> None:
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    snapshot["probe"]["HostConfig"]["IpcMode"] = mode

    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


def test_backend_inspect_accepts_the_current_dockerfile_command() -> None:
    command = _runtime_dockerfile_command()
    snapshot, _ = _inspect_fixture()
    snapshot["containers"]["backend"]["Config"]["Cmd"] = command

    assert _derive(runtime, snapshot) == _expected_input(snapshot)


def test_backend_admission_pins_accept_the_current_dockerfile_command() -> None:
    pins = replace(_pins(), backend_command=tuple(_runtime_dockerfile_command()))

    assert _admitted(pins, pins)


@pytest.mark.parametrize("mutation", ["legacy_worker", "forwarded_flag", "extra_arg"])
def test_backend_inspect_rejects_a_different_dockerfile_command(mutation: str) -> None:
    command = _runtime_dockerfile_command()
    snapshot, _ = _inspect_fixture()
    snapshot["containers"]["backend"]["Config"]["Cmd"] = command.copy()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    changed = command.copy()
    if mutation == "legacy_worker":
        changed[3] = "uvicorn.workers.UvicornWorker"
    elif mutation == "forwarded_flag":
        changed.extend(["--forwarded-allow-ips", "*"])
    else:
        changed.append("--preload")
    snapshot["containers"]["backend"]["Config"]["Cmd"] = changed

    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


def test_backend_admission_rejects_legacy_worker_even_when_pins_match() -> None:
    command = _runtime_dockerfile_command()
    command[3] = "uvicorn.workers.UvicornWorker"
    pins = replace(_pins(), backend_command=tuple(command))

    assert not _admitted(pins, pins)


@pytest.mark.parametrize("configured", [None, "120"])
def test_runtime_admits_only_the_supported_ws_bucket(configured: str | None) -> None:
    snapshot, _ = _inspect_fixture()
    if configured is not None:
        snapshot["containers"]["ws-hub"]["Config"]["Env"].append(
            f"WS_UPGRADE_RATE_PER_MINUTE={configured}"
        )
    assert _derive(runtime, snapshot) == _expected_input(snapshot)


@pytest.mark.parametrize(
    "configured", ["10", "600", "0", "-1", "", "120 ", "0120", "unknown"]
)
def test_runtime_refuses_an_unbound_ws_bucket(configured: str) -> None:
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
    snapshot["containers"]["ws-hub"]["Config"]["Env"].append(
        f"WS_UPGRADE_RATE_PER_MINUTE={configured}"
    )
    with pytest.raises(runtime.RuntimeNotReady):
        _derive(runtime, snapshot)


def test_runtime_budget_matches_the_current_ws_hub_default() -> None:
    root = Path(__file__).resolve().parents[1]
    config = (root / "services/ws-hub/pkg/config/config.go").read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^const DefaultWSUpgradeRatePerMinute\s*=\s*(\d+)\s*$", config
    )
    assert match is not None
    assert int(match.group(1)) == 120
    snapshot, _ = _inspect_fixture()
    assert _derive(runtime, snapshot) == _expected_input(snapshot)
