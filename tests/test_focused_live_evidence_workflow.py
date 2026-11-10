"""Execute the focused evidence gate offline, without Docker or a live stand."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)


@pytest.mark.parametrize(
    ("inventory_status", "containers", "mounts", "record", "expected_status"),
    [
        (0, "", 3, False, 0),
        (23, "", 3, False, 1),
        (23, "abc123\n", 3, False, 1),
        (0, "abc123\n", 3, False, 1),
        (0, "abc123\ndef456\n", 3, False, 1),
        (0, "", 2, False, 1),
        (0, "", 4, False, 1),
        (0, "", 3, True, 1),
    ],
)
def test_seed_cleanup_evidence_requires_successful_empty_inventory(
    tmp_path: Path,
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    inventory_status: int,
    containers: str,
    mounts: int,
    record: bool,
    expected_status: int,
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/focused-live-evidence.yml").read_text(
            encoding="utf-8"
        )
    )
    step = next(
        step
        for step in workflow["jobs"]["focused-live-evidence"]["steps"]
        if step.get("name") == "Run each spec alone and require every case to pass"
    )
    state = tmp_path / "state"
    if record:
        (state / ".secrets").mkdir(parents=True)
        (state / ".secrets/owned-stand-seed.json").write_text("{}", encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"BASH_ENV", "ENV"}
    }
    env.update(
        RUNNER_TEMP=str(tmp_path),
        LIVE_STATE_DIR=str(state),
        MOCK_INVENTORY_STATUS=str(inventory_status),
        MOCK_CONTAINERS=containers,
        MOCK_MOUNTS=str(mounts),
    )
    # Functions shadow both external entry points. No live commands are executed.
    mocks = r"""
uv() {
  printf 'live E2E counts passed=1\nlive E2E outcome=passed exit_code=0\n'
  for ((i = 0; i < MOCK_MOUNTS; i++)); do
    echo 'AUD-313 seed target verified for ue-live-0123456789abcdef: owner record is one exact read-only mount'
  done
}
docker() {
  [[ "$*" == 'ps -aq --filter label=com.docker.compose.oneoff=True' ]] || return 99
  printf '%s' "$MOCK_CONTAINERS"
  return "$MOCK_INVENTORY_STATUS"
}
"""
    bash = shutil.which("bash")
    assert bash is not None
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    completed = pytester.run(
        bash, "--noprofile", "--norc", "-e", "-c", mocks + step["run"], timeout=20
    )
    assert completed.ret == expected_status, completed.outlines + completed.errlines
    evidence = [
        line for line in completed.outlines if line.startswith("AUD-313 seed evidence ")
    ]
    # Failure must not prevent collecting evidence for the remaining four specs.
    assert len(evidence) == 5
    expected_outcome = "failed" if expected_status else "passed"
    assert all(line.endswith(f"outcome={expected_outcome}") for line in evidence)
    if not containers and inventory_status == 0:
        assert all("oneoff_containers=0 " in line for line in evidence)
    if inventory_status != 0:
        assert all("oneoff_containers=unknown " in line for line in evidence)
        assert all("abc123" not in line for line in evidence)
