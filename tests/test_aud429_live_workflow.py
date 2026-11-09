"""Executable checks for the full-stand realtime and visual workflow guards."""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REUSABLE = ROOT / ".github/workflows/reusable-live-realtime-visual.yml"
NIGHTLY = ROOT / ".github/workflows/nightly-full-gate.yml"


def _workflow(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return result


def _step(name: str) -> dict[str, Any]:
    steps = _workflow(REUSABLE)["jobs"]["live-realtime-visual"]["steps"]
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def _embedded_python(name: str) -> str:
    run = _step(name)["run"]
    before, delimiter, after = run.partition("<<'PY'\n")
    assert delimiter and before
    body, end, _ = after.partition("\nPY\n")
    assert end
    return str(body)


def _embedded_node(name: str) -> str:
    run = _step(name)["run"]
    before, delimiter, after = run.partition("<<'NODE'\n")
    assert delimiter and before
    body, end, _ = after.partition("\nNODE\n")
    assert end
    return str(body)


def _execute_guard(
    source: str, target: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed interpreter executes the checked-in workflow guard
        [sys.executable, "-c", source, str(target), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    ("summary", "accepted"),
    [
        ("live E2E counts passed=16\nlive E2E outcome=passed exit_code=0\n", True),
        (
            "live E2E counts passed=15 skipped=1\nlive E2E outcome=passed exit_code=0\n",
            False,
        ),
        (
            "live E2E counts passed=16 flaky=1\nlive E2E outcome=passed exit_code=0\n",
            False,
        ),
        (
            "live E2E counts passed=0 skipped=16\nlive E2E outcome=passed exit_code=0\n",
            False,
        ),
        ("live E2E counts passed=16\n", False),
        ("live E2E counts passed=16\nlive E2E outcome=failed exit_code=1\n", False),
        (
            "live E2E counts passed=16\nlive E2E counts passed=16\n"
            "live E2E outcome=passed exit_code=0\n",
            False,
        ),
        ("", False),
    ],
)
def test_realtime_guard_rejects_missing_skipped_flaky_and_duplicate_results(
    tmp_path: Path, summary: str, *, accepted: bool
) -> None:
    output = tmp_path / "summary.txt"
    output.write_text("private seed output\n" + summary, encoding="utf-8")
    sanitized = tmp_path / "safe-summary.txt"
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        output,
        str(sanitized),
        "0",
    )
    assert "private seed output" not in sanitized.read_text(encoding="utf-8")
    assert (result.returncode == 0) is accepted


def test_realtime_guard_rejects_failed_process_even_with_forged_success_summary(
    tmp_path: Path,
) -> None:
    output = tmp_path / "raw.txt"
    output.write_text(
        "live E2E counts passed=16\nlive E2E outcome=passed exit_code=0\n",
        encoding="utf-8",
    )
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        output,
        str(tmp_path / "safe.txt"),
        "1",
    )
    assert result.returncode != 0


def test_realtime_artifact_drops_unrecognized_or_oversized_count_lines(
    tmp_path: Path,
) -> None:
    output = tmp_path / "raw.txt"
    output.write_text(
        "live E2E counts passed=16 private-content\n"
        "live E2E outcome=passed exit_code=0 private-content\n"
        + "live E2E counts "
        + "passed=16 " * 40
        + "\n",
        encoding="utf-8",
    )
    sanitized = tmp_path / "safe.txt"
    result = _execute_guard(
        _embedded_python("Exercise real realtime sessions without skips"),
        output,
        str(sanitized),
        "0",
    )
    assert result.returncode != 0
    assert sanitized.read_text(encoding="utf-8") == "\n"


def _screenshots(directory: Path) -> list[Path]:
    directory.mkdir()
    paths = []
    for route, locale, theme, width in itertools.product(
        ("dashboard", "events", "news"),
        ("en", "ru"),
        ("light", "dark"),
        (390, 1440),
    ):
        image = directory / f"{route}_{locale}_{theme}_w{width}.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        paths.append(image)
    return paths


@pytest.mark.parametrize(
    "defect", ["none", "missing", "duplicate", "invalid", "renamed"]
)
def test_visual_guard_requires_the_exact_complete_png_matrix(
    tmp_path: Path, defect: str
) -> None:
    output = tmp_path / "captures"
    images = _screenshots(output)
    if defect == "missing":
        images[0].unlink()
    elif defect == "duplicate":
        extra = output / "extra"
        extra.mkdir()
        (extra / images[0].name).write_bytes(images[0].read_bytes())
    elif defect == "invalid":
        images[0].write_bytes(b"not an image")
    elif defect == "renamed":
        images[0].rename(output / "wrong.png")
    result = _execute_guard(
        _embedded_python(
            "Capture and audit authenticated visual matrix on the full stand"
        ),
        output,
    )
    assert (result.returncode == 0) is (defect == "none")


