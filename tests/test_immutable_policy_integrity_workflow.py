"""Contracts for the base-branch security policy integrity workflow."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "security-policy-integrity.yml"


def _workflow() -> dict[str, object]:
    loaded = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _uses_unsupported_gh_api_option(source: str) -> bool:
    normalized = re.sub(r"\\\r?\n[ \t]*", " ", source)
    lexer = shlex.shlex(
        normalized,
        posix=True,
        punctuation_chars=";&|()\n",
    )
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"

    command: list[str] = []
    for token in lexer:
        if token and all(character in ";&|()\n" for character in token):
            if _gh_api_command_has_unsupported_option(command):
                return True
            command = []
        else:
            command.append(token)
    return _gh_api_command_has_unsupported_option(command)


def _gh_api_command_has_unsupported_option(command: list[str]) -> bool:
    for index in range(len(command) - 1):
        if command[index : index + 2] != ["gh", "api"]:
            continue
        if any(
            argument.partition("=")[0] == "--fail-with-body"
            for argument in command[index + 2 :]
        ):
            return True
    return False


def test_policy_integrity_runs_from_trusted_base_without_pr_code_execution() -> None:
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    target = triggers["pull_request_target"]
    assert target["branches"] == ["main"]
    assert set(target["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
        "edited",
    }
    assert workflow["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert workflow["concurrency"] == {
        "group": "security-policy-integrity-${{ github.event.pull_request.number }}",
        "cancel-in-progress": True,
    }

    jobs = workflow["jobs"]
    job = jobs["security-policy-integrity"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert job["timeout-minutes"] == 5
    assert all("uses" not in step for step in job["steps"])

    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "github.workflow_sha" in source
    assert '[[ "$WORKFLOW_SHA" == "$BASE_SHA" ]]' in source
    assert "gh api --paginate --slurp" in source
    assert "pulls/$PR_NUMBER/files?per_page=100" in source
    assert "repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER" in source
    assert ".base.sha == $base_sha" in source
    assert ".head.sha == $head_sha" in source
    assert "expected_changed_files" in source
    assert "enumerated_changed_files" in source
    assert "exceeds the GitHub API safety limit" in source
    assert ".previous_filename" in source
    assert "jq -e" in source
    assert "git checkout" not in source
    assert "actions/checkout" not in source
    assert "pull_request_target" in source


def test_policy_integrity_rechecks_when_pull_request_metadata_is_edited() -> None:
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    target = triggers["pull_request_target"]
    assert set(target["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
        "edited",
    }


def test_policy_integrity_uses_supported_gh_api_options() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")

    # `--fail-with-body` belongs to curl, not `gh api`; an unsupported flag
    # prevents this trusted-base security gate from reaching its policy checks.
    # Without `gh api`'s own nonzero failure status, strict mode is what keeps
    # an API error from being treated as an empty or incomplete policy result.
    assert "set -euo pipefail" in source
    assert not _uses_unsupported_gh_api_option(source)

    multiline_fixture = (
        "gh api \\\n  --paginate \\\n  --fail-with-body \\\n  /repos/example/repository"
    )
    assert _uses_unsupported_gh_api_option(multiline_fixture)
    assert not _uses_unsupported_gh_api_option(
        "curl --fail-with-body /repos/example/repository"
    )


def test_policy_integrity_protects_workflows_and_scanner_adapters() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    for protected_path in (
        ".github/workflows/*",
        "quality/*",
        "security/*",
        "scripts/osv_batch_audit.py",
        "scripts/check_dependency_audit_report.py",
        "scripts/quality/validate_semgrep_sarif.py",
        "frontend/package-lock.json",
        "uv.lock",
        "native/rust_ext/deny.toml",
    ):
        assert protected_path in source
    assert '"$PR_AUTHOR" != "egorribun"' in source
    assert "owner-authored" in source


def test_policy_integrity_protects_npm_lifecycle_inputs() -> None:
    """Package manifests and referenced install hooks are trusted inputs."""

    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    for protected_path in (
        "frontend/package.json",
        "frontend/.npmrc",
        "frontend/scripts/ensure-wasm.mjs",
        "frontend/scripts/setup-husky.cjs",
        "frontend/scripts/setup-lhci-binaries.cjs",
    ):
        assert protected_path in source
