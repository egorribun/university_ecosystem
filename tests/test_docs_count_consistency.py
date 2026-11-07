"""AUD-423: documented secret-scanning counts match the workspace inventories.

The counts are read from the files they describe, so documentation stays aligned
with the current checkout, including approved policy updates that are not yet
published.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISPOSITION_RECORDS = 506


def _baseline_identities() -> int:
    baseline = json.loads((ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
    return sum(len(entries) for entries in baseline["results"].values())


def _disposition_records() -> int:
    policy = json.loads(
        (ROOT / "quality" / "security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    return len(policy["records"])


def _text(relative: str) -> str:
    return " ".join((ROOT / relative).read_text(encoding="utf-8").split())


def test_secrets_baseline_count_matches_the_workspace_file() -> None:
    assert _baseline_identities() == 242


def test_disposition_policy_count_matches_the_workspace_file() -> None:
    assert _disposition_records() == EXPECTED_DISPOSITION_RECORDS


def test_docs_index_states_the_workspace_baseline_and_disposition_counts() -> None:
    document = _text("docs/README.md")

    assert f"baseline contains {_baseline_identities()} identities" in document
    assert re.search(
        rf"working tree contains\s+{EXPECTED_DISPOSITION_RECORDS}\b", document
    )
    assert (
        "363 previously active records, 106 previously owner-approved identities now materialized, "
        "21 previously approved exact identities, and five newly approved exact identities"
    ) in document
    assert (
        "The inventory is not evidence of a passing scan or required checks; each "
        "source SHA requires its own validation."
    ) in document
    assert "319" not in re.findall(r"\b\d{3}\b", document)


def test_agents_guide_states_the_workspace_baseline_and_disposition_counts() -> None:
    guide = _text("AGENTS.md")

    assert f"baseline contains {_baseline_identities()} identities" in guide
    assert f"contains {EXPECTED_DISPOSITION_RECORDS} finite approved" in guide
    assert (
        "This count is inventory only, not evidence of a passing scan or required checks."
    ) in guide


def test_audit_summaries_state_the_current_policy_inventory() -> None:
    inventory = (
        "The current policy-file inventory is **"
        f"{_disposition_records()} dispositions / "
        f"{_baseline_identities()} baseline identities / 27 Gitleaks fingerprints / "
        "15 Semgrep rows**."
    )
    for relative in (
        "docs/audits/INDEX.md",
        "docs/superpowers/plans/STATUS.md",
        "docs/audits/AUDIT-2026-11-06-full-reassessment.md",
    ):
        assert inventory in _text(relative), relative


def test_count_census_detects_a_stale_claim() -> None:
    stale = "The current baseline contains 319 identities."
    current = f"The current baseline contains {_baseline_identities()} identities."

    assert f"baseline contains {_baseline_identities()} identities" not in stale
    assert f"baseline contains {_baseline_identities()} identities" in current