def test_workflow_runs_the_live_apis_and_uploads_bounded_evidence() -> None:
    job = _workflow(REUSABLE)["jobs"]["live-realtime-visual"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 180
    assert "continue-on-error" not in job
    start = _step("Start the owned full live stand")
    assert "--stack full" in start["run"]
    realtime = _step("Exercise real realtime sessions without skips")["run"]
    for source in (
        "messenger-realtime.live.spec.ts",
        "messenger-reconnect-ordering.live.spec.ts",
        "messenger-unread-read.live.spec.ts",
    ):
        assert source in realtime
    visual = _step("Capture and audit authenticated visual matrix on the full stand")
    assert "verify-endpoints" in visual["run"]
    assert "VISUAL_CAPTURE_MATRIX=1" in visual["run"]
    assert "authenticated-visual-audit.mjs" in visual["run"]
    assert (
        visual["if"] == "${{ !cancelled() && steps.start-stand.outcome == 'success' }}"
    )
    assert "steps.realtime.outcome" not in visual["if"]
    assert "continue-on-error" not in visual
    assert "load_or_create_stand_admin_password" in visual["run"]
    assert "::add-mask::" in visual["run"]
    for name in (
        "Upload redacted realtime execution summary",
        "Upload synthetic visual screenshots",
    ):
        step = _step(name)
        assert step["with"]["if-no-files-found"] == "error"
        assert step["with"]["retention-days"] == 14
        assert "github.sha" in step["with"]["name"]
    assert _step("Upload synthetic visual screenshots")["with"]["path"].endswith(
        "/**/*.png"
    )
    assert "always()" in _step("Stop only the owned stand containers")["if"]


def test_visual_diagnostic_runs_after_realtime_failure_and_keeps_the_job_blocking() -> (
    None
):
    visual = _step("Capture and audit authenticated visual matrix on the full stand")
    realtime = _step("Exercise real realtime sessions without skips")
    stop = _step("Stop only the owned stand containers")
    job = _workflow(REUSABLE)["jobs"]["live-realtime-visual"]

    # Model the checked-in status expression with mocked step outcomes. GitHub's
    # cancelled() status function removes the implicit success() condition.
    expression = visual["if"]
    assert "!cancelled()" in expression
    assert "steps.start-stand.outcome == 'success'" in expression
    assert "steps.realtime.outcome" not in expression
    assert "continue-on-error" not in job
    assert "continue-on-error" not in realtime

    def evaluate(
        *,
        stand: str,
        cancelled: bool,
        realtime_result: str,
        visual_result: str = "success",
    ) -> tuple[bool, bool, bool]:
        visual_runs = not cancelled and stand == "success"
        cleanup_runs = stand != "skipped" and "always()" in stop["if"]
        job_fails = not cancelled and (
            realtime_result != "success"
            or not visual_runs
            or (visual_runs and visual_result != "success")
        )
        return visual_runs, cleanup_runs, job_fails

    assert evaluate(stand="success", cancelled=False, realtime_result="failure") == (
        True,
        True,
        True,
    )
    assert evaluate(stand="success", cancelled=False, realtime_result="success") == (
        True,
        True,
        False,
    )
    assert evaluate(
        stand="success",
        cancelled=False,
        realtime_result="success",
        visual_result="failure",
    ) == (True, True, True)
    assert evaluate(stand="failure", cancelled=False, realtime_result="skipped") == (
        False,
        True,
        True,
    )
    assert evaluate(stand="success", cancelled=True, realtime_result="cancelled") == (
        False,
        True,
        False,
    )


def test_visual_runner_masks_owned_password_and_isolates_audit_environment(
    tmp_path: Path,
) -> None:
    source = _embedded_node(
        "Capture and audit authenticated visual matrix on the full stand"
    )
    source = source.replace(
        'import { spawnSync } from "node:child_process"',
        "const spawnSync = globalThis.__mockSpawnSync",
    )
    source = source.replace(
        'import {\n  createAuthenticatedVisualAuditEnvironment,\n} from "./scripts/authenticated-visual-audit.mjs"',
        "const { createAuthenticatedVisualAuditEnvironment } = globalThis.__visualHelpers",
    )
    assert "__mockSpawnSync" in source
    assert "__visualHelpers" in source

    runner = tmp_path / "visual-runner.mjs"
    runner.write_text(source, encoding="utf-8")
    harness = tmp_path / "mock-workflow.mjs"
    harness.write_text(
        """import process from 'node:process'
import { pathToFileURL } from 'node:url'

const calls = []
const maskedOutput = []
let helperInput
const originalWrite = process.stdout.write.bind(process.stdout)
process.stdout.write = (chunk) => {
  maskedOutput.push(String(chunk))
  return true
}
globalThis.__mockSpawnSync = (command, args, options) => {
  const environment = options.env
  calls.push({
    command,
    args,
    cwd: options.cwd,
    env: {
      testEmailPresent: Object.hasOwn(environment, 'TEST_EMAIL'),
      testPasswordPresent: Object.hasOwn(environment, 'TEST_PASSWORD'),
      testEmail: environment.TEST_EMAIL,
      testPasswordMatchesOwned: environment.TEST_PASSWORD === process.env.MOCK_TEST_PASSWORD,
      tokenPresent: Object.hasOwn(environment, 'GITHUB_TOKEN'),
    },
    stdio: options.stdio,
  })
  return calls.length === 1
    ? { status: 0, stdout: `${process.env.MOCK_TEST_PASSWORD}\\n` }
    : { status: 0 }
}
globalThis.__visualHelpers = {
  createAuthenticatedVisualAuditEnvironment(environment, credentials) {
    helperInput = {
      testEmailPresent: Object.hasOwn(environment, 'TEST_EMAIL'),
      testPasswordPresent: Object.hasOwn(environment, 'TEST_PASSWORD'),
      tokenPresent: Object.hasOwn(environment, 'GITHUB_TOKEN'),
      credentialsMatchOwnedPassword:
        credentials.password === process.env.MOCK_TEST_PASSWORD,
    }
    return {
      PATH: environment.PATH,
      ORIGIN: environment.ORIGIN,
      SOURCE_SHA: environment.SOURCE_SHA,
      TEST_EMAIL: credentials.email,
      TEST_PASSWORD: credentials.password,
    }
  },
}
await import(pathToFileURL(process.argv[2]).href)
process.stdout.write = originalWrite
originalWrite(JSON.stringify({
  calls,
  maskCommandCorrect: maskedOutput.length === 1 &&
    maskedOutput[0] === `::add-mask::${process.env.MOCK_TEST_PASSWORD}\\n`,
  helperInput,
}))
""",
        encoding="utf-8",
    )

    node = shutil.which("node")
    assert node is not None, "Node.js is required for the mocked workflow runner"
    owned_password = f"runtime-{uuid4()}"
    ambient_password = f"ambient-{uuid4()}"
    ambient_token = f"ambient-{uuid4()}"
    environment = {
        **os.environ,
        "MOCK_TEST_PASSWORD": owned_password,
        "LIVE_STATE_DIR": str(tmp_path / "owned-state"),
        "GITHUB_WORKSPACE": str(tmp_path / "workspace"),
        "TEST_EMAIL": "ambient@example.test",
        "TEST_PASSWORD": ambient_password,
        "GITHUB_TOKEN": ambient_token,
        "ORIGIN": "http://127.0.0.1:18000",
        "SOURCE_SHA": "b" * 40,
    }
    result = subprocess.run(  # noqa: S603  # fixed Node interpreter executes the mocked workflow wrapper
        [node, str(harness), str(runner)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    outcome = json.loads(result.stdout)
    assert len(outcome["calls"]) == 2
    assert outcome["calls"][0]["cwd"] == environment["GITHUB_WORKSPACE"]
    assert outcome["calls"][0]["env"]["testEmailPresent"] is False
    assert outcome["calls"][0]["env"]["testPasswordPresent"] is False
    assert outcome["calls"][0]["env"]["tokenPresent"] is False
    assert outcome["calls"][1]["env"]["testEmail"] == "test@university.dev"
    assert outcome["calls"][1]["env"]["testPasswordMatchesOwned"] is True
    assert outcome["calls"][1]["env"]["tokenPresent"] is False
    assert outcome["calls"][1]["stdio"] == "inherit"
    assert outcome["helperInput"]["testEmailPresent"] is False
    assert outcome["helperInput"]["testPasswordPresent"] is False
    assert outcome["helperInput"]["tokenPresent"] is True
    assert outcome["helperInput"]["credentialsMatchOwnedPassword"] is True
    assert outcome["maskCommandCorrect"] is True
    assert owned_password not in result.stderr
    assert ambient_password not in result.stdout
    assert ambient_token not in result.stdout


def test_nightly_runs_and_reports_the_same_live_workflow_on_main() -> None:
    jobs = _workflow(NIGHTLY)["jobs"]
    assert (
        jobs["live-realtime-visual"]["if"] == "${{ github.ref == 'refs/heads/main' }}"
    )
    assert (
        jobs["live-realtime-visual"]["uses"]
        == "./.github/workflows/reusable-live-realtime-visual.yml"
    )
    assert "live-realtime-visual" in jobs["notify-failure"]["needs"]
