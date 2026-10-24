"""Regression contracts for complete-history secret scanning in CI."""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import shutil
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.quality import gitleaks_ci
from scripts.quality.gitleaks_ci import (
    GitleaksGateError,
    build_gitleaks_command,
    execute_scan,
    prepare_scan,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GITLEAKS_CONFIG_PATH = REPOSITORY_ROOT / ".gitleaks.toml"
GITLEAKS_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "gitleaks.yml"
CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_GO_ACTION = "actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e"
UPLOAD_ARTIFACT_ACTION = (
    "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
)
SYNTHETIC_RESOLUTION_MARKER = "merge-resolution-only-contract-marker"


def _workflow_triggers(workflow: dict[object, object]) -> dict[str, object]:
    """Support PyYAML's YAML 1.1 parsing of the "on" key as True."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _git(repo: Path, *args: str, check: bool = True) -> SimpleNamespace:
    command = ["git", "-C", str(repo), *args]

    async def run() -> SimpleNamespace:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        result = SimpleNamespace(
            returncode=process.returncode,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
        if check and result.returncode != 0:
            raise AssertionError(result.stderr)
        return result

    return asyncio.run(run())


def _commit(repo: Path, message: str) -> None:
    _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit",
        "-m",
        message,
    )


def _create_pull_request_graph(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Build 30+ commits and a merge-only change without touching the checkout."""

    repo = tmp_path / "source"
    repo.mkdir()
    shutil.copyfile(GITLEAKS_CONFIG_PATH, repo / ".gitleaks.toml")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "core.autocrlf", "false")
    for index in range(4):
        (repo / f"base-history-{index:02d}.txt").write_text(
            f"history {index}\n", encoding="utf-8"
        )
        _git(repo, "add", ".")
        _commit(repo, "base history")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _commit(repo, "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "-c", "pull-request")
    for index in range(32):
        (repo / f"step-{index:02d}.txt").write_text(
            f"change {index}\n", encoding="utf-8"
        )
        _git(repo, "add", ".")
        _commit(repo, f"change {index}")

    (repo / "conflict.txt").write_text("common\n", encoding="utf-8")
    _git(repo, "add", "conflict.txt")
    _commit(repo, "add merge base")

    _git(repo, "switch", "-c", "resolution-side")
    (repo / "conflict.txt").write_text("side parent\n", encoding="utf-8")
    _git(repo, "add", "conflict.txt")
    _commit(repo, "side change")
    side_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "pull-request")
    (repo / "conflict.txt").write_text("first parent\n", encoding="utf-8")
    _git(repo, "add", "conflict.txt")
    _commit(repo, "first-parent change")
    first_parent_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "conflict.txt").write_text(
        f"resolved\n{SYNTHETIC_RESOLUTION_MARKER}\n", encoding="utf-8"
    )
    _git(repo, "add", "conflict.txt")
    merge_tree = _git(repo, "write-tree").stdout.strip()
    merge_sha = _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit-tree",
        merge_tree,
        "-p",
        first_parent_sha,
        "-p",
        side_sha,
        "-m",
        "resolve conflict",
    ).stdout.strip()
    _git(repo, "reset", "--hard", merge_sha)
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "switch", "--detach", base_sha)
    _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "merge",
        "--no-ff",
        "-m",
        "synthetic checkout merge",
        head_sha,
    )
    checkout_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base_sha, head_sha, checkout_sha


def _pull_request_environment(
    base_sha: str,
    head_sha: str,
    checkout_sha: str,
    repository: Path,
) -> dict[str, str]:
    return {
        "GITLEAKS_EVENT_NAME": "pull_request",
        "GITLEAKS_BASE_SHA": base_sha,
        "GITLEAKS_EVENT_HEAD_SHA": head_sha,
        "GITHUB_SHA": checkout_sha,
        "GITHUB_WORKSPACE": str(repository),
    }


def test_gitleaks_allowlist_contains_only_existing_lockfile_paths() -> None:
    """Stale file and placeholder exceptions must not hide secret findings."""

    import tomllib

    with GITLEAKS_CONFIG_PATH.open("rb") as config_file:
        allowlist = tomllib.load(config_file)["allowlist"]

    assert set(allowlist["paths"]) == {"uv.lock", "package-lock.json", "go.sum"}
    assert "files" not in allowlist
    assert "regexes" not in allowlist


def test_gitleaks_configuration_extends_default_detection_rules() -> None:
    """The custom repository config must retain the built-in detector rules."""

    import tomllib

    with GITLEAKS_CONFIG_PATH.open("rb") as config_file:
        config = tomllib.load(config_file)

    assert config.get("extend") == {"useDefault": True}


def test_gitleaks_scans_main_pushes_and_pull_requests_without_duplicate_runs() -> None:
    """The protected branch and PR receive one authoritative scan each."""

    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert triggers["push"]["branches"] == ["main"]
    # The pull-request base-branch filter keeps source-branch pushes from
    # duplicating the protected-branch scan.
    assert triggers["pull_request"]["branches"] == ["main"]


