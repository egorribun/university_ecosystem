"""Contracts for the audited SQLAlchemy dual-defaults migration boundary."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dual_defaults_inventory_and_exceptions_are_recorded() -> None:
    """BE-02 must have a durable measured inventory before any DDL rewrite."""

    adr_path = ROOT / "docs/adr/ADR-036-sqlalchemy-dual-default-migration-policy.md"
    index_path = ROOT / "docs/adr/README.md"
    assert adr_path.is_file()
    adr = adr_path.read_text(encoding="utf-8").lower()
    assert "status" in adr and "accepted" in adr
    for heading in (
        "## context",
        "## inventory",
        "## decision",
        "## migration policy",
        "## exceptions",
    ):
        assert heading in adr
    assert "26 declarations have both" in adr
    assert "91 effective declarations are python-only" in adr
    assert "18 declarations are server-only" in adr
    assert "108 `mapped_column` calls" in adr
    assert re.search(r"26 both,\s+65 python-only and 17\s+server-only", adr)
    assert "uuidv7 primary-key" in adr
    assert "54 explicit python-only" not in adr
    assert "postgresql catalog preflight" in adr
    assert "check ... not valid" in adr
    index = index_path.read_text(encoding="utf-8")
    assert "ADR-036" in index
    assert "SQLAlchemy Dual-Defaults Migration Policy" in index
