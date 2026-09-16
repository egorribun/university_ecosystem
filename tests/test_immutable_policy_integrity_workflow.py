"""Contracts for the base-branch security policy integrity workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "security-policy-integrity.yml"


def _workflow() -> dict[str, object]:
    loaded = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


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