def test_gitleaks_workflow_pins_complete_graph_scanner_and_redacted_artifact() -> None:
    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["gitleaks"]
    assert job["name"] == "Gitleaks scan"
    assert workflow["permissions"] == {"contents": "read"}

    steps = job["steps"]
    checkout = next(step for step in steps if step["name"] == "Checkout repository")
    assert checkout["uses"] == CHECKOUT_ACTION
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}

    policy_guard = next(
        step
        for step in steps
        if step["name"] == "Verify security policy inputs against protected base"
    )
    assert policy_guard["if"] == "${{ github.event_name == 'pull_request' }}"
    for required in (
        "BASE_SHA",
        "BASE_REPOSITORY",
        "PR_AUTHOR",
        "policy_paths=(",
        "BASE_REPOSITORY",
        "security policy changes require an owner-authored PR",
    ):
        assert required in policy_guard["run"]
    for path in (
        '".github/workflows"',
        '".gitleaks.toml"',
        '".gitleaksignore"',
        '"native/rust_ext/deny.toml"',
        '"quality/ci-check-catalog.json"',
        '"quality/security-false-positive-dispositions.json"',
        '"security/audit-allowlist.yaml"',
    ):
        assert path in policy_guard["run"]

    setup_go = next(step for step in steps if step["name"] == "Set up Go")
    assert setup_go["uses"] == SETUP_GO_ACTION
    assert setup_go["with"]["go-version"] == "1.26.10"
    assert setup_go["with"]["cache"] is False

    install = next(step for step in steps if step["name"] == "Install Gitleaks")
    assert install["env"]["GOSUMDB"] == "sum.golang.org"
    assert install["env"]["GOPROXY"] == "https://proxy.golang.org"
    assert "github.com/zricethezav/gitleaks/v8@v8.30.1" in install["run"]
    assert "go version -m" in install["run"]
    assert "v8.30.1" in install["run"]
    assert "latest" not in install["run"].lower()

    scan = next(
        step for step in steps if step["name"] == "Run complete Gitleaks history"
    )
    assert scan["run"] == "python scripts/quality/gitleaks_ci.py"
    assert scan["env"]["GITLEAKS_EVENT_NAME"] == "${{ github.event_name }}"
    assert scan["env"]["GITLEAKS_BASE_SHA"] == (
        "${{ github.event_name == 'pull_request' && "
        "github.event.pull_request.base.sha || github.event.before }}"
    )
    assert scan["env"]["GITLEAKS_EVENT_HEAD_SHA"] == (
        "${{ github.event_name == 'pull_request' && "
        "github.event.pull_request.head.sha || github.event.after }}"
    )
    assert scan["env"]["GITLEAKS_REPORT_PATH"] == (
        "${{ runner.temp }}/gitleaks-results/results.sarif"
    )
    assert scan["env"]["GITLEAKS_BIN"] == "${{ runner.temp }}/gitleaks-bin/gitleaks"

    upload = next(
        step for step in steps if step["name"] == "Upload redacted Gitleaks SARIF"
    )
    assert upload["if"] == "${{ always() }}"
    assert upload["uses"] == UPLOAD_ARTIFACT_ACTION
    assert upload["with"]["name"] == "gitleaks-results.sarif"
    assert upload["with"]["path"] == (
        "${{ runner.temp }}/gitleaks-results/results.sarif"
    )
    assert upload["with"]["if-no-files-found"] == "warn"
    assert all(
        not step.get("uses", "").startswith("gitleaks/gitleaks-action@")
        for step in steps
    )


def test_pr_scan_covers_complete_graph_and_merge_resolution_delta(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    plan = prepare_scan(
        repo, _pull_request_environment(base_sha, head_sha, checkout_sha, repo)
    )

    count = int(_git(repo, "rev-list", "--count", f"{base_sha}..{head_sha}").stdout)
    assert count > 30
    assert plan.git_log_opts == f"{base_sha}..{head_sha} --diff-merges=first-parent"
    assert "--first-parent" not in plan.git_log_opts.split()
    assert "--no-merges" not in plan.git_log_opts.split()

    merge_aware_log = _git(
        repo,
        "log",
        "-p",
        "-U0",
        *plan.git_log_opts.split(),
    ).stdout
    assert SYNTHETIC_RESOLUTION_MARKER in merge_aware_log

    default_merge_log = _git(
        repo,
        "-c",
        "log.diffMerges=off",
        "log",
        "-p",
        "-U0",
        f"{base_sha}..{head_sha}",
    ).stdout
    assert SYNTHETIC_RESOLUTION_MARKER not in default_merge_log


def test_pr_scan_rejects_checkout_tree_drift_and_dirty_worktree(tmp_path: Path) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    env = _pull_request_environment(base_sha, head_sha, checkout_sha, repo)

    (repo / "uncommitted.txt").write_text("uncommitted\n", encoding="utf-8")
    with pytest.raises(GitleaksGateError, match="working tree"):
        prepare_scan(repo, env)

    _git(repo, "checkout", "--", ".")
    (repo / "uncommitted.txt").unlink(missing_ok=True)
    _git(repo, "switch", "--detach", head_sha)
    (repo / "checkout-only.txt").write_text("merge-only content\n", encoding="utf-8")
    _git(repo, "add", "checkout-only.txt")
    drifted_tree = _git(repo, "write-tree").stdout.strip()
    drifted_sha = _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit-tree",
        drifted_tree,
        "-p",
        base_sha,
        "-p",
        head_sha,
        "-m",
        "checkout content drift",
    ).stdout.strip()
    _git(repo, "switch", "--detach", drifted_sha)

    with pytest.raises(GitleaksGateError, match="tree"):
        prepare_scan(
            repo, _pull_request_environment(base_sha, head_sha, drifted_sha, repo)
        )


def test_pr_scan_rejects_reordered_synthetic_merge_parents(tmp_path: Path) -> None:
    repo, base_sha, head_sha, _ = _create_pull_request_graph(tmp_path)
    head_tree = _git(repo, "rev-parse", f"{head_sha}^{{tree}}").stdout.strip()
    reversed_checkout = _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "commit-tree",
        head_tree,
        "-p",
        head_sha,
        "-p",
        base_sha,
        "-m",
        "reversed synthetic parents",
    ).stdout.strip()
    _git(repo, "switch", "--detach", reversed_checkout)
    event = _pull_request_environment(base_sha, head_sha, reversed_checkout, repo)

    with pytest.raises(GitleaksGateError, match="parents"):
        prepare_scan(repo, event)


