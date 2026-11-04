"""Exercise the AUD-378 provenance step's fail-closed shell behavior.

The verifier's cryptographic behavior is exercised by the hosted job. These
tests run the actual workflow step under Bash with external commands replaced
by deterministic doubles so download, checksum, and verification failures can
be injected without network access or long retry delays.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
VERIFY_STEP = "Verify SLSA provenance attestation of slsa-verifier"


def _bash() -> str:
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_dir = Path(git).resolve().parent
            for candidate in (
                git_dir / "bash.exe",
                git_dir.parent / "bin" / "bash.exe",
            ):
                if candidate.is_file():
                    return str(candidate)
    executable = shutil.which("bash")
    if not executable:
        pytest.fail("Bash is required to execute the provenance workflow step")
    return executable


def _step_body() -> str:
    workflow: dict[str, Any] = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["provenance-check"]["steps"]
    matches = [step for step in steps if step.get("name") == VERIFY_STEP]
    assert len(matches) == 1
    body: str = matches[0]["run"]
    return body


_COMMAND_DOUBLES = """
attempts=0
curl() {
  printf 'TRACE download\\n'
  return "$DOWNLOAD_STATUS"
}
sha256sum() {
  read -r checksum path
  printf 'TRACE checksum\\n'
  return "$CHECKSUM_STATUS"
}
timeout() {
  attempts=$((attempts + 1))
  printf 'TRACE verify %s\\n' "$*"
  if [[ "$attempts" -le "$VERIFY_FAILURES" ]]; then
    return "$VERIFY_STATUS"
  fi
  return 0
}
sleep() { printf 'TRACE delay %s\\n' "$1"; }
"""


def _run_step(
    *,
    download_status: int = 0,
    checksum_status: int = 0,
    verify_failures: int = 0,
    verify_status: int = 1,
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "RUNNER_TEMP": "runner-test",
        "DOWNLOAD_STATUS": str(download_status),
        "CHECKSUM_STATUS": str(checksum_status),
        "VERIFY_FAILURES": str(verify_failures),
        "VERIFY_STATUS": str(verify_status),
    }
    return subprocess.run(  # noqa: S603  # fixed argv executes the repository workflow step
        [_bash(), "-c", _COMMAND_DOUBLES + "\n" + _step_body()],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _trace(result: subprocess.CompletedProcess[str], action: str) -> list[str]:
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith(f"TRACE {action}")
    ]


def test_verification_succeeds_only_after_the_verifier_accepts() -> None:
    result = _run_step(verify_failures=1)

    assert result.returncode == 0, result.stderr
    attempts = _trace(result, "verify")
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    assert "--source-uri github.com/slsa-framework/slsa-verifier" in attempts[0]
    assert "--source-tag v2.7.1" in attempts[0]
    assert _trace(result, "delay") == ["TRACE delay 20"]
    assert "attestation verified" in result.stdout


@pytest.mark.parametrize("status", [1, 124])
def test_exhausted_verification_failures_fail_the_step(status: int) -> None:
    result = _run_step(verify_failures=3, verify_status=status)

    assert result.returncode != 0
    assert len(_trace(result, "verify")) == 3
    assert _trace(result, "delay") == ["TRACE delay 20", "TRACE delay 40"]
    assert "did not verify" in result.stderr
    assert "attestation verified" not in result.stdout


def test_download_failure_stops_before_checksum_or_verification() -> None:
    result = _run_step(download_status=22)

    assert result.returncode != 0
    assert _trace(result, "download") == ["TRACE download"]
    assert not _trace(result, "checksum")
    assert not _trace(result, "verify")


def test_checksum_failure_stops_before_verification() -> None:
    result = _run_step(checksum_status=1)

    assert result.returncode != 0
    assert _trace(result, "checksum") == ["TRACE checksum"]
    assert not _trace(result, "verify")
