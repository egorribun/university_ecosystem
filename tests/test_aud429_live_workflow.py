"""Executable checks for the full-stand realtime and visual workflow guards."""

from __future__ import annotations

import itertools
import subprocess
import sys
from pathlib import Path
from typing import Any

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