def test_push_scan_requires_nonzero_ancestor_before_and_exact_checkout(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha, synthetic_checkout = _create_pull_request_graph(tmp_path)
    _git(repo, "switch", "--detach", head_sha)
    valid_env = {
        "GITLEAKS_EVENT_NAME": "push",
        "GITLEAKS_BASE_SHA": base_sha,
        "GITLEAKS_EVENT_HEAD_SHA": head_sha,
        "GITHUB_SHA": head_sha,
        "GITHUB_WORKSPACE": str(repo),
    }
    plan = prepare_scan(repo, valid_env)
    assert plan.base_sha == base_sha
    assert plan.event_head_sha == head_sha

    with pytest.raises(GitleaksGateError, match="commit"):
        prepare_scan(
            repo,
            {
                **valid_env,
                "GITLEAKS_BASE_SHA": "0" * 40,
            },
        )

    with pytest.raises(GitleaksGateError, match="ancestor"):
        prepare_scan(
            repo,
            {
                **valid_env,
                "GITLEAKS_BASE_SHA": synthetic_checkout,
            },
        )

    with pytest.raises(GitleaksGateError, match="checkout"):
        prepare_scan(
            repo,
            {
                **valid_env,
                "GITHUB_SHA": base_sha,
            },
        )


def test_scan_command_uses_exact_range_redaction_and_sarif_report(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    plan = prepare_scan(
        repo, _pull_request_environment(base_sha, head_sha, checkout_sha, repo)
    )
    report_path = tmp_path / "reports" / "results.sarif"
    argv = build_gitleaks_command(Path(tmp_path / "gitleaks"), repo, plan, report_path)

    assert argv[0] == str(tmp_path / "gitleaks")
    assert argv[1] == "git"
    assert "--redact=100" in argv
    assert "--report-format=sarif" in argv
    assert f"--report-path={report_path}" in argv
    assert "--exit-code=2" in argv
    log_opts = argv[argv.index("--log-opts") + 1]
    assert log_opts == f"{base_sha}..{head_sha} --diff-merges=first-parent"
    invalid_plan = gitleaks_ci.ScanPlan(
        event_name=plan.event_name,
        base_sha=base_sha,
        event_head_sha=head_sha,
        git_log_opts=f"{base_sha}..{head_sha} --diff-merges=first-parent --all",
    )
    with pytest.raises(GitleaksGateError, match="validated plan"):
        build_gitleaks_command(
            Path(tmp_path / "gitleaks"), repo, invalid_plan, report_path
        )


def test_workflow_security_policy_guard_keeps_read_only_pull_request_scope() -> None:
    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    policy_guard = next(
        step
        for step in workflow["jobs"]["gitleaks"]["steps"]
        if step["name"] == "Verify security policy inputs against protected base"
    )
    assert policy_guard["if"] == "${{ github.event_name == 'pull_request' }}"
    assert 'git fetch --no-tags origin "$BASE_SHA"' in policy_guard["run"]
    assert "--depth=" not in policy_guard["run"]
    assert 'BASE_REPOSITORY" != "$GITHUB_REPOSITORY' in policy_guard["run"]
    assert 'PR_AUTHOR" != "egorribun' in policy_guard["run"]


def test_gitleaks_runner_entrypoint_is_an_owner_protected_policy_input() -> None:
    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["gitleaks"]["steps"]
    policy_guard = next(
        step
        for step in steps
        if step["name"] == "Verify security policy inputs against protected base"
    )
    scan_step = next(
        step for step in steps if step["name"] == "Run complete Gitleaks history"
    )

    runner_path = "scripts/quality/gitleaks_ci.py"
    assert scan_step["run"] == f"python {runner_path}"
    assert f'"{runner_path}"' in policy_guard["run"]
    assert 'for path in "${policy_paths[@]}"; do' in policy_guard["run"]
    assert 'git diff --quiet "$BASE_SHA" -- "$path"' in policy_guard["run"]
    assert 'if [[ "$PR_AUTHOR" != "egorribun" ]]' in policy_guard["run"]


def test_prepare_scan_uses_closed_git_calls_and_external_isolated_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    event = {
        **_pull_request_environment(base_sha, head_sha, checkout_sha, repo),
        "UNAPPROVED_ENVIRONMENT_VALUE": "synthetic-environment-sentinel",
    }
    real_spawn = asyncio.create_subprocess_exec
    real_wait_for = asyncio.wait_for
    calls: list[dict[str, object]] = []
    waits: list[float | None] = []

    async def observe_spawn(
        *args: object, **kwargs: object
    ) -> asyncio.subprocess.Process:
        command = args
        if command and command[0] == "git":
            calls.append(kwargs)
        return await real_spawn(*args, **kwargs)

    async def observe_wait_for(
        awaitable: object, timeout: float | None = None
    ) -> object:
        waits.append(timeout)
        return await real_wait_for(awaitable, timeout=timeout)

    monkeypatch.setattr(gitleaks_ci.asyncio, "create_subprocess_exec", observe_spawn)
    monkeypatch.setattr(gitleaks_ci.asyncio, "wait_for", observe_wait_for)
    prepare_scan(repo, event)

    assert calls
    assert waits and all(wait is not None and 0 < wait <= 10 for wait in waits)
    for call in calls:
        assert call["stdin"] is asyncio.subprocess.DEVNULL
        assert call["stdout"] is asyncio.subprocess.PIPE
        assert call["stderr"] is asyncio.subprocess.DEVNULL
        environment = call["env"]
        assert isinstance(environment, dict)
        config_path = Path(environment["GIT_CONFIG_GLOBAL"])
        assert config_path.is_absolute()
        assert not config_path.is_relative_to(repo.resolve())
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert "UNAPPROVED_ENVIRONMENT_VALUE" not in environment


def test_execute_scan_runs_quietly_with_deadline_and_validates_redacted_sarif(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    report_path = tmp_path / "runner-temp" / "gitleaks-results" / "results.sarif"
    binary = tmp_path / "runner-temp" / "gitleaks-bin" / "gitleaks"
    event = {
        **_pull_request_environment(base_sha, head_sha, checkout_sha, repo),
        "GITLEAKS_REPORT_PATH": str(report_path),
        "GITLEAKS_BIN": str(binary),
        "UNAPPROVED_ENVIRONMENT_VALUE": "synthetic-environment-sentinel",
        "PRIVATE_TEST_SENTINEL": "private-test-sentinel",
    }
    observed: dict[str, object] = {}

    def fake_scan(
        command: list[str],
        environment: dict[str, str],
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> SimpleNamespace:
        observed["command"] = command
        observed["environment"] = environment
        observed["timeout_seconds"] = timeout_seconds
        observed["cwd"] = cwd
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            '{"version":"2.1.0","runs":[{"results":[]}]}', encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(gitleaks_ci, "_run_silent", fake_scan)
    assert execute_scan(event) == 0

    command = observed["command"]
    assert isinstance(command, list)
    assert "--redact=100" in command
    assert observed["timeout_seconds"] == 960
    assert observed["cwd"] == repo.resolve()
    scan_environment = observed["environment"]
    assert isinstance(scan_environment, dict)
    assert "UNAPPROVED_ENVIRONMENT_VALUE" not in scan_environment
    assert "PRIVATE_TEST_SENTINEL" not in scan_environment
    assert Path(scan_environment["GIT_CONFIG_GLOBAL"]).is_absolute()


def test_gitleaks_rejects_sarif_output_inside_source_checkout(tmp_path: Path) -> None:
    repo, base_sha, head_sha, checkout_sha = _create_pull_request_graph(tmp_path)
    plan = prepare_scan(
        repo, _pull_request_environment(base_sha, head_sha, checkout_sha, repo)
    )
    with pytest.raises(GitleaksGateError, match="outside the checkout"):
        build_gitleaks_command(
            tmp_path / "gitleaks", repo, plan, repo / "results.sarif"
        )


def _advance_base_and_merge_pull_request(
    repo: Path, event_head_sha: str
) -> tuple[str, str]:
    """Create a non-conflicting base advance and the resulting merge checkout."""

    _git(repo, "switch", "main")
    (repo / "base-only-advance.txt").write_text("base advance\n", encoding="utf-8")
    _git(repo, "add", "base-only-advance.txt")
    _commit(repo, "advance base only")
    advanced_base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "switch", "--detach", advanced_base)
    _git(
        repo,
        "-c",
        "user.name=Contract Test",
        "-c",
        "user.email=contract@example.invalid",
        "merge",
        "--no-ff",
        "-m",
        "advanced-base checkout merge",
        event_head_sha,
    )
    checkout = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return advanced_base, checkout


def test_depth_one_base_fetch_adds_shared_ancestors_to_difference_range(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-root"
    source_root.mkdir()
    source, original_base_sha, event_head, _ = _create_pull_request_graph(source_root)
    base_sha, checkout_sha = _advance_base_and_merge_pull_request(source, event_head)
    _git(source, "branch", "synthetic-merge-checkout", checkout_sha)

    remote = tmp_path / "origin.git"
    full_clone = tmp_path / "full-clone"
    _git(source, "clone", "--bare", str(source), str(remote))
    _git(
        source,
        "clone",
        "-c",
        "core.autocrlf=false",
        "--no-local",
        str(remote),
        str(full_clone),
    )
    _git(full_clone, "switch", "--detach", checkout_sha)

    assert _git(full_clone, "rev-parse", "--is-shallow-repository").stdout.strip() == (
        "false"
    )
    full_range = set(
        _git(full_clone, "rev-list", f"{base_sha}..{event_head}").stdout.splitlines()
    )
    _git(full_clone, "fetch", "--no-tags", "--depth=1", "origin", base_sha)

    assert _git(full_clone, "rev-parse", "--is-shallow-repository").stdout.strip() == (
        "true"
    )
    shallow_range = set(
        _git(full_clone, "rev-list", f"{base_sha}..{event_head}").stdout.splitlines()
    )
    assert original_base_sha not in full_range
    assert original_base_sha in shallow_range
    assert len(shallow_range - full_range) >= 4


def test_prepare_scan_refuses_a_checkout_made_shallow_by_base_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source-root"
    source_root.mkdir()
    source, base_sha, event_head, checkout_sha = _create_pull_request_graph(source_root)
    _git(source, "branch", "synthetic-merge-checkout", checkout_sha)

    remote = tmp_path / "origin.git"
    full_clone = tmp_path / "full-clone"
    _git(source, "clone", "--bare", str(source), str(remote))
    _git(
        source,
        "clone",
        "-c",
        "core.autocrlf=false",
        "--no-local",
        str(remote),
        str(full_clone),
    )
    _git(full_clone, "switch", "--detach", checkout_sha)
    event = _pull_request_environment(base_sha, event_head, checkout_sha, full_clone)

    assert _git(full_clone, "rev-parse", "--is-shallow-repository").stdout.strip() == (
        "false"
    )
    prepare_scan(full_clone, event)
    _git(full_clone, "fetch", "--no-tags", "--depth=1", "origin", base_sha)
    assert _git(full_clone, "rev-parse", "--is-shallow-repository").stdout.strip() == (
        "true"
    )

    scanner_calls: list[list[str]] = []

    def unexpected_scan(
        command: list[str],
        environment: dict[str, str],
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> SimpleNamespace:
        scanner_calls.append(command)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(gitleaks_ci, "_run_silent", unexpected_scan)
    with pytest.raises(GitleaksGateError, match="shallow"):
        prepare_scan(full_clone, event)
    with pytest.raises(GitleaksGateError, match="shallow"):
        execute_scan(
            {
                **event,
                "GITLEAKS_REPORT_PATH": str(tmp_path / "report.sarif"),
                "GITLEAKS_BIN": str(tmp_path / "gitleaks"),
            }
        )
    assert scanner_calls == []


def test_pr_scan_rejects_base_advanced_merge_before_scanner_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, event_head, _ = _create_pull_request_graph(tmp_path)
    base_sha, checkout_sha = _advance_base_and_merge_pull_request(repo, event_head)
    report_path = tmp_path / "runner-temp" / "results.sarif"
    event = {
        **_pull_request_environment(base_sha, event_head, checkout_sha, repo),
        "GITLEAKS_REPORT_PATH": str(report_path),
        "GITLEAKS_BIN": str(tmp_path / "runner-temp" / "gitleaks"),
        "PRIVATE_TEST_SENTINEL": "private-synthetic-marker",
    }
    scanner_calls: list[object] = []
    monkeypatch.setattr(
        gitleaks_ci,
        "_run_silent",
        lambda *args, **kwargs: scanner_calls.append((args, kwargs)),
    )

    with pytest.raises(
        GitleaksGateError,
        match="merge current base into PR branch before scanning",
    ) as error:
        execute_scan(event)

    assert scanner_calls == []
    assert str(repo) not in str(error.value)
    assert "private-synthetic-marker" not in str(error.value)


def _linux_process_identity(pid: int) -> tuple[str, int, int] | None:
    status_path = Path("/proc") / str(pid) / "stat"
    try:
        fields = status_path.read_text(encoding="ascii").rsplit(") ", 1)[1].split()
    except FileNotFoundError:
        return None
    return fields[0], int(fields[2]), int(fields[19])


def _assert_scan_timeout_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix":
        spawn_attempts: list[object] = []

        async def unexpected_spawn(*args: object, **kwargs: object) -> None:
            spawn_attempts.append((args, kwargs))
            raise AssertionError("unsupported scanner platform must fail before spawn")

        monkeypatch.setattr(
            gitleaks_ci.asyncio, "create_subprocess_exec", unexpected_spawn
        )
        with pytest.raises(
            GitleaksGateError, match="Gitleaks process-group cleanup is unavailable"
        ):
            asyncio.run(
                gitleaks_ci._spawn_and_collect(
                    [sys.executable, "-c", "pass"],
                    {"PATH": os.environ.get("PATH", "")},
                    timeout_seconds=1,
                    max_stdout_bytes=None,
                    require_process_group_cleanup=True,
                )
            )
        assert spawn_attempts == []
        return

    if sys.platform != "linux":
        spawned: list[dict[str, object]] = []
        original_spawn = asyncio.create_subprocess_exec

        async def capture_spawn(
            *args: object, **kwargs: object
        ) -> asyncio.subprocess.Process:
            spawned.append(dict(kwargs))
            return await original_spawn(*args, **kwargs)

        monkeypatch.setattr(
            gitleaks_ci.asyncio, "create_subprocess_exec", capture_spawn
        )
        result = asyncio.run(
            gitleaks_ci._spawn_and_collect(
                [sys.executable, "-c", "pass"],
                {"PATH": os.environ.get("PATH", "")},
                timeout_seconds=2,
                max_stdout_bytes=None,
                require_process_group_cleanup=True,
            )
        )
        assert result.returncode == 0
        assert len(spawned) == 1
        assert spawned[0].get("start_new_session") is True
        return

    child_record = tmp_path / "child-process.txt"
    child_code = (
        "import os, signal, sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "with open('/proc/self/stat', encoding='ascii') as stat:\n"
        "    stat_fields = stat.read().rsplit(') ', 1)[1].split()\n"
        "with open(sys.argv[1], 'w', encoding='ascii') as record:\n"
        "    record.write(f'{os.getpid()} {os.getpgid(0)} {stat_fields[19]}\\n')\n"
        "print('descendant-ready', flush=True)\n"
        "signal.pause()\n"
    )
    parent_code = (
        "import signal, subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, {str(child_record)!r}]); "
        "signal.pause()"
    )
    command = [sys.executable, "-c", parent_code]
    environment = {"PATH": os.environ.get("PATH", "")}
    original_spawn = asyncio.create_subprocess_exec
    spawned: list[tuple[asyncio.subprocess.Process, dict[str, object]]] = []

    async def exercise_ready_process_group() -> float:
        # Interpreter startup is fixture setup, not the timeout-cleanup budget.
        # Use a real isolated group and a readiness record, never a fixed sleep.
        process = await original_spawn(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )
        try:
            assert process.stdout is not None
            readiness = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            assert readiness == b"descendant-ready\n"
            assert process.returncode is None
            assert os.getsid(process.pid) == process.pid
            ready_pid, ready_group, ready_start = map(
                int, child_record.read_text(encoding="ascii").split()
            )
            assert ready_group == process.pid
            ready_identity = _linux_process_identity(ready_pid)
            assert ready_identity is not None
            assert ready_identity[0] != "Z"
            assert ready_identity[1:] == (ready_group, ready_start)

            async def capture_spawn(
                *args: object, **kwargs: object
            ) -> asyncio.subprocess.Process:
                # Exercise production timeout/cleanup on this ready real group.
                # The production launch request must still match its contract.
                assert args == tuple(command)
                assert kwargs.get("env") == environment
                assert kwargs.get("start_new_session") is True
                assert kwargs.get("stdin") is asyncio.subprocess.DEVNULL
                assert kwargs.get("stdout") is asyncio.subprocess.DEVNULL
                assert kwargs.get("stderr") is asyncio.subprocess.DEVNULL
                spawned.append((process, dict(kwargs)))
                return process

            monkeypatch.setattr(
                gitleaks_ci.asyncio, "create_subprocess_exec", capture_spawn
            )
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                await gitleaks_ci._spawn_and_collect(
                    command,
                    environment,
                    timeout_seconds=1,
                    max_stdout_bytes=None,
                    require_process_group_cleanup=True,
                )
            elapsed = time.monotonic() - started
            # Observe production's result before fixture rescue can repair it.
            assert process.returncode is not None, (
                "production did not reap scanner leader"
            )
            return elapsed
        finally:
            # Setup can fail before production owns the process. Kill only
            # while this direct child is unreaped, then bound its reap as well.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.wait_for(process.wait(), timeout=1)

    try:
        elapsed = asyncio.run(exercise_ready_process_group())
        assert elapsed < 3
        assert len(spawned) == 1
        process, spawn_kwargs = spawned[0]
        assert spawn_kwargs.get("start_new_session") is True
        assert process.returncode is not None
        child_pid_text, child_group_text, child_start_text = child_record.read_text(
            encoding="ascii"
        ).split()
        child_pid = int(child_pid_text)
        child_group = int(child_group_text)
        child_start_time = int(child_start_text)
        assert child_group == process.pid
        child_deadline = time.monotonic() + 0.5
        pidfd: int | None = None
        try:
            try:
                pidfd = os.pidfd_open(child_pid, 0)
            except ProcessLookupError:
                pass
            else:
                with selectors.DefaultSelector() as selector:
                    selector.register(pidfd, selectors.EVENT_READ)
                    remaining = child_deadline - time.monotonic()
                    assert remaining > 0
                    assert selector.select(remaining)
            child_identity = _linux_process_identity(child_pid)
            assert child_identity is None or child_identity == (
                "Z",
                child_group,
                child_start_time,
            )
        finally:
            if pidfd is not None:
                os.close(pidfd)
    finally:
        if child_record.exists():
            child_pid_text, child_group_text, child_start_text = child_record.read_text(
                encoding="ascii"
            ).split()
            child_pid = int(child_pid_text)
            child_group = int(child_group_text)
            child_start_time = int(child_start_text)
            child_identity = _linux_process_identity(child_pid)
            if child_identity is not None and child_identity != (
                "Z",
                child_group,
                child_start_time,
            ):
                assert child_identity[1:] == (child_group, child_start_time)
                try:
                    pidfd = os.pidfd_open(child_pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    try:
                        current_identity = _linux_process_identity(child_pid)
                        if current_identity == child_identity:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                            with selectors.DefaultSelector() as selector:
                                selector.register(pidfd, selectors.EVENT_READ)
                                assert selector.select(0.5)
                    except ProcessLookupError:
                        pass
                    finally:
                        os.close(pidfd)


def test_scan_timeout_kills_descendant_or_rejects_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assert_scan_timeout_contract(tmp_path, monkeypatch)


def test_scan_timeout_contract_rejects_disabled_production_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix" or sys.platform != "linux":
        _assert_scan_timeout_contract(tmp_path, monkeypatch)
        return

    cleanup_calls: list[int] = []

    async def ignore_cleanup(process: asyncio.subprocess.Process) -> bool:
        cleanup_calls.append(process.pid)
        return True

    monkeypatch.setattr(gitleaks_ci, "_terminate_and_reap", ignore_cleanup)
    with pytest.raises(AssertionError, match="production did not reap scanner leader"):
        _assert_scan_timeout_contract(tmp_path, monkeypatch)
    assert len(cleanup_calls) == 1


def test_scan_cleanup_bounds_unconfirmed_direct_child_reap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NeverReapedProcess:
        pid = 424242
        returncode = None
        killed = False
        terminated = False

        async def wait(self) -> int:
            await asyncio.Event().wait()
            return 0

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    signals: list[tuple[int, int]] = []
    if os.name == "posix":
        monkeypatch.setattr(
            gitleaks_ci.os,
            "killpg",
            lambda pid, sig: signals.append((pid, sig)),
        )
    monkeypatch.setattr(gitleaks_ci, "_TERMINATION_TERM_GRACE_SECONDS", 0.01)
    monkeypatch.setattr(gitleaks_ci, "_TERMINATION_REAP_TIMEOUT_SECONDS", 0.05)
    process = NeverReapedProcess()
    started = time.monotonic()

    reaped = asyncio.run(gitleaks_ci._terminate_and_reap(process))

    assert reaped is False
    if os.name == "posix":
        assert [sig for _, sig in signals] == [signal.SIGKILL]
        assert process.terminated is False
        assert process.killed is False
    else:
        assert signals == []
        assert process.terminated is True
        assert process.killed is True
    assert time.monotonic() - started < 0.5


def test_scan_cleanup_does_not_signal_after_leader_is_already_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AlreadyReapedProcess:
        pid = 424242
        returncode = 0
        signal_calls = 0
        wait_calls = 0

        async def wait(self) -> int:
            self.wait_calls += 1
            return 0

        def terminate(self) -> None:
            self.signal_calls += 1

        def kill(self) -> None:
            self.signal_calls += 1

    group_signals: list[tuple[int, int]] = []
    if os.name == "posix":
        monkeypatch.setattr(
            gitleaks_ci.os,
            "killpg",
            lambda pid, sig: group_signals.append((pid, sig)),
        )
    process = AlreadyReapedProcess()

    cleanup_confirmed = asyncio.run(gitleaks_ci._terminate_and_reap(process))

    assert cleanup_confirmed is False
    assert process.signal_calls == 0
    assert process.wait_calls == 0
    assert group_signals == []


@pytest.fixture(scope="module")
def diagnostic_graph(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, str, str, str]:
    return _create_pull_request_graph(tmp_path_factory.mktemp("gitleaks-diagnostics"))


@pytest.fixture
def diagnostic_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    diagnostic_graph: tuple[Path, str, str, str],
):
    """Keep graph validation real; replace only the external scanner process."""
    repo, base_sha, head_sha, checkout_sha = diagnostic_graph
    report_path = tmp_path / "reports" / "results.sarif"
    event = {
        **_pull_request_environment(base_sha, head_sha, checkout_sha, repo),
        "GITLEAKS_REPORT_PATH": str(report_path),
        "GITLEAKS_BIN": str(tmp_path / "scanner"),
    }
    for name, value in event.items():
        monkeypatch.setenv(name, value)

    state: dict[str, object] = {}

    def fake_scan(
        command: list[str],
        environment: dict[str, str],
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> SimpleNamespace:
        assert cwd == repo.resolve()
        assert "--redact=100" in command
        assert "--exit-code=2" in command
        assert timeout_seconds == 960
        assert "GITHUB_TOKEN" not in environment
        error = state.get("error")
        if error is not None:
            raise error
        report = state["report"]
        if report is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report), encoding="utf-8")
        return SimpleNamespace(returncode=state["returncode"], stdout="")

    monkeypatch.setattr(gitleaks_ci, "_run_silent", fake_scan)

    def invoke(
        report: object,
        returncode: int = 2,
        error: GitleaksGateError | None = None,
    ) -> int:
        report_path.unlink(missing_ok=True)
        state.update(report=report, returncode=returncode, error=error)
        return gitleaks_ci.main()

    return invoke


def _diagnostic_result(index: int = 7) -> dict[str, object]:
    """Match the pinned SARIF field names, never scanner secret values."""
    marker = "synthetic-private-diagnostic-marker"
    return {
        "ruleId": "generic-api-key",
        "message": {"text": marker},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "tests/synthetic_case.py"},
                    "region": {
                        "startLine": index,
                        "endLine": index,
                        "startColumn": 1,
                        "endColumn": 9,
                        "snippet": {"text": marker},
                    },
                }
            }
        ],
        "partialFingerprints": {
            "commitSha": "1" * 40,
            "author": marker,
            "email": marker,
            "commitMessage": marker,
            "date": marker,
            "arbitraryFingerprint": marker,
        },
        "properties": {"tags": [marker]},
        "match": marker,
        "secret": marker,
    }


