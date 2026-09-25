"""Keep the CI spelling gate tied to a reviewed English documentation set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "cspell.json"
CI = ROOT / ".github/workflows/ci.yml"
CANARY = [
    "docs/README.md",
    "docs/api_versioning.md",
    "docs/api/README.md",
    "docs/adr/README.md",
    "docs/adr/ADR-039-frontend-mutation-shard-cost-model.md",
    "docs/adr/ADR-040-frontend-mutation-presentation-ignorer.md",
]
if not CONFIG.is_file() or not CI.is_file():
    pytest.skip(  # QUALITY-123 @egorribun
        "Spelling gate assets are absent from this isolated test checkout",
        allow_module_level=True,
    )


def test_cspell_config_selects_existing_reviewed_english_docs() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert config["files"] == CANARY
    assert all((ROOT / path).is_file() for path in CANARY)
    assert "**/*" not in config["ignorePaths"]


def test_ci_checks_canary_every_run_and_rejects_empty_results() -> None:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["quality"]["steps"]
    spellcheck = next(step for step in steps if step.get("name") == "Run cspell")
    result_guard = next(
        step
        for step in steps
        if step.get("name") == "Verify cspell checked reviewed docs"
    )

    assert spellcheck["id"] == "cspell"
    assert spellcheck["with"]["config"] == "cspell.json"
    assert spellcheck["with"]["use_cspell_files"] is True
    assert spellcheck["with"]["incremental_files_only"] is False
    assert result_guard["env"]["CSPELL_FILES_CHECKED"] == (
        "${{ steps.cspell.outputs.number_of_files_checked }}"
    )
    assert 'if [[ "$CSPELL_FILES_CHECKED" != "6" ]]; then' in result_guard["run"]
    assert "exit 1" in result_guard["run"]
