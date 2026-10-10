"""Exercise the real Pact writer and the consumer/provider artifact boundary."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

CONTRACTS = Path(__file__).parent
CONSUMERS = (
    "test_ws_hub_contract.py",
    "test_nats_message_contract.py",
    "test_gateway_rest_contract.py",
    "test_file_processor_grpc_contract.py",
)
WS_HUB_INTERACTIONS = {
    "a cache invalidation event",
    "a user-wide cache invalidation event",
    "a broadcast event to all clients",
    "a client heartbeat timeout event",
    "a direct chat message event",
    "a chat message_sent domain event",
    "a chat deleted event",
    "a user.created domain event",
    "a notification.sent event",
    "a generic NATS task envelope",
}


def _run_consumers(
    directory: Path,
    *,
    output: Path | None,
    reverse: bool = False,
    workers: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Run isolated copies so a regression cannot rewrite checked-in pacts."""
    directory.mkdir(exist_ok=True)
    for name in (*CONSUMERS, "conftest.py"):
        source = CONTRACTS / name
        if source.exists():
            shutil.copyfile(source, directory / name)
    config = directory / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_XDIST_") and key != "PACT_OUTPUT_DIR"
    }
    env.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        PACT_DO_NOT_TRACK="true",
    )
    if output is not None:
        env["PACT_OUTPUT_DIR"] = str(output)
    command = [sys.executable, "-m", "pytest", "-c", str(config), "-q"]
    if workers:
        command.extend(["-p", "xdist.plugin", "-n", str(workers)])
    command.extend(["--basetemp", str(directory / "pytest-temp")])
    command.extend(reversed(CONSUMERS) if reverse else CONSUMERS)
    # The interpreter and consumer filenames are fixed; no shell or user input.
    return subprocess.run(  # noqa: S603
        command,
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("reverse", [False, True], ids=["ws-first", "nats-first"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="Pact FFI is unavailable on Windows"
)
def test_pact_artifact_preserves_both_ws_hub_groups(
    tmp_path: Path, reverse: bool
) -> None:
    output = tmp_path / "published"
    result = _run_consumers(tmp_path, output=output, reverse=reverse)
    assert result.returncode == 0, result.stdout + result.stderr
    # Discover outputs first so the original overwrite fails on lost messages,
    # before checking that publication also stayed outside the source tree.
    paths = list(tmp_path.rglob("ws-hub-university-backend.json"))
    assert len(paths) == 1
    interactions = json.loads(paths[0].read_text())["interactions"]
    assert {item["description"] for item in interactions} == WS_HUB_INTERACTIONS
    assert len(interactions) == len(WS_HUB_INTERACTIONS)
    assert paths[0].parent == output
    assert {path.name for path in output.glob("*.json")} == {
        "ws-hub-university-backend.json",
        "gateway-university-backend.json",
        "university-backend-file-processor.json",
    }
    for name in (
        "gateway-university-backend.json",
        "university-backend-file-processor.json",
    ):
        assert len(json.loads((output / name).read_text())["interactions"]) == 1
    assert not (tmp_path / "pacts").exists()


@pytest.mark.parametrize("workers", [0, 2], ids=["serial", "xdist"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="Pact FFI is unavailable on Windows"
)
def test_default_pact_outputs_do_not_mutate_source_snapshots(
    tmp_path: Path, workers: int
) -> None:
    snapshots = tmp_path / "pacts"
    snapshots.mkdir()
    original = b'{"preserve": "checked-in contract"}\n'
    snapshot = snapshots / "ws-hub-university-backend.json"
    snapshot.write_bytes(original)
    result = _run_consumers(tmp_path, output=None, workers=workers)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot.read_bytes() == original
    assert list(snapshots.iterdir()) == [snapshot]
    paths = list((tmp_path / "pytest-temp").rglob("ws-hub-university-backend.json"))
    assert paths
    assert {
        item["description"]
        for path in paths
        for item in json.loads(path.read_text())["interactions"]
    } == WS_HUB_INTERACTIONS


@pytest.mark.parametrize("stale", [False, True], ids=["empty", "stale"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="Pact FFI is unavailable on Windows"
)
def test_pact_publication_requires_a_fresh_destination(
    tmp_path: Path, stale: bool
) -> None:
    output = tmp_path / "published"
    output.mkdir()
    if stale:
        (output / "ws-hub-university-backend.json").write_text(
            '{"interactions": [{"description": "removed interaction"}]}',
            encoding="utf-8",
        )
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    result = _run_consumers(tmp_path, output=output)
    assert result.returncode != 0
    assert "PACT_OUTPUT_DIR must not already exist" in result.stdout + result.stderr
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


@pytest.mark.skipif(
    sys.platform == "win32", reason="Pact FFI is unavailable on Windows"
)
def test_pact_publication_rejects_parallel_writers(tmp_path: Path) -> None:
    output = tmp_path / "published"
    result = _run_consumers(tmp_path, output=output, workers=2)
    assert result.returncode != 0
    assert "PACT_OUTPUT_DIR requires serial pytest" in result.stdout + result.stderr
    assert not output.exists()


def test_checked_in_ws_hub_snapshot_preserves_both_groups() -> None:
    pact = json.loads((CONTRACTS / "pacts/ws-hub-university-backend.json").read_text())
    assert pact["consumer"]["name"] == "ws-hub"
    assert pact["provider"]["name"] == "university-backend"
    interactions = pact["interactions"]
    assert {item["description"] for item in interactions} == WS_HUB_INTERACTIONS
    assert len(interactions) == len(WS_HUB_INTERACTIONS)


def test_pact_workflow_replays_only_the_current_generated_artifacts() -> None:
    workflow = yaml.safe_load(
        (CONTRACTS.parents[1] / ".github/workflows/contract-tests.yml").read_text()
    )
    jobs = workflow["jobs"]
    consumer = jobs["consumer"]
    steps = consumer["steps"]
    generate = next(
        step for step in steps if step.get("name") == "Run consumer contract tests"
    )
    directory = generate["env"]["PACT_OUTPUT_DIR"]
    assert directory.startswith("${{ runner.temp }}/")
    assert "-n 0" in generate["run"]
    for filename in CONSUMERS:
        assert filename in generate["run"]
    upload = next(
        step for step in steps if "actions/upload-artifact@" in step.get("uses", "")
    )
    assert set(upload["with"]["path"].splitlines()) == {
        f"{directory}/ws-hub-university-backend.json",
        f"{directory}/gateway-university-backend.json",
        f"{directory}/university-backend-file-processor.json",
    }
    for name in ("message-provider-verify", "pact-provider-verify"):
        provider = jobs[name]
        download = next(
            step
            for step in provider["steps"]
            if "actions/download-artifact@" in step.get("uses", "")
        )
        assert download["with"]["path"] == directory
        assert download["with"]["name"] == upload["with"]["name"]
        assert "tests/contracts/pacts" not in str(provider)
        for step in provider["steps"]:
            if "go test -tags contract" in step.get("run", ""):
                assert step["env"]["PACT_DIR"] == directory
    http = jobs["pact-provider-verify"]
    replay = next(
        step
        for step in http["steps"]
        if step.get("name") == "Replay gateway Pact against real backend"
    )
    assert replay["env"]["PACT_DIR"] == directory
    assert '--pact-file "$PACT_DIR/gateway-university-backend.json"' in replay["run"]