def _diagnostic_report(
    results: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "gitleaks",
                        "semanticVersion": "8.30.1",
                        "informationUri": "https://github.com/gitleaks/gitleaks",
                        "rules": [],
                    }
                },
                "results": results,
            }
        ],
    }


def _read_diagnostic(captured: pytest.CaptureResult[str]) -> dict[str, object]:
    lines = (captured.out + captured.err).splitlines()
    prefix = "GITLEAKS_DIAGNOSTIC "
    summaries = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
    assert len(summaries) == 1, "one bounded non-sensitive diagnostic is required"
    summary = json.loads(summaries[0])
    assert isinstance(summary, dict)
    return summary


def test_findings_diagnostic_preserves_failure_and_omits_all_report_content(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    assert diagnostic_scan(_diagnostic_report([_diagnostic_result()])) == 2

    captured = capsys.readouterr()
    assert "synthetic-private-diagnostic-marker" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {
        "status": "findings",
        "scanner_exit_code": 2,
        "result_count": 1,
        "identities": [
            {
                "rule_id": "generic-api-key",
                "path": "tests/synthetic_case.py",
                "line": 7,
                "commit": "1" * 40,
            }
        ],
        "omitted_identity_count": 0,
    }


def test_clean_diagnostic_preserves_zero_exit(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    assert diagnostic_scan(_diagnostic_report([]), returncode=0) == 0

    assert _read_diagnostic(capsys.readouterr()) == {
        "status": "clean",
        "scanner_exit_code": 0,
        "result_count": 0,
        "identities": [],
        "omitted_identity_count": 0,
    }


@pytest.mark.parametrize("commit_case", ["absent", "empty"])
def test_diagnostic_never_substitutes_arbitrary_fingerprints_for_missing_commit(
    diagnostic_scan,
    capsys: pytest.CaptureFixture[str],
    commit_case: str,
) -> None:
    result = _diagnostic_result()
    if commit_case == "absent":
        del result["partialFingerprints"]
    else:
        result["partialFingerprints"]["commitSha"] = ""

    assert diagnostic_scan(_diagnostic_report([result])) == 2

    captured = capsys.readouterr()
    assert "synthetic-private-diagnostic-marker" not in captured.out + captured.err
    assert _read_diagnostic(captured)["identities"] == [
        {
            "rule_id": "generic-api-key",
            "path": "tests/synthetic_case.py",
            "line": 7,
        }
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rule", ""),
        ("rule", None),
        ("rule", "generic api key"),
        ("rule", "generic.api-key"),
        ("rule", "/unsafe-rule"),
        ("rule", "generic-api-key\n::error::synthetic-injection"),
        ("rule", "x" * 129),
        ("path", None),
        ("path", ""),
        ("path", "tests/source name.py"),
        ("path", "tests/é.py"),
        ("path", "/absolute/source.py"),
        ("path", "../outside.py"),
        ("path", "tests/../outside.py"),
        ("path", "tests/./source.py"),
        ("path", "tests//source.py"),
        ("path", r"tests\source.py"),
        ("path", "https://example.invalid/source.py"),
        ("path", "tests/%2e%2e/source.py"),
        ("path", "tests/source.py\n::error::synthetic-injection"),
        ("path", "x" * 513),
        ("line", 0),
        ("line", -1),
        ("line", True),
        ("line", "7"),
        ("line", 2**31),
        ("commit", "not-an-immutable-commit"),
        ("commit", "a" * 39),
        ("commit", "a" * 41),
        ("commit", "a" * 40 + "\n"),
        ("commit", 7),
    ],
)
def test_malformed_diagnostic_identity_fails_closed_without_partial_output(
    diagnostic_scan,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    result = _diagnostic_result()
    location = result["locations"][0]["physicalLocation"]
    if field == "rule":
        result["ruleId"] = value
    elif field == "path":
        location["artifactLocation"]["uri"] = value
    elif field == "line":
        location["region"]["startLine"] = value
    else:
        result["partialFingerprints"]["commitSha"] = value

    # A valid result before the malformed one must not be partially printed.
    report = _diagnostic_report([_diagnostic_result(), result])
    assert diagnostic_scan(report) == 1

    captured = capsys.readouterr()
    assert "synthetic-private-diagnostic-marker" not in captured.out + captured.err
    assert "synthetic-injection" not in captured.out + captured.err
    assert "tests/synthetic_case.py" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


@pytest.mark.parametrize(
    "shape",
    [
        "run_not_object",
        "later_run_not_object",
        "results_not_list",
        "result_not_object",
        "locations_empty",
        "locations_not_list",
        "location_not_object",
        "physical_location_not_object",
        "region_not_object",
        "artifact_location_missing",
        "artifact_location_not_object",
        "line_missing",
        "fingerprints_not_object",
    ],
)
def test_malformed_diagnostic_structure_is_never_reported_as_clean(
    diagnostic_scan, capsys: pytest.CaptureFixture[str], shape: str
) -> None:
    result = _diagnostic_result()
    report = _diagnostic_report([result])
    if shape == "run_not_object":
        report["runs"] = [None]
    elif shape == "later_run_not_object":
        report["runs"].append(None)
    elif shape == "results_not_list":
        report["runs"][0]["results"] = "synthetic-malformed-report"
    elif shape == "result_not_object":
        report["runs"][0]["results"] = [None]
    elif shape == "locations_empty":
        result["locations"] = []
    elif shape == "locations_not_list":
        result["locations"] = {}
    elif shape == "location_not_object":
        result["locations"] = [None]
    elif shape == "physical_location_not_object":
        result["locations"][0]["physicalLocation"] = None
    elif shape == "region_not_object":
        result["locations"][0]["physicalLocation"]["region"] = None
    elif shape == "artifact_location_missing":
        del result["locations"][0]["physicalLocation"]["artifactLocation"]
    elif shape == "artifact_location_not_object":
        result["locations"][0]["physicalLocation"]["artifactLocation"] = None
    elif shape == "line_missing":
        del result["locations"][0]["physicalLocation"]["region"]["startLine"]
    else:
        result["partialFingerprints"] = []

    assert diagnostic_scan(report, returncode=0) == 1

    captured = capsys.readouterr()
    assert "synthetic-malformed-report" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


def test_diagnostic_caps_output_but_counts_every_valid_identity(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    results = [_diagnostic_result(index) for index in range(1, 101)]
    for result in results:
        result["ruleId"] = "r" * 128
        location = result["locations"][0]["physicalLocation"]
        location["artifactLocation"]["uri"] = "p" * 512
    assert diagnostic_scan(_diagnostic_report(results)) == 2

    captured = capsys.readouterr()
    summary = _read_diagnostic(captured)
    assert summary["status"] == "findings"
    assert summary["result_count"] == 100
    assert len(summary["identities"]) == 25
    assert summary["omitted_identity_count"] == 75
    assert len((captured.out + captured.err).encode("utf-8")) <= 32 * 1024
    assert "synthetic-private-diagnostic-marker" not in captured.out + captured.err


def test_diagnostic_validates_even_identities_past_output_cap(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    results = [_diagnostic_result(index) for index in range(1, 27)]
    results[-1]["locations"][0]["physicalLocation"]["region"]["startLine"] = False

    assert diagnostic_scan(_diagnostic_report(results)) == 1

    captured = capsys.readouterr()
    assert "tests/synthetic_case.py" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


@pytest.mark.parametrize("scanner_exit", [1, 3, -9])
def test_scanner_errors_stay_failed_without_printing_report_metadata(
    diagnostic_scan, capsys: pytest.CaptureFixture[str], scanner_exit: int
) -> None:
    assert (
        diagnostic_scan(
            _diagnostic_report([_diagnostic_result()]), returncode=scanner_exit
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "synthetic-private-diagnostic-marker" not in captured.out + captured.err
    assert "tests/synthetic_case.py" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


def test_gate_error_diagnostic_never_prints_exception_details(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        diagnostic_scan(
            None,
            error=GitleaksGateError("synthetic-private-exception-details"),
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "synthetic-private-exception-details" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


def test_missing_report_still_fails_with_only_fixed_diagnostic(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    assert diagnostic_scan(None) == 1

    assert _read_diagnostic(capsys.readouterr()) == {"status": "gate_error"}


@pytest.mark.parametrize("topology", ["multiple_runs", "multiple_locations"])
def test_diagnostic_rejects_topology_outside_pinned_scanner_schema(
    diagnostic_scan, capsys: pytest.CaptureFixture[str], topology: str
) -> None:
    result = _diagnostic_result()
    report = _diagnostic_report([result])
    if topology == "multiple_runs":
        report["runs"].append(_diagnostic_report([_diagnostic_result(9)])["runs"][0])
    else:
        result["locations"].append(_diagnostic_result(8)["locations"][0])

    assert diagnostic_scan(report) == 1

    captured = capsys.readouterr()
    assert "tests/synthetic_case.py" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


def test_diagnostic_rejects_malformed_later_location_before_any_output(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _diagnostic_result()
    invalid = _diagnostic_result(8)["locations"][0]
    invalid["physicalLocation"]["artifactLocation"]["uri"] = "../outside.py"
    result["locations"].append(invalid)

    assert diagnostic_scan(_diagnostic_report([result])) == 1

    captured = capsys.readouterr()
    assert "tests/synthetic_case.py" not in captured.out + captured.err
    assert _read_diagnostic(captured) == {"status": "gate_error"}


def test_nonempty_results_cannot_be_reported_as_a_clean_scan(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    status = diagnostic_scan(_diagnostic_report([_diagnostic_result()]), returncode=0)
    assert status == 1

    assert _read_diagnostic(capsys.readouterr()) == {"status": "gate_error"}


def test_empty_report_cannot_turn_scanner_findings_exit_into_success(
    diagnostic_scan, capsys: pytest.CaptureFixture[str]
) -> None:
    assert diagnostic_scan(_diagnostic_report([]), returncode=2) == 2

    summary = _read_diagnostic(capsys.readouterr())
    assert summary["status"] == "findings"
    assert summary["scanner_exit_code"] == 2
    assert summary["result_count"] == 0
    assert summary["identities"] == []
