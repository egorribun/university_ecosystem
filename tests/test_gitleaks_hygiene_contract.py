"""Regression contracts for repository secret-scanning coverage."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GITLEAKS_CONFIG_PATH = REPOSITORY_ROOT / ".gitleaks.toml"
GITLEAKS_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "gitleaks.yml"


def _workflow_triggers(workflow: dict[object, object]) -> dict[str, object]:
    """Support PyYAML's YAML 1.1 parsing of the ``on`` key as ``True``."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def test_gitleaks_allowlist_contains_only_existing_lockfile_paths() -> None:
    """Stale file and placeholder exceptions must not hide secret findings."""

    with GITLEAKS_CONFIG_PATH.open("rb") as config_file:
        allowlist = tomllib.load(config_file)["allowlist"]

    assert set(allowlist["paths"]) == {"uv.lock", "package-lock.json", "go.sum"}
    assert "files" not in allowlist
    assert "regexes" not in allowlist


def test_gitleaks_scans_main_pushes_and_pull_requests_without_duplicate_runs() -> None:
    """The protected branch and PR receive one authoritative scan each."""

    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert triggers["push"]["branches"] == ["main"]
    # ``pull_request.branches`` filters the base branch, so PRs into main stay
    # covered without duplicating the push scan on the source branch.
    assert triggers["pull_request"]["branches"] == ["main"]
