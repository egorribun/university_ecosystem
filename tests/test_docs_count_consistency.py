"""AUD-423: documented secret-scanning counts match the committed inventories.

The counts are read from the files they describe, so a documentation claim
cannot drift from the detect-secrets baseline or the disposition policy
without this test failing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    return (ROOT / relative).read_text(encoding="utf-8")


def test_secrets_baseline_count_matches_the_committed_file() -> None:
    assert _baseline_identities() == 242


def test_disposition_policy_count_matches_the_committed_file() -> None:
    assert _disposition_records() == 351


def test_docs_index_states_the_committed_baseline_and_disposition_counts() -> None:
    document = _text("docs/README.md")

    assert f"baseline contains {_baseline_identities()} identities" in document
    assert f"disposition scope is {_disposition_records()};" in document
    assert "319" not in re.findall(r"\b\d{3}\b", document)


def test_agents_guide_states_the_committed_baseline_and_disposition_counts() -> None:
    guide = _text("AGENTS.md")

    assert f"baseline contains {_baseline_identities()} identities" in guide
    assert f"contains exactly {_disposition_records()} finite approved" in guide


def test_count_census_detects_a_stale_claim() -> None:
    stale = "The current baseline contains 319 identities."
    current = f"The current baseline contains {_baseline_identities()} identities."

    assert f"baseline contains {_baseline_identities()} identities" not in stale
    assert f"baseline contains {_baseline_identities()} identities" in current
