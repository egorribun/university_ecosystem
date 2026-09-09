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


def test_gitleaks_scans_main_and_active_development_branch_pushes() -> None:
    """Direct pushes to the maintained branch must receive the same scan."""

    workflow = yaml.safe_load(GITLEAKS_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert triggers["push"]["branches"] == ["main", "egorribun"]
    # ``pull_request.branches`` filters the base branch, so PRs into main stay
    # covered without duplicating scans for the active source branch.
    assert triggers["pull_request"]["branches"] == ["main"]
