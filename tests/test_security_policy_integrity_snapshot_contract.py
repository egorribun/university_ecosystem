"""Contracts for the immutable policy workflow's API snapshot boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "security-policy-integrity.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_policy_snapshot_is_revalidated_after_paginated_file_listing() -> None:
    source = _source()

    metadata_endpoint = '"repos/$GITHUB_REPOSITORY/pulls/$PR_NUMBER"'
    assert source.count(metadata_endpoint) >= 2
    assert "pr_metadata_after" in source
    assert ".changed_files == $expected_changed_files" in source
    assert "metadata changed while enumerating" in source


def test_policy_snapshot_rejects_duplicate_changed_paths() -> None:
    source = _source()

    assert "group_by(.)" in source
    assert "select(length > 1)" in source
    assert "duplicate changed-file path" in source
