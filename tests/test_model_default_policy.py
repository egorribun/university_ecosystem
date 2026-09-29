"""Contracts for the audited SQLAlchemy dual-defaults migration boundary."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "quality" / "model-default-policy.json"


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
    assert "53 declarations have both" in adr
    assert "81 effective declarations are python-only" in adr
    assert "0 declarations are server-only" in adr
    assert "108 `mapped_column` calls" in adr
    assert re.search(r"53 both,\s+55 python-only and 0\s+server-only", adr)
    assert "uuidv7 primary-key" in adr
    assert "54 explicit python-only" not in adr
    assert "postgresql catalog preflight" in adr
    assert "phase two: python-side completion for server-only defaults" in adr
    # Phase two changed no DDL; that property is what makes it safe to ship
    # without the catalog preflight the DDL phases require.
    assert "no ddl and no migration" in adr
    assert "check ... not valid" in adr
    index = index_path.read_text(encoding="utf-8")
    assert "ADR-036" in index
    assert "SQLAlchemy Dual-Defaults Migration Policy" in index


def test_effective_metadata_inventory_matches_adr_snapshot() -> None:
    """Keep the measured ADR counts synchronized with SQLAlchemy metadata."""

    import app.models  # noqa: F401  # ensure every model is registered
    from app.core.database import Base

    counts = {"both": 0, "python_only": 0, "server_only": 0}
    computed_columns = []
    for table in Base.metadata.tables.values():
        for column in table.c:
            if column.computed is not None:
                computed_columns.append(f"{table.name}.{column.name}")
                continue
            has_python_default = column.default is not None
            has_server_default = column.server_default is not None
            if has_python_default and has_server_default:
                counts["both"] += 1
            elif has_python_default:
                counts["python_only"] += 1
            elif has_server_default:
                counts["server_only"] += 1

    # The expected numbers come from the policy.  They move with every BE-02
    # phase, so a private copy here either has to be edited in lockstep or
    # silently contradicts the policy this test exists to protect.
    expected = json.loads(POLICY_PATH.read_text(encoding="utf-8"))["expected"]

    assert len(Base.metadata.tables) == expected["table_count"]
    assert computed_columns == expected["computed_columns"]
    assert counts == expected["effective_counts"]
