"""Exercise the differential coverage step with controlled external commands."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reusable-frontend-tests.yml"
RUN_GUID = "0" * 32
pytest_plugins = ("pytester",)


def _bash() -> str:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if os.name == "nt" and git_bash.is_file():
        return str(git_bash)
    found = shutil.which("bash")
    assert found, "Bash is required for the workflow execution contract"
    return found


def _shell_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    absolute = path.resolve().as_posix()
    return f"/{absolute[0].lower()}{absolute[2:]}"


def _fake_tools(directory: Path) -> None:
    common = """#!/usr/bin/env bash
set -eu
name=${0##*/}
if [[ "$name" == node && "${1:-}" == -p ]]; then
  printf '%032d\\n' 0
  exit 0
fi
printf '%s' "$name" >> "$EVENTS"
printf '|%s' "$@" >> "$EVENTS"
printf '\\n' >> "$EVENTS"
case "$name:${1:-}" in
  uv:sync) phase=sync ;;
  uv:run) phase=diff ;;
  node:--test) phase=contract ;;
  node:*)
    phase=preflight
    while (($#)); do
      if [[ "$1" == --output ]]; then
        shift
        printf 'normalized report' > "$1"
        break
      fi
      shift
    done
    ;;
  git:fetch) phase=fetch ;;
  *) exit 99 ;;
esac
if [[ "${FAIL_AT:-}" == "$phase" ]]; then exit 17; fi
"""
    directory.mkdir()
    for name in ("uv", "node", "git"):
        executable = directory / name
        executable.write_text(common, encoding="utf-8", newline="\n")
        executable.chmod(0o755)


@pytest.mark.parametrize(
    ("fail_at", "expected_commands"),
    [
        ("", ["uv", "node", "git", "node", "uv"]),
        ("sync", ["uv"]),
        ("contract", ["uv", "node"]),
        ("fetch", ["uv", "node", "git"]),
        ("collision", ["uv", "node", "git"]),
        ("preflight", ["uv", "node", "git", "node"]),
        ("diff", ["uv", "node", "git", "node", "uv"]),
    ],
)
def test_differential_coverage_runs_in_order_and_cleans_up(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    fail_at: str,
    expected_commands: list[str],
) -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    steps = jobs["unit-tests"]["steps"]
    step = next(
        item
        for item in steps
        if item.get("name") == "Check differential frontend coverage"
    )
    assert step["shell"] == "bash"
    assert step["if"] == "${{ github.event_name == 'pull_request' }}"
    assert step["env"]["COMPARE_BRANCH"] == "${{ github.base_ref }}"

    tmp_path = pytester.path
    bin_dir = tmp_path / "bin"
    _fake_tools(bin_dir)
    runner_temp = tmp_path / "runner temp"
    runner_temp.mkdir()
    report_path = runner_temp / f"frontend-diff-lcov-123-2-{RUN_GUID}.info"
    if fail_at == "collision":
        report_path.write_text("existing report", encoding="utf-8")
    events = tmp_path / "events.txt"
    branch = "feature/$literal;touch injected"
    env = {
        "RUNNER_TEMP": _shell_path(runner_temp),
        "GITHUB_WORKSPACE": _shell_path(tmp_path),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "COMPARE_BRANCH": branch,
        "EVENTS": _shell_path(events),
        "FAIL_AT": fail_at,
        "FAKE_BIN": _shell_path(bin_dir),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    result = pytester.run(
        _bash(),
        "--noprofile",
        "--norc",
        "-e",
        "-o",
        "pipefail",
        "-c",
        'PATH="$FAKE_BIN:$PATH"\n' + step["run"],
        timeout=15,
    )
    assert (result.ret == 0) is (not fail_at), result.stderr.lines
    lines = events.read_text(encoding="utf-8").splitlines()
    assert [line.split("|", 1)[0] for line in lines] == expected_commands
    if "git" in expected_commands:
        assert f"git|fetch|origin|{branch}" in lines
    if fail_at not in ("sync", "contract", "fetch", "collision"):
        report = _shell_path(report_path)
        assert (
            "node|scripts/quality/verify_frontend_diff_coverage.mjs"
            f"|--repo-root|{_shell_path(tmp_path)}|--base-ref|origin/{branch}|--output|{report}"
        ) in lines
    if not fail_at or fail_at == "diff":
        assert lines[-1].endswith(f"|--compare-branch=origin/{branch}|--fail-under=100")
    if fail_at == "collision":
        assert report_path.read_text(encoding="utf-8") == "existing report"
    else:
        assert list(runner_temp.iterdir()) == []
    assert not (tmp_path / "injected").exists()
